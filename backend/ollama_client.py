"""
Async wrapper around the Ollama HTTP REST API.

Design principles:
  - Zero routing logic — this module contains only business logic.
  - All methods are async generators or coroutines; callers decide how to serve them.
  - Streaming methods use `async with client.stream(...)` so that the underlying
    TCP connection is closed as soon as the caller stops consuming the generator
    (via `aclose()` or garbage collection), preventing resource leaks on client
    disconnection.
  - The `base_url` is injected at construction time, enabling clean unit testing
    without any real Ollama instance.
"""

import json
from typing import Any, AsyncIterator

import httpx

# Default Ollama service address.
OLLAMA_BASE_URL = "http://localhost:11434"


class OllamaClient:
    """
    Async HTTP client for the Ollama REST API.

    Usage:
        client = OllamaClient()
        models = await client.list_models()
    """

    def __init__(self, base_url: str = OLLAMA_BASE_URL) -> None:
        """
        Initialise the client.

        Args:
            base_url: Base URL of the Ollama HTTP server, e.g. "http://localhost:11434".
        """
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    async def list_models(self) -> list[dict[str, Any]]:
        """
        Fetch the list of locally installed models.

        Calls GET /api/tags and returns the ``models`` array from the response.

        Returns:
            A list of model descriptor dicts, each containing at minimum a ``name`` key.

        Raises:
            httpx.HTTPStatusError: If Ollama returns a non-2xx response.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            # Ollama may omit the ``models`` key entirely if no models are installed.
            return data.get("models", [])

    async def pull_model(self, name: str) -> AsyncIterator[dict[str, Any]]:
        """
        Stream pull progress for the named model from the Ollama registry.

        Calls POST /api/pull with ``stream: true``.  Each yielded dict mirrors one
        newline-delimited JSON object, e.g.:
            {"status": "downloading", "digest": "sha256:...", "completed": 1048576, "total": 8192000}
            {"status": "success"}

        Resource safety: the underlying ``httpx`` stream context is entered with
        ``async with``, so if the caller's ``async for`` loop exits early (e.g. the
        browser tab is closed and FastAPI cancels the request coroutine), the
        stream's ``__aexit__`` is called automatically via the generator's
        ``aclose()`` protocol, closing the TCP connection immediately.

        Args:
            name: Model tag to pull, e.g. ``"llama3:latest"``.

        Yields:
            Progress dicts from the Ollama streaming response.

        Raises:
            httpx.HTTPStatusError: If Ollama returns a non-2xx response at stream open.
        """
        # timeout=None because large model downloads may take many minutes.
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": name, "stream": True},
            ) as response:
                response.raise_for_status()
                try:
                    async for line in response.aiter_lines():
                        if line.strip():
                            yield json.loads(line)
                finally:
                    # Ensure the streaming response is drained/closed even if the
                    # caller abandons the generator mid-stream (client disconnect).
                    await response.aclose()

    async def delete_model(self, name: str) -> None:
        """
        Delete a locally installed model.

        Calls DELETE /api/delete with the model name in the JSON body.

        Args:
            name: Model tag to delete, e.g. ``"mistral:latest"``.

        Raises:
            httpx.HTTPStatusError: If Ollama returns a non-2xx response.
        """
        async with httpx.AsyncClient() as client:
            response = await client.request(
                "DELETE",
                f"{self.base_url}/api/delete",
                json={"name": name},
            )
            response.raise_for_status()

    # ------------------------------------------------------------------
    # Inference — chat mode (structured turn-by-turn messages)
    # ------------------------------------------------------------------

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        """
        Stream chat response tokens using the Ollama ``/api/chat`` endpoint.

        Each yielded value is the ``content`` string from one streaming chunk.
        The generator stops automatically when Ollama sends ``"done": true``.

        Resource safety is handled via the same ``try/finally`` + ``aclose()``
        pattern as :meth:`pull_model`.

        Args:
            model: Model tag, e.g. ``"llama3:latest"``.
            messages: List of message dicts with ``role`` and ``content`` keys.

        Yields:
            Individual text tokens to be concatenated by the caller.

        Raises:
            httpx.HTTPStatusError: On non-2xx response from Ollama.
        """
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": True},
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    # 400 almost always means an incompatible model type (e.g.
                    # embedding model used for chat).  Convert to a friendly
                    # ValueError so callers emit a readable SSE error event.
                    if exc.response.status_code == 400:
                        raise ValueError(
                            "This model does not support chat or text generation. "
                            "It may be an embedding model. "
                            "Please select a chat-capable model from the Playground."
                        ) from exc
                    raise
                try:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        # Extract the text token from the nested message object.
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        # Ollama signals the end of the stream with this flag.
                        if data.get("done", False):
                            break
                finally:
                    await response.aclose()

    # ------------------------------------------------------------------
    # Inference — raw/generate mode (single prompt, no chat history)
    # ------------------------------------------------------------------

    async def generate(self, model: str, prompt: str) -> AsyncIterator[str]:
        """
        Stream raw completion tokens using the Ollama ``/api/generate`` endpoint.

        Suitable for the Raw Console mode where no conversation history is needed.

        Args:
            model: Model tag, e.g. ``"mistral:latest"``.
            prompt: Raw text prompt to send.

        Yields:
            Individual text tokens from the ``response`` field.

        Raises:
            httpx.HTTPStatusError: On non-2xx response from Ollama.
        """
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": True},
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    # Same pattern as chat(): map 400 to a readable ValueError.
                    if exc.response.status_code == 400:
                        raise ValueError(
                            "This model does not support text generation. "
                            "It may be an embedding model. "
                            "Please select a generation-capable model."
                        ) from exc
                    raise
                try:
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done", False):
                            break
                finally:
                    await response.aclose()
