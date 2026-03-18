"""
Unit tests for connectivity.py.

All external HTTP calls are mocked via unittest.mock so that tests run
offline without any real network activity or Ollama instance.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectivity import check_internet, check_ollama


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(status_code: int) -> MagicMock:
    """
    Build a minimal mock that mimics an httpx.Response.

    Args:
        status_code: The HTTP status code the mock should report.

    Returns:
        A MagicMock pre-configured with the given status_code.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    return mock_resp


def _patch_async_client(mock_response: MagicMock):
    """
    Return a context-manager patch that injects `mock_response` as the result
    of `httpx.AsyncClient().get(...)`.

    The patch target uses the module name as imported by connectivity.py so
    that Python's import machinery resolves it correctly.
    """
    return patch("connectivity.httpx.AsyncClient")


# ---------------------------------------------------------------------------
# check_internet
# ---------------------------------------------------------------------------


class TestCheckInternet:
    """Tests for check_internet()."""

    async def test_returns_true_on_200(self):
        """A 200 response means the internet is reachable."""
        mock_response = _make_mock_response(200)

        with patch("connectivity.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.get = AsyncMock(return_value=mock_response)

            result = await check_internet()

        assert result is True

    async def test_returns_true_on_4xx(self):
        """
        A 4xx from the probe URL still means the network is reachable.
        (Unexpected, but we should not flag it as offline.)
        """
        mock_response = _make_mock_response(403)

        with patch("connectivity.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.get = AsyncMock(return_value=mock_response)

            result = await check_internet()

        assert result is True

    async def test_returns_false_on_timeout(self):
        """A timeout exception is swallowed and mapped to False."""
        with patch("connectivity.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.get = AsyncMock(
                side_effect=httpx_timeout_exception()
            )

            result = await check_internet()

        assert result is False

    async def test_returns_false_on_connection_error(self):
        """Any connection-level exception is swallowed and mapped to False."""
        with patch("connectivity.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.get = AsyncMock(
                side_effect=Exception("Network unreachable")
            )

            result = await check_internet()

        assert result is False

    async def test_uses_custom_probe_url(self):
        """The probe_url parameter is forwarded to httpx.get()."""
        custom_url = "https://example.com"
        mock_response = _make_mock_response(200)

        with patch("connectivity.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get = AsyncMock(return_value=mock_response)
            MockClient.return_value.get = mock_get

            await check_internet(probe_url=custom_url)

        # Verify the custom URL was passed as the first positional argument.
        call_args = mock_get.call_args
        assert call_args[0][0] == custom_url


# ---------------------------------------------------------------------------
# check_ollama
# ---------------------------------------------------------------------------


class TestCheckOllama:
    """Tests for check_ollama()."""

    async def test_returns_true_when_ollama_responds(self):
        """Ollama returning 200 means the service is healthy."""
        mock_response = _make_mock_response(200)

        with patch("connectivity.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.get = AsyncMock(return_value=mock_response)

            result = await check_ollama()

        assert result is True

    async def test_returns_false_when_ollama_is_down(self):
        """A connection-refused exception means Ollama is not running."""
        with patch("connectivity.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value.get = AsyncMock(
                side_effect=Exception("Connection refused")
            )

            result = await check_ollama()

        assert result is False

    async def test_uses_custom_base_url(self):
        """The base_url parameter is forwarded to the client."""
        custom_url = "http://localhost:22222"
        mock_response = _make_mock_response(200)

        with patch("connectivity.httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(
                return_value=MockClient.return_value
            )
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get = AsyncMock(return_value=mock_response)
            MockClient.return_value.get = mock_get

            await check_ollama(base_url=custom_url)

        call_args = mock_get.call_args
        assert call_args[0][0] == custom_url


# ---------------------------------------------------------------------------
# Private helpers (not part of the public test surface)
# ---------------------------------------------------------------------------

def httpx_timeout_exception():
    """
    Return an httpx.TimeoutException instance to simulate a network timeout
    without needing an import at module level.
    """
    import httpx as _httpx  # noqa: PLC0415

    return _httpx.TimeoutException("Timed out")
