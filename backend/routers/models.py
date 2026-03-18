"""
Model management router — list, pull, update, and delete Ollama models.

All three streaming endpoints (pull, update) implement the following
disconnection-safety pattern:
  1. ``await request.is_disconnected()`` is polled before each ``yield``.
  2. ``asyncio.CancelledError`` is caught — raised by FastAPI/Starlette when
     the HTTP connection is torn down mid-stream.
  3. Unexpected exceptions are caught and emitted as ``{"error": ...}`` SSE
     events instead of crashing the server.

This ensures memory leaks and zombie generator objects are avoided regardless
of how (or when) the client disconnects.
"""

import asyncio
import json
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from available_models import AVAILABLE_MODELS
from deps import get_ollama_client
from model_category import categorize_model
from ollama_client import OllamaClient

router = APIRouter()

# SSE response headers that improve compatibility with proxies and browsers.
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Disables nginx/proxy response buffering so events reach the browser live.
    "X-Accel-Buffering": "no",
}


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class ModelNameRequest(BaseModel):
    """Request body for pull and update operations."""

    name: str


# ---------------------------------------------------------------------------
# Helper — shared SSE pull generator
# ---------------------------------------------------------------------------


async def _pull_event_stream(
    name: str,
    request: Request,
    ollama: OllamaClient,
) -> AsyncGenerator[str, None]:
    """
    Async generator that wraps OllamaClient.pull_model() and yields
    properly formatted SSE events.

    Disconnection safety:
      - Polls ``request.is_disconnected()`` before each event yield.
      - Catches ``asyncio.CancelledError`` (FastAPI cancels the generator
        when the client closes the connection).
      - Catches all other exceptions and emits them as error events so
        the client always receives a terminal signal rather than a hanging
        connection.

    Args:
        name: Ollama model tag to pull.
        request: The active FastAPI request object used for disconnection probing.
        ollama: OllamaClient instance (injected via dependency).

    Yields:
        SSE-formatted strings: ``data: {json}\\n\\n``
    """
    try:
        async for chunk in ollama.pull_model(name):
            # Bail out early if the browser tab was closed or request was cancelled.
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(chunk)}\n\n"
    except asyncio.CancelledError:
        # FastAPI raised this when it detected the client went away.
        # Exiting silently is the correct behaviour — no event to emit.
        pass
    except Exception as exc:
        # Emit a structured error event instead of letting the generator crash.
        yield f"data: {json.dumps({'status': 'error', 'error': str(exc)})}\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/models",
    summary="List installed models",
    description="Returns the list of locally installed Ollama models.",
)
async def list_models(ollama: OllamaClient = Depends(get_ollama_client)) -> dict:
    """
    Fetch the list of locally installed models from Ollama.

    Returns:
        dict: ``{"models": [model, ...]}``

    Raises:
        HTTPException 503: If Ollama is unreachable.
    """
    try:
        models = await ollama.list_models()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not reach Ollama: {exc}",
        )

    # Enrich each model with a capability category so the frontend can render
    # capability pills without additional API calls.
    for m in models:
        m["category"] = categorize_model(
            name=m.get("name", ""),
            family=m.get("details", {}).get("family"),
            tags=[],  # installed models have no catalogue tags
        )

    return {"models": models}


@router.get(
    "/models/available",
    summary="List available models for download",
    description=(
        "Returns the curated catalogue of popular models from the Ollama registry. "
        "This is a static list — no external network request is made."
    ),
)
async def list_available_models() -> dict:
    """
    Return the curated catalogue of downloadable models.

    Returns:
        dict: ``{"models": [model_descriptor, ...]}``
    """
    return {"models": AVAILABLE_MODELS}


@router.post(
    "/models/pull",
    summary="Pull (install) a model",
    description=(
        "Streams Ollama's pull progress as Server-Sent Events. "
        "Each event is a JSON object mirroring the Ollama pull response "
        "(e.g. ``{\\\"status\\\": \\\"downloading\\\", \\\"completed\\\": 100, \\\"total\\\": 1000}``)."
    ),
)
async def pull_model(
    body: ModelNameRequest,
    request: Request,
    ollama: OllamaClient = Depends(get_ollama_client),
) -> StreamingResponse:
    """
    Pull a model from the Ollama registry and stream download progress.

    Args:
        body: JSON body containing the model ``name``.
        request: Active request object for disconnection detection.
        ollama: Injected OllamaClient.

    Returns:
        StreamingResponse: SSE stream of progress events.
    """
    return StreamingResponse(
        _pull_event_stream(body.name, request, ollama),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post(
    "/models/update",
    summary="Update an installed model",
    description=(
        "Re-pulls the model tag to fetch the latest version. "
        "Internally identical to a pull — Ollama checks the registry digest "
        "and only downloads changed layers. Streams progress as SSE events."
    ),
)
async def update_model(
    body: ModelNameRequest,
    request: Request,
    ollama: OllamaClient = Depends(get_ollama_client),
) -> StreamingResponse:
    """
    Update a model by re-pulling its tag.

    Ollama is digest-aware: if the model is already up-to-date, the pull
    completes immediately with ``{\"status\": \"success\"}``.

    Args:
        body: JSON body containing the model ``name``.
        request: Active request object for disconnection detection.
        ollama: Injected OllamaClient.

    Returns:
        StreamingResponse: SSE stream of progress events.
    """
    # Update is semantically a pull — reuse the same generator.
    return StreamingResponse(
        _pull_event_stream(body.name, request, ollama),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.delete(
    "/models/{name}",
    summary="Delete an installed model",
    description=(
        "Removes the specified model from the local Ollama store. "
        "Model names may include a tag, e.g. ``llama3:latest``."
    ),
)
async def delete_model(
    name: str,
    ollama: OllamaClient = Depends(get_ollama_client),
) -> dict:
    """
    Delete a locally installed model.

    Args:
        name: URL path segment identifying the model, e.g. ``llama3:latest``.
        ollama: Injected OllamaClient.

    Returns:
        dict: ``{"status": "deleted", "name": name}``

    Raises:
        HTTPException: Relays the HTTP status code returned by Ollama.
    """
    try:
        await ollama.delete_model(name)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Ollama error: {exc.response.text}",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not reach Ollama: {exc}")
    return {"status": "deleted", "name": name}
