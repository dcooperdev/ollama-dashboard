"""
FastAPI dependency providers.

Centralising dependency creation here allows every router to stay thin and
makes it trivial to swap real implementations for mocks in tests via
`app.dependency_overrides[get_ollama_client] = lambda: FakeClient()`.
"""

from ollama_client import OllamaClient

# A single shared client instance reused across all requests.
# httpx.AsyncClient is internally created per-call inside OllamaClient, so
# this singleton is safe for concurrent request handling.
_ollama_client = OllamaClient()


def get_ollama_client() -> OllamaClient:
    """
    FastAPI dependency that returns the shared OllamaClient singleton.

    Override this in tests::

        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
    """
    return _ollama_client
