"""
Unit tests for ollama_client.py.

All HTTP interactions are mocked — no real Ollama instance is required.
Streaming methods use async generator helpers to simulate line-by-line
server-sent JSON responses.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ollama_client import OllamaClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> OllamaClient:
    """
    Return an OllamaClient pointed at a fake URL so no real Ollama is needed.
    """
    return OllamaClient(base_url="http://fake-ollama:11434")


# ---------------------------------------------------------------------------
# Async generator helpers
# ---------------------------------------------------------------------------


async def _async_lines(*lines: str):
    """
    Yield each string in `lines` one at a time, mimicking httpx's
    `response.aiter_lines()` async generator.
    """
    for line in lines:
        yield line


def _make_stream_ctx(lines: list[str]) -> MagicMock:
    """
    Build a mock that behaves like the context manager returned by
    `httpx.AsyncClient.stream(...)`.

    The mock's __aenter__ returns a fake response whose `aiter_lines` method
    yields the provided `lines`, and whose `aclose` and `raise_for_status`
    are no-ops.

    Args:
        lines: Iterable of raw string lines to yield from `aiter_lines()`.

    Returns:
        A MagicMock suitable for use with `async with client.stream(...) as resp`.
    """
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aclose = AsyncMock()
    mock_response.aiter_lines = MagicMock(return_value=_async_lines(*lines))

    stream_ctx = MagicMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)
    return stream_ctx


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


class TestListModels:
    """Tests for OllamaClient.list_models()."""

    async def test_returns_model_list(self, client: OllamaClient):
        """A JSON payload with a ``models`` key is parsed correctly."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:latest"},
                {"name": "mistral:latest"},
            ]
        }

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.get = AsyncMock(return_value=mock_response)

            result = await client.list_models()

        assert len(result) == 2
        assert result[0]["name"] == "llama3:latest"
        assert result[1]["name"] == "mistral:latest"

    async def test_returns_empty_list_when_key_missing(self, client: OllamaClient):
        """
        If Ollama omits the ``models`` key (no models installed), the method
        must return an empty list rather than raising a KeyError.
        """
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {}

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.get = AsyncMock(return_value=mock_response)

            result = await client.list_models()

        assert result == []

    async def test_calls_correct_endpoint(self, client: OllamaClient):
        """The GET request must target /api/tags on the configured base_url."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"models": []}

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get = AsyncMock(return_value=mock_response)
            MockClient.return_value.get = mock_get

            await client.list_models()

        mock_get.assert_called_once_with("http://fake-ollama:11434/api/tags")


# ---------------------------------------------------------------------------
# delete_model
# ---------------------------------------------------------------------------


class TestDeleteModel:
    """Tests for OllamaClient.delete_model()."""

    async def test_sends_delete_request_with_correct_body(
        self, client: OllamaClient
    ):
        """
        The DELETE /api/delete request must carry the model name in the JSON body
        and must use the HTTP DELETE verb.
        """
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_request = AsyncMock(return_value=mock_response)
            MockClient.return_value.request = mock_request

            await client.delete_model("llama3:latest")

        mock_request.assert_called_once_with(
            "DELETE",
            "http://fake-ollama:11434/api/delete",
            json={"name": "llama3:latest"},
        )

    async def test_raises_on_http_error(self, client: OllamaClient):
        """
        If Ollama returns a non-2xx status, raise_for_status propagates the
        exception to the caller.
        """
        import httpx

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(),
            )
        )

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.request = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await client.delete_model("nonexistent:latest")


# ---------------------------------------------------------------------------
# pull_model  (streaming)
# ---------------------------------------------------------------------------


class TestPullModel:
    """Tests for OllamaClient.pull_model()."""

    async def test_yields_progress_chunks(self, client: OllamaClient):
        """Each newline-delimited JSON line must be yielded as a parsed dict."""
        lines = [
            json.dumps({"status": "pulling manifest"}),
            json.dumps(
                {"status": "downloading", "completed": 1_048_576, "total": 8_388_608}
            ),
            json.dumps({"status": "success"}),
        ]
        stream_ctx = _make_stream_ctx(lines)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            chunks = [chunk async for chunk in client.pull_model("llama3:latest")]

        assert len(chunks) == 3
        assert chunks[0] == {"status": "pulling manifest"}
        assert chunks[1]["completed"] == 1_048_576
        assert chunks[2]["status"] == "success"

    async def test_skips_blank_lines(self, client: OllamaClient):
        """Blank lines in the stream must be silently ignored."""
        lines = [
            "",  # blank line — should be skipped
            json.dumps({"status": "success"}),
            "",  # trailing blank line
        ]
        stream_ctx = _make_stream_ctx(lines)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            chunks = [chunk async for chunk in client.pull_model("mistral:latest")]

        assert len(chunks) == 1
        assert chunks[0]["status"] == "success"

    async def test_calls_correct_endpoint_and_payload(self, client: OllamaClient):
        """POST /api/pull must include the model name and stream=True."""
        stream_ctx = _make_stream_ctx([json.dumps({"status": "success"})])

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_stream = MagicMock(return_value=stream_ctx)
            MockClient.return_value.stream = mock_stream

            _ = [chunk async for chunk in client.pull_model("phi3:latest")]

        mock_stream.assert_called_once_with(
            "POST",
            "http://fake-ollama:11434/api/pull",
            json={"name": "phi3:latest", "stream": True},
        )

    async def test_aclose_called_on_stream_response(self, client: OllamaClient):
        """
        The streaming response's aclose() must be called even when the generator
        is fully consumed, ensuring the TCP connection is returned to the pool.
        """
        lines = [json.dumps({"status": "success"})]
        stream_ctx = _make_stream_ctx(lines)
        mock_response = stream_ctx.__aenter__.return_value

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            _ = [chunk async for chunk in client.pull_model("llama3:latest")]

        mock_response.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# chat  (streaming)
# ---------------------------------------------------------------------------


class TestChat:
    """Tests for OllamaClient.chat()."""

    async def test_yields_token_strings(self, client: OllamaClient):
        """Each parsed ``content`` value must be individually yielded."""
        messages = [{"role": "user", "content": "What is 2+2?"}]
        lines = [
            json.dumps(
                {"message": {"role": "assistant", "content": "2+2 is "}, "done": False}
            ),
            json.dumps(
                {"message": {"role": "assistant", "content": "4."}, "done": False}
            ),
            json.dumps(
                {"message": {"role": "assistant", "content": ""}, "done": True}
            ),
        ]
        stream_ctx = _make_stream_ctx(lines)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            tokens = [t async for t in client.chat("llama3:latest", messages)]

        assert tokens == ["2+2 is ", "4."]

    async def test_stops_on_done_flag(self, client: OllamaClient):
        """
        No tokens should be yielded after a chunk where ``done`` is True,
        even if Ollama sends more lines after that.
        """
        messages = [{"role": "user", "content": "Hello"}]
        lines = [
            json.dumps({"message": {"role": "assistant", "content": "Hi"}, "done": True}),
            # This line must never be yielded because done=True was already seen.
            json.dumps({"message": {"role": "assistant", "content": " extra"}, "done": False}),
        ]
        stream_ctx = _make_stream_ctx(lines)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            tokens = [t async for t in client.chat("llama3:latest", messages)]

        # "Hi" is yielded; " extra" is not because we break after done=True.
        assert tokens == ["Hi"]

    async def test_skips_empty_content_tokens(self, client: OllamaClient):
        """
        Chunks with an empty ``content`` string (e.g., the final done chunk)
        must NOT be yielded as tokens.
        """
        messages = [{"role": "user", "content": "Ping"}]
        lines = [
            json.dumps({"message": {"role": "assistant", "content": "Pong"}, "done": False}),
            json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}),
        ]
        stream_ctx = _make_stream_ctx(lines)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            tokens = [t async for t in client.chat("llama3:latest", messages)]

        assert tokens == ["Pong"]

    async def test_aclose_called_on_stream_response(self, client: OllamaClient):
        """aclose() must be called to prevent connection leaks."""
        messages = [{"role": "user", "content": "Hi"}]
        lines = [
            json.dumps({"message": {"role": "assistant", "content": "Hello"}, "done": True}),
        ]
        stream_ctx = _make_stream_ctx(lines)
        mock_response = stream_ctx.__aenter__.return_value

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            _ = [t async for t in client.chat("llama3:latest", messages)]

        mock_response.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# generate  (streaming)
# ---------------------------------------------------------------------------


class TestGenerate:
    """Tests for OllamaClient.generate()."""

    async def test_yields_response_tokens(self, client: OllamaClient):
        """Each ``response`` field from the streamed JSON is yielded as a token."""
        lines = [
            json.dumps({"response": "The capital ", "done": False}),
            json.dumps({"response": "of France is Paris.", "done": True}),
        ]
        stream_ctx = _make_stream_ctx(lines)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            tokens = [t async for t in client.generate("mistral:latest", "Capital of France?")]

        assert tokens == ["The capital ", "of France is Paris."]

    async def test_calls_correct_endpoint_and_payload(self, client: OllamaClient):
        """POST /api/generate must carry the model, prompt, and stream=True."""
        prompt = "What is Python?"
        lines = [json.dumps({"response": "A language.", "done": True})]
        stream_ctx = _make_stream_ctx(lines)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_stream = MagicMock(return_value=stream_ctx)
            MockClient.return_value.stream = mock_stream

            _ = [t async for t in client.generate("gemma2:latest", prompt)]

        mock_stream.assert_called_once_with(
            "POST",
            "http://fake-ollama:11434/api/generate",
            json={"model": "gemma2:latest", "prompt": prompt, "stream": True},
        )

    async def test_aclose_called_on_stream_response(self, client: OllamaClient):
        """aclose() must be called to prevent connection leaks."""
        lines = [json.dumps({"response": "Done.", "done": True})]
        stream_ctx = _make_stream_ctx(lines)
        mock_response = stream_ctx.__aenter__.return_value

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            _ = [t async for t in client.generate("mistral:latest", "Hello")]

        mock_response.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# Error paths for chat() — 400 → ValueError, non-400 → re-raise
# ---------------------------------------------------------------------------


class TestChatErrorPaths:
    """Tests for OllamaClient.chat() HTTP error handling (lines 162-172, 176)."""

    def _make_error_stream_ctx(self, status_code: int) -> MagicMock:
        """Build a stream context whose raise_for_status raises HTTPStatusError."""
        import httpx

        mock_request = MagicMock()
        mock_response_obj = MagicMock()
        mock_response_obj.status_code = status_code
        exc = httpx.HTTPStatusError(
            f"{status_code}", request=mock_request, response=mock_response_obj
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(side_effect=exc)
        mock_response.aclose = AsyncMock()
        mock_response.aiter_lines = MagicMock(return_value=_async_lines())

        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        return stream_ctx

    async def test_400_converted_to_value_error(self):
        """HTTP 400 from /api/chat must be converted to a friendly ValueError."""
        client = OllamaClient(base_url="http://fake-ollama:11434")
        stream_ctx = self._make_error_stream_ctx(400)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            with pytest.raises(ValueError, match="embedding"):
                async for _ in client.chat("embed-model", [{"role": "user", "content": "hi"}]):
                    pass

    async def test_non_400_http_error_reraised(self):
        """HTTP errors other than 400 (e.g. 503) must be re-raised as-is."""
        import httpx

        client = OllamaClient(base_url="http://fake-ollama:11434")
        stream_ctx = self._make_error_stream_ctx(503)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            with pytest.raises(httpx.HTTPStatusError):
                async for _ in client.chat("some-model", [{"role": "user", "content": "hi"}]):
                    pass


# ---------------------------------------------------------------------------
# Error paths for generate() — 400 → ValueError, non-400 → re-raise
# ---------------------------------------------------------------------------


class TestGenerateErrorPaths:
    """Tests for OllamaClient.generate() HTTP error handling (lines 216-224, 228)."""

    def _make_error_stream_ctx(self, status_code: int) -> MagicMock:
        """Build a stream context whose raise_for_status raises HTTPStatusError."""
        import httpx

        mock_request = MagicMock()
        mock_response_obj = MagicMock()
        mock_response_obj.status_code = status_code
        exc = httpx.HTTPStatusError(
            f"{status_code}", request=mock_request, response=mock_response_obj
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(side_effect=exc)
        mock_response.aclose = AsyncMock()
        mock_response.aiter_lines = MagicMock(return_value=_async_lines())

        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        return stream_ctx

    async def test_400_converted_to_value_error(self):
        """HTTP 400 from /api/generate must be converted to a friendly ValueError."""
        client = OllamaClient(base_url="http://fake-ollama:11434")
        stream_ctx = self._make_error_stream_ctx(400)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            with pytest.raises(ValueError, match="embedding"):
                async for _ in client.generate("embed-model", "some prompt"):
                    pass

    async def test_non_400_http_error_reraised(self):
        """HTTP errors other than 400 must be re-raised as-is from generate()."""
        import httpx

        client = OllamaClient(base_url="http://fake-ollama:11434")
        stream_ctx = self._make_error_stream_ctx(503)

        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            with pytest.raises(httpx.HTTPStatusError):
                async for _ in client.generate("some-model", "some prompt"):
                    pass


# ---------------------------------------------------------------------------
# OllamaClient constructor — base_url stripping
# ---------------------------------------------------------------------------


class TestOllamaClientConstructor:
    """Tests for OllamaClient.__init__() base_url normalisation."""

    def test_strips_trailing_slash(self):
        """Trailing slashes on base_url must be stripped to avoid double slashes."""
        client = OllamaClient(base_url="http://localhost:11434/")
        assert client.base_url == "http://localhost:11434"

    def test_default_base_url(self):
        """Default base_url should be the standard Ollama port."""
        client = OllamaClient()
        assert "11434" in client.base_url


# ---------------------------------------------------------------------------
# deps.py — get_ollama_client
# ---------------------------------------------------------------------------


class TestGetOllamaClient:
    """Tests for deps.get_ollama_client()."""

    def test_returns_ollama_client_instance(self):
        """get_ollama_client() must return a properly initialised OllamaClient."""
        from deps import get_ollama_client

        result = get_ollama_client()
        assert isinstance(result, OllamaClient)

    def test_returns_same_singleton(self):
        """Multiple calls must return the same cached singleton instance."""
        from deps import get_ollama_client

        a = get_ollama_client()
        b = get_ollama_client()
        assert a is b
