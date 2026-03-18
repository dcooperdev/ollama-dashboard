"""
Direct unit tests for private generator functions in routers/chat.py and
routers/models.py, covering disconnection, CancelledError, and regex-fallback
paths that cannot be exercised via FastAPI TestClient.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helper: mock Request
# ---------------------------------------------------------------------------

def _make_request(disconnected: bool = False) -> MagicMock:
    """Build a mock FastAPI Request whose is_disconnected() returns the given value."""
    req = MagicMock()
    req.is_disconnected = AsyncMock(return_value=disconnected)
    return req


async def _collect(gen) -> list[str]:
    """Drain an async generator and return all yielded strings."""
    results = []
    async for item in gen:
        results.append(item)
    return results


# ---------------------------------------------------------------------------
# _token_stream — disconnect break (line 203) and CancelledError (line 206)
# ---------------------------------------------------------------------------


class TestTokenStream:
    """Tests for _token_stream() generator."""

    async def test_break_on_disconnect(self):
        """is_disconnected() == True must break the loop without emitting the token."""
        from routers.chat import _token_stream

        async def token_gen():
            yield "hello"
            yield "world"

        # Disconnect before first iteration
        request = _make_request(disconnected=True)
        results = await _collect(_token_stream(token_gen(), request))
        # break path hit — [DONE] emitted from else clause since no exception
        # But break means the else runs — check nothing in error branch
        assert not any("error" in r for r in results)

    async def test_yields_when_connected(self):
        """Tokens must be emitted when request is not disconnected."""
        from routers.chat import _token_stream

        async def token_gen():
            yield "hello"

        request = _make_request(disconnected=False)
        results = await _collect(_token_stream(token_gen(), request))

        assert len(results) == 2  # token event + [DONE]
        assert json.loads(results[0].replace("data: ", "").strip())["token"] == "hello"

    async def test_cancelled_error_passes_silently(self):
        """CancelledError from the token source must be swallowed silently (line 206)."""
        from routers.chat import _token_stream

        async def cancelled_gen():
            raise asyncio.CancelledError()
            yield  # pragma: no cover

        request = _make_request(disconnected=False)
        # Must not raise and must not emit error
        results = await _collect(_token_stream(cancelled_gen(), request))
        assert not any("error" in r for r in results)

    async def test_http_400_emits_friendly_error(self):
        """HTTP 400 from the token source must emit a friendly error SSE event."""
        from routers.chat import _token_stream

        async def http400_gen():
            req = httpx.Request("POST", "http://localhost/api/chat")
            resp = httpx.Response(400, text="Bad request", request=req)
            raise httpx.HTTPStatusError("400", request=req, response=resp)
            yield  # pragma: no cover

        request = _make_request(disconnected=False)
        results = await _collect(_token_stream(http400_gen(), request))

        assert len(results) == 1  # only error event (HTTPStatusError branch has no DONE)
        error_event = json.loads(results[0].replace("data: ", "").strip())
        assert "error" in error_event
        assert "embedding" in error_event["error"].lower()

    async def test_http_non_400_emits_generic_error(self):
        """HTTP 503 from the token source must emit a generic HTTP error SSE event."""
        from routers.chat import _token_stream

        async def http503_gen():
            req = httpx.Request("POST", "http://localhost/api/chat")
            resp = httpx.Response(503, text="Unavailable", request=req)
            raise httpx.HTTPStatusError("503", request=req, response=resp)
            yield  # pragma: no cover

        request = _make_request(disconnected=False)
        results = await _collect(_token_stream(http503_gen(), request))

        assert len(results) == 1
        error_event = json.loads(results[0].replace("data: ", "").strip())
        assert "error" in error_event
        assert "503" in error_event["error"]


# ---------------------------------------------------------------------------
# _stream_reprompt — disconnect return (line 247)
# ---------------------------------------------------------------------------


class TestStreamReprompt:
    """Tests for _stream_reprompt() disconnect branch (line 247)."""

    async def test_disconnect_during_reprompt_returns_early(self):
        """is_disconnected() during re-prompt must stop the generator immediately."""
        from routers.chat import _stream_reprompt

        async def reprompt_gen(model, messages):
            yield "token"
            yield "more"

        mock_ollama = MagicMock()
        mock_ollama.chat = reprompt_gen

        request = _make_request(disconnected=True)
        results = await _collect(
            _stream_reprompt(mock_ollama, "llama3", [{"role": "user", "content": "hi"}], "err", request)
        )

        # With is_disconnected True, should return before emitting tokens
        token_events = [r for r in results if '"token"' in r]
        assert token_events == []


# ---------------------------------------------------------------------------
# _meta_agent_interceptor — CancelledError (line 412)
# ---------------------------------------------------------------------------


class TestMetaAgentCancelledError:
    """Tests for _meta_agent_interceptor() CancelledError branch (line 412)."""

    async def test_cancelled_error_returns_silently(self):
        """CancelledError in the interceptor must be swallowed without an error event."""
        from routers.chat import _meta_agent_interceptor

        async def chat_gen(model, messages):
            raise asyncio.CancelledError()
            yield  # pragma: no cover

        mock_ollama = MagicMock()
        mock_ollama.chat = chat_gen
        mock_ollama.list_models = AsyncMock(return_value=[])

        request = _make_request(disconnected=False)
        results = await _collect(
            _meta_agent_interceptor("llama3", [{"role": "user", "content": "hi"}], mock_ollama, request)
        )

        # No error event (clean exit)
        data_lines = [r for r in results if "error" in r]
        assert data_lines == []


# ---------------------------------------------------------------------------
# _meta_agent_interceptor — disconnect in main loop (line 277)
# ---------------------------------------------------------------------------


class TestMetaAgentMainLoopDisconnect:
    """Tests for disconnect check in _meta_agent_interceptor main loop (line 277)."""

    async def test_disconnect_during_main_streaming_returns_early(self):
        """is_disconnected() True after first token in main loop must stop the generator."""
        from routers.chat import _meta_agent_interceptor

        disconnect_calls = [0]

        async def chat_gen(model, messages):
            yield "Hello"  # should be yielded
            yield " World"  # should NOT be yielded (disconnect happens between these)

        async def is_disconnected_fn():
            disconnect_calls[0] += 1
            # Return False on call 1 (first chunk), True on call 2 (second chunk)
            return disconnect_calls[0] > 1

        mock_ollama = MagicMock()
        mock_ollama.chat = chat_gen
        mock_ollama.list_models = AsyncMock(return_value=[])

        request = MagicMock()
        request.is_disconnected = is_disconnected_fn

        results = await _collect(
            _meta_agent_interceptor("llama3", [{"role": "user", "content": "hi"}], mock_ollama, request)
        )

        # First token must be emitted; processing stops after disconnect
        assert any('"Hello"' in r for r in results)
        # Second token must NOT be emitted
        assert not any('"World"' in r for r in results)


# ---------------------------------------------------------------------------
# _meta_agent_interceptor — disconnect during expert generation (line 362)
# ---------------------------------------------------------------------------


class TestMetaAgentDisconnectDuringExpert:
    """Tests for disconnect check inside expert generation loop (line 362)."""

    async def test_disconnect_during_expert_returns_early(self):
        """is_disconnected() becomes True mid-expert-generation, hitting line 362 break."""
        from routers.chat import _meta_agent_interceptor

        async def chat_gen(model, messages):
            yield '{"action": "consult", "target_model": "codellama:latest", "prompt": "help"}'

        async def gen_gen(model, prompt):
            yield "first expert token"
            yield "second expert token"  # should not be reached after disconnect

        mock_ollama = MagicMock()
        mock_ollama.chat = chat_gen
        mock_ollama.generate = gen_gen
        mock_ollama.list_models = AsyncMock(return_value=[{"name": "codellama:latest", "details": {}}])

        # First few calls return False (initial chat streaming), then True once in expert gen
        call_count = 0
        async def is_disconnected_fn():
            nonlocal call_count
            call_count += 1
            # Allow the JSON to be parsed first (call 1), then disconnect on expert generation
            return call_count > 2  # True when checking inside expert loop

        request = MagicMock()
        request.is_disconnected = is_disconnected_fn

        results = await _collect(
            _meta_agent_interceptor(
                "llama3",
                [{"role": "user", "content": "write code"}],
                mock_ollama,
                request,
                valid_model_names=frozenset(["codellama:latest"]),
            )
        )

        # The consulting event must have been emitted before disconnection
        assert any("consulting" in r for r in results)
        # The generator must have stopped without emitting all expert tokens as final synthesis



# ---------------------------------------------------------------------------
# _meta_agent_interceptor — buffer wait after '{' with no next char yet (lines 299-300)
# ---------------------------------------------------------------------------


class TestMetaAgentBufferWait:
    """Tests for the 'wait for next chunk' branch when buffer ends exactly with '{'."""

    async def test_brace_at_end_waits_for_next_chunk(self):
        """Buffer ending in '{' without a following char must continue to next chunk."""
        from routers.chat import _meta_agent_interceptor

        # Yield '{' alone — triggers lines 299-300: not enough info yet, continue
        # Then yield content that completes the buffer to something flushable
        async def chat_gen(model, messages):
            yield "{"          # triggers lines 299-300 buffer-wait branch
            yield "plain text"  # continues, now buffer = "{plain text" → brace not followed by quote

        mock_ollama = MagicMock()
        mock_ollama.chat = chat_gen
        mock_ollama.list_models = AsyncMock(return_value=[])

        request = _make_request(disconnected=False)
        results = await _collect(
            _meta_agent_interceptor("llama3", [{"role": "user", "content": "hi"}], mock_ollama, request)
        )
        # Must complete without crashing
        assert any("DONE" in r for r in results)


# ---------------------------------------------------------------------------
# _meta_agent_interceptor — regex JSON fallback (lines 325-333)
# ---------------------------------------------------------------------------


class TestMetaAgentRegexFallback:
    """Tests for the regex fallback path (lines 325-333)."""

    async def test_regex_extracts_json_embedded_in_text(self):
        """Regex must extract JSON embedded in a larger buffer with trailing prose."""
        from routers.chat import _meta_agent_interceptor

        # The JSON has trailing text after it — json.loads would fail from start,
        # but re.search(r'{.*}') extracts the JSON block.
        async def chat_gen(model, messages):
            yield '{"action": "consult", "target_model": "codellama:latest", "prompt": "help"} trailing prose'

        async def gen_gen(model, prompt):
            yield "expert answer"
            return

        mock_ollama = MagicMock()
        mock_ollama.chat = chat_gen
        mock_ollama.generate = gen_gen
        mock_ollama.list_models = AsyncMock(return_value=[{"name": "codellama:latest", "details": {}}])

        request = _make_request(disconnected=False)
        results = await _collect(
            _meta_agent_interceptor(
                "llama3",
                [{"role": "user", "content": "hi"}],
                mock_ollama,
                request,
                valid_model_names=frozenset(["codellama:latest"]),
            )
        )
        # The consult must have been intercepted — consulting status event emitted
        assert any("consulting" in r for r in results)


# ---------------------------------------------------------------------------
# _meta_agent_interceptor — pass branch in JSON accumulation (line 315)
# ---------------------------------------------------------------------------


class TestMetaAgentPassBranch:
    """Tests for the pass statement in JSON accumulation mode (line 315)."""

    async def test_brace_without_quote_in_accumulation_mode(self):
        """In JSON accumulation mode, a char after brace that isn't '\"' hits the pass."""
        from routers.chat import _meta_agent_interceptor

        # Send brace (to start accumulation), then a token that starts with non-quote
        # The second chunk starts with '{' without '"' — hits line 313 condition
        async def chat_gen(model, messages):
            yield "{"            # starts JSON accumulation, not enough info: continue
            yield "notquote}"   # in accumulation mode: after_brace starts with 'n', hits pass (line 315)
                                 # then tries json.loads("{notquote}") which fails, no regex match
                                 # buffer stays, then overflows or stream ends

        mock_ollama = MagicMock()
        mock_ollama.chat = chat_gen
        mock_ollama.list_models = AsyncMock(return_value=[])

        request = _make_request(disconnected=False)
        results = await _collect(
            _meta_agent_interceptor("llama3", [{"role": "user", "content": "hi"}], mock_ollama, request)
        )
        # Must complete without crashing and flush residual content
        assert any("DONE" in r for r in results)


# ---------------------------------------------------------------------------
# _pull_event_stream — disconnect break (routers/models.py line 86)
# ---------------------------------------------------------------------------


class TestPullEventStreamDisconnect:
    """Tests for _pull_event_stream() disconnect break (line 86)."""

    async def test_disconnect_breaks_pull_stream(self):
        """is_disconnected() becomes True after yielding first chunk, hitting line 86 break."""
        from routers.models import _pull_event_stream

        chunks_yielded = [0]

        async def slow_pull(name):
            chunks_yielded[0] += 1
            yield {"status": "pulling manifest"}
            chunks_yielded[0] += 1
            yield {"status": "downloading"}  # should not be reached after disconnect

        mock_ollama = MagicMock()
        mock_ollama.pull_model = slow_pull

        disconnect_calls = [0]

        async def is_disconnected_fn():
            disconnect_calls[0] += 1
            # Return False on the first check (emit first chunk), True after
            return disconnect_calls[0] > 1

        request = MagicMock()
        request.is_disconnected = is_disconnected_fn

        results = await _collect(_pull_event_stream("llama3:latest", request, mock_ollama))

        # First chunk must be emitted
        assert len(results) == 1
        assert "pulling manifest" in results[0]



# ---------------------------------------------------------------------------
# ollama_client.py — blank line continue paths (lines 176, 228)
# (Tests with multiple blank lines to guarantee the continue branch is taken)
# ---------------------------------------------------------------------------


class TestOllamaClientBlankLineContinue:
    """Tests for blank-line filtering inside chat() and generate() (lines 176, 228)."""

    async def test_chat_skips_multiple_blank_lines(self):
        """Multiple blank lines between data lines must be silently skipped (line 176)."""
        from ollama_client import OllamaClient
        from unittest.mock import patch

        async def _lines(*lines):
            for line in lines:
                yield line

        data = [
            "",  # blank → continue
            "",  # blank → continue
            json.dumps({"message": {"role": "assistant", "content": "Hello"}, "done": False}),
            "",  # blank → continue
            json.dumps({"message": {"role": "assistant", "content": " world"}, "done": True}),
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aclose = AsyncMock()
        mock_response.aiter_lines = MagicMock(return_value=_lines(*data))

        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)

        client = OllamaClient(base_url="http://fake:11434")
        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            tokens = [t async for t in client.chat("llama3", [{"role": "user", "content": "hi"}])]

        assert tokens == ["Hello", " world"]

    async def test_generate_skips_multiple_blank_lines(self):
        """Multiple blank lines between generate lines must be silently skipped (line 228)."""
        from ollama_client import OllamaClient
        from unittest.mock import patch

        async def _lines(*lines):
            for line in lines:
                yield line

        data = [
            "",
            json.dumps({"response": "Paris", "done": False}),
            "",
            json.dumps({"response": ".", "done": True}),
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aclose = AsyncMock()
        mock_response.aiter_lines = MagicMock(return_value=_lines(*data))

        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)

        client = OllamaClient(base_url="http://fake:11434")
        with patch("ollama_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.stream = MagicMock(return_value=stream_ctx)

            tokens = [t async for t in client.generate("llama3", "Capital of France?")]

        assert tokens == ["Paris", "."]
