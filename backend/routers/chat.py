"""
Chat and raw inference router — streaming SSE endpoints.

/api/chat implements a Meta-Agent Interceptor:
  - A hidden system message is injected listing all installed specialist models.
  - Incoming tokens are buffered to detect whether the primary model emitted a
    JSON consultation block instead of plain text.
  - On detection the interceptor transparently:
      1. Emits a {"status": "consulting", "target": "<model>"} SSE event.
      2. Collects the expert model's full response via OllamaClient.generate().
      3. Appends that answer as a system message and re-triggers the primary model.
      4. Streams the primary model's final reply to the client.

/api/raw is unchanged and uses the simple _token_stream() helper.

SSE event formats:
  token    -> data: {"token": "<text>"}\\n\\n
  status   -> data: {"status": "consulting", "target": "<model>"}\\n\\n
  error    -> data: {"error": "<message>"}\\n\\n
  terminal -> data: [DONE]\\n\\n
"""

import asyncio
import json
import re
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from deps import get_ollama_client
from model_category import categorize_model
from ollama_client import OllamaClient

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# JSON prefix emitted by the primary model when it wants to consult a specialist.
_CONSULT_PREFIX = '{"action"'

# Safety valve: if the buffer grows beyond this many characters without resolving
# to a valid consult JSON block, treat the content as plain text and flush it.
_CONSULT_BUFFER_LIMIT = 2_000

# The only action value the orchestrator is permitted to emit.
_VALID_ACTIONS: frozenset[str] = frozenset({"consult", "recommend_install"})


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Request body for the agent chat endpoint."""

    model: str
    messages: list[dict]
    skip_routing: bool = False


class RawRequest(BaseModel):
    """Request body for the raw generation endpoint."""

    model: str
    prompt: str


# ---------------------------------------------------------------------------
# System context helpers  (Single Responsibility — context building only)
# ---------------------------------------------------------------------------

def _build_system_context(models: list[dict]) -> str:
    """
    Build the hardened orchestrator system prompt.

    The prompt is deliberately strict:
      - Lists only real installed models (no hallucinations possible).
      - Specifies the ONE permitted action: ``consult``.
      - Provides explicit CORRECT and WRONG format examples.
      - Forbids markdown wrappers, filler text, and invented model names.

    Args:
        models: Installed model dicts from OllamaClient.list_models().

    Returns:
        Multi-line orchestrator system prompt string.
    """
    if models:
        lines = []
        valid_names = []
        for m in models:
            name = m.get("name", "")
            cat = categorize_model(
                name=name,
                family=m.get("details", {}).get("family"),
                tags=[],
            )
            lines.append(f"  - {name} (category: {cat})")
            valid_names.append(name)
        model_list = "\n".join(lines)
        names_list = ", ".join(f'"{n}"' for n in valid_names)
    else:
        model_list = "  - No other models currently installed."
        names_list = "(none)"

    return (
        "You are the primary orchestrator AI inside a local Ollama dashboard.\n"
        "Your ONLY permitted behaviours are:\n"
        "  1. Answer the user directly in plain language.\n"
        "  2. Consult a specialist model by emitting a strict JSON command.\n"
        "  3. Recommend a missing ideal model by emitting a strict JSON command.\n\n"
        "INSTALLED SPECIALIST MODELS (use ONLY these exact names):\n"
        f"{model_list}\n"
        f"Valid target_model values: {names_list}\n\n"
        "━━━ IDEAL INDUSTRY STANDARDS ━━━\n"
        "If a specific highly technical task is requested, these are the ideal experts:\n"
        "  - Coding / Programming -> qwen2.5-coder:7b\n"
        "  - Complex Logic / Math -> phi3:latest\n"
        "  - Heavy Reasoning -> deepseek-r1\n"
        "  - Finance / Real-time -> mistral:latest or llama3-70b\n\n"
        "━━━ CONSULTATION & RECOMMENDATION RULES (read carefully) ━━━\n"
        "If you determine that another installed model is significantly better suited "
        "for the user's request, you may delegate to it. "
        "To delegate, output ONLY this JSON object — nothing else:\n"
        '{"action": "consult", "target_model": "<exact name from installed list>", '
        '"prompt": "<concise expert prompt>"}\n\n'
        "If the task requires a specialist and the ideal standard model is NOT in "
        "the installed list, output ONLY this JSON object — nothing else:\n"
        '{"action": "recommend_install", "target_model": "<ideal_model_name>", '
        '"reason": "<brief 1-sentence explanation why it is needed>"}\n\n'
        "STRICT CONSTRAINTS — violating any of these will break the system:\n"
        "  ✗ DO NOT explain your limitations.\n"
        "  ✗ DO NOT ask the user for permission.\n"
        "  ✗ DO NOT narrate your actions.\n"
        "  ✗ Do NOT write any text before or after the JSON object.\n"
        '  ✗ Do NOT wrap JSON in markdown (no ```json or ``` fences).\n'
        "  ✗ Do NOT invent model names not in the list above.\n"
        '  ✗ Do NOT use any action value other than "consult" or "recommend_install".\n'
        "  ✗ Do NOT hallucinate capabilities like get_stock_price, browse_web, etc.\n\n"
        "━━━ FEW-SHOT EXAMPLES ━━━\n"
        "Example 1 (Consulting an installed expert):\n"
        'User: "Translate this to French"\n'
        'You: {"action": "consult", "target_model": "gemma:2b", "prompt": "Translate this to French..."}\n\n'
        "Example 2 (Recommending an installation):\n"
        'User: "Write a complex Python script"\n'
        'You: {"action": "recommend_install", "target_model": "qwen2.5-coder:7b", "reason": "Advanced coding tasks require a specialized model."}\n\n'
        "If none of the listed models are relevant, answer directly yourself in plain language."
    )


def _inject_system_context(messages: list[dict], system_prompt: str) -> list[dict]:
    """
    Prepend a system message to the conversation without mutating the original list.

    If ``messages`` already begins with a system-role entry the existing one is
    preserved and the generated prompt is NOT injected, to respect explicit caller
    overrides.

    Args:
        messages:      Original conversation history.
        system_prompt: Orchestrator context built by _build_system_context().

    Returns:
        New list with system message at index 0 (or the original list unchanged).
    """
    if not system_prompt:
        return messages
    if messages and messages[0].get("role") == "system":
        return messages
    return [{"role": "system", "content": system_prompt}] + list(messages)


# ---------------------------------------------------------------------------
# Raw SSE generator  (used by /api/raw only — unchanged)
# ---------------------------------------------------------------------------


async def _token_stream(
    token_source: AsyncGenerator[str, None],
    request: Request,
) -> AsyncGenerator[str, None]:
    """
    Wrap any async token generator and format its output as SSE events.

    Args:
        token_source: Async generator that yields string tokens.
        request:      Active FastAPI request for disconnection probing.

    Yields:
        SSE-formatted strings.
    """
    try:
        async for token in token_source:
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps({'token': token})}\n\n"
    except asyncio.CancelledError:
        pass
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        msg = (
            "This model does not support chat or generation. "
            "It may be an embedding model. "
            "Please select a chat-capable model from the Playground."
            if status == 400
            else f"Ollama returned HTTP {status}. Please check the server and try again."
        )
        yield f"data: {json.dumps({'error': msg})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"
    else:
        yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Meta-Agent Interceptor  (used by /api/chat)
# ---------------------------------------------------------------------------


async def _stream_reprompt(
    ollama: OllamaClient,
    model: str,
    messages: list[dict],
    err_msg: str,
    request: Request,
) -> AsyncGenerator[str, None]:
    """Internal helper to force the primary model to re-generate if it hallucinates."""
    extended = list(messages)
    if extended and extended[-1].get("role") == "user":
        extended[-1] = {
            "role": "user",
            "content": extended[-1]["content"] + f"\n\n[{err_msg}]",
        }
    else:
        extended.append({"role": "user", "content": f"[{err_msg}]"})

    async for final_token in ollama.chat(model, extended):
        if await request.is_disconnected():
            return
        yield f"data: {json.dumps({'token': final_token})}\n\n"
    yield "data: [DONE]\n\n"


async def _meta_agent_interceptor(
    model: str,
    messages: list[dict],
    ollama: OllamaClient,
    request: Request,
    valid_model_names: frozenset[str] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream chat tokens while transparently intercepting specialist consultations.

    Dynamic interception algorithm
    -----------------------------
    1. Stream everything before the first `{`.
    2. If `{` is followed by `"`, buffer it as a JSON candidate.
    3. If `}` appears, attempt `json.loads`.
    4. If buffer > 200 chars and json.loads failed from start, rely on REGEX to extract hallucinated JSON.
    5. If valid consult JSON, execute delegation.
    6. If action == "recommend_install", emit status event and stop cleanly.
    """
    buffer = ""
    streaming_text = True

    try:
        async for chunk in ollama.chat(model, messages):
            if await request.is_disconnected():
                return
            
            buffer += chunk

            if streaming_text:
                brace_idx = buffer.find("{")

                if brace_idx == -1:
                    # No '{' at all. Stream the whole buffer safely.
                    yield f"data: {json.dumps({'token': buffer})}\n\n"
                    buffer = ""
                    continue

                # Found a '{'. Stream everything BEFORE it immediately.
                if brace_idx > 0:
                    yield f"data: {json.dumps({'token': buffer[:brace_idx]})}\n\n"
                    buffer = buffer[brace_idx:]  # Now buffer starts exactly with '{'

                # Inspect the character after '{'
                after_brace = buffer[1:].lstrip()
                if not after_brace:
                    # Not enough info yet, wait for next token.
                    streaming_text = False
                    continue

                if not after_brace.startswith('"'):
                    # Definitely not a standard JSON object key. Flush as text.
                    yield f"data: {json.dumps({'token': buffer})}\n\n"
                    buffer = ""
                    continue

                # Switch to JSON accumulation mode.
                streaming_text = False

            # --- JSON ACCUMULATION MODE ---
            after_brace = buffer[1:].lstrip()
            if after_brace and not after_brace.startswith('"'):
                # Not a standard JSON string key right after the brace.
                pass  # We keep buffering anyway, Regex might catch it later if it's deeply buried.

            # Try to parse the buffer if a closing brace arrived.
            if "}" in buffer:
                # 1. Attempt raw load from start of buffer:
                clean_buf = buffer.rstrip().rstrip("`").rstrip()
                data = None
                
                try:
                    data = json.loads(clean_buf)
                except json.JSONDecodeError:
                    # 2. Regex fallback to extract JSON embedded with trailing text or markdown
                    import re
                    match = re.search(r'\{.*\}', buffer, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(0))
                        except json.JSONDecodeError:
                            pass # Keep buffering until absolute limit
                
                if data is not None:
                    action = data.get("action")

                    if action == "consult":
                        target_model = data.get("target_model")
                        expert_prompt = data.get("prompt")

                        if not target_model or not expert_prompt:
                            err = "System Error: Missing 'target_model' or 'prompt' keys in JSON. Answer directly in plain language."
                            async for token in _stream_reprompt(ollama, model, messages, err, request):
                                yield token
                            return

                        if valid_model_names is not None and target_model not in valid_model_names:
                            reason_msg = f"The primary model requested a consultation with {target_model}, but it is not currently installed."
                            yield f"data: {json.dumps({'status': 'recommendation', 'target_model': target_model, 'reason': reason_msg})}\n\n"
                            # Stop stream so Human-in-the-Loop input UI can appear
                            yield "data: [DONE]\n\n"
                            return

                        # Valid explicit consultation!
                        yield f"data: {json.dumps({'status': 'consulting', 'target': target_model})}\n\n"

                        try:
                            expert_parts = []
                            async for e_chunk in ollama.generate(target_model, expert_prompt):
                                if await request.is_disconnected():
                                    return
                                expert_parts.append(e_chunk)
                            expert_text = "".join(expert_parts)
                            
                            ok_msg = f"System Note: Consultation with {target_model} complete. Expert response:\n\n{expert_text}\n\nNow provide the final synthesized answer in plain language."
                            async for token in _stream_reprompt(ollama, model, messages, ok_msg, request):
                                yield token
                            return

                        except ValueError as e:
                            yield f"data: {json.dumps({'error': str(e)})}\n\n"
                            yield "data: [DONE]\n\n"
                            return
                        except Exception as e:
                            yield f"data: {json.dumps({'error': f'Specialist error: {str(e)}'})}\n\n"
                            yield "data: [DONE]\n\n"
                            return

                    elif action == "recommend_install":
                        target_model = data.get("target_model")
                        reason = data.get("reason", "Highly recommended for this specific technical request.")
                        if target_model:
                            yield f"data: {json.dumps({'status': 'recommendation', 'target_model': target_model, 'reason': reason})}\n\n"
                        else:
                            yield f"data: {json.dumps({'error': 'System Error: recommendation missed target_model.'})}\n\n"
                        
                        # Stop stream completely to wait for Human-in-the-Loop input.
                        yield "data: [DONE]\n\n"
                        return

                    elif isinstance(action, str):
                        # Hallucinated action (e.g. "get_stock_price")
                        err = f"System Error: action '{action}' is forbidden. Answer directly in plain language."
                        async for token in _stream_reprompt(ollama, model, messages, err, request):
                            yield token
                        return
                    else:
                        # Normal JSON dictionary the user might have asked for. Flush as text.
                        yield f"data: {json.dumps({'token': buffer})}\n\n"
                        buffer = ""
                        streaming_text = True
                        continue

            if len(buffer) > _CONSULT_BUFFER_LIMIT:
                # Exceeded absolute safety limit. Flush as text.
                yield f"data: {json.dumps({'token': buffer})}\n\n"
                buffer = ""
                streaming_text = True

    except asyncio.CancelledError:
        return
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        msg = (
            "This model does not support chat or generation. "
            "It may be an embedding model. "
            "Please select a chat-capable model from the Playground."
            if status == 400
            else f"Ollama returned HTTP {status}. Please check the server and try again."
        )
        yield f"data: {json.dumps({'error': msg})}\n\n"
        return
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        return

    # Flush any residual buffer (e.g. partial JSON that never completed).
    if buffer:
        yield f"data: {json.dumps({'token': buffer})}\n\n"

    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/chat",
    summary="Agent chat — streaming with meta-agent interception",
    description=(
        "Sends a conversation to the selected model and streams the response as SSE. "
        "A hidden system context is injected so the primary model can transparently "
        "delegate to specialist local models. Each event: "
        "``data: {\\\"token\\\": \\\"...\\\"}\\n\\n``. "
        "A 'consulting' status event may appear when a secondary model is queried. "
        "Terminates with ``data: [DONE]`` on success."
    ),
)
async def chat(
    body: ChatRequest,
    request: Request,
    ollama: OllamaClient = Depends(get_ollama_client),
) -> StreamingResponse:
    """
    Stream a chat response with meta-agent interception.

    Fetches installed models to build the orchestrator system prompt, injects it
    as a hidden system message, then delegates to _meta_agent_interceptor().

    Args:
        body:    Model name and conversation history.
        request: Active request for disconnection detection.
        ollama:  Injected OllamaClient.

    Returns:
        StreamingResponse: SSE stream of token, status, and control events.
    """
    # Fetch installed models to populate the orchestrator context.
    # A failure here is non-fatal — the endpoint degrades to normal chat.
    try:
        installed_models = await ollama.list_models()
    except Exception:
        installed_models = []

    # Only non-embedding models can generate text responses.
    # Exclude embedding models from the consultable list so the primary model
    # never attempts to delegate to a model that would reject a generate call.
    consultable_models = [
        m for m in installed_models
        if categorize_model(
            name=m.get("name", ""),
            family=m.get("details", {}).get("family"),
            tags=[],
        ) != "embedding"
    ]

    # Build the frozenset of valid consultable model names for hallucination rejection.
    # Uses consultable_models (not installed_models) so embedding targets are refused.
    valid_model_names: frozenset[str] = frozenset(
        m.get("name", "") for m in consultable_models if m.get("name")
    )

    # System context lists only consultable models so the primary model
    # cannot be tricked into delegating to an embedding-only specialist.
    system_prompt = _build_system_context(consultable_models)
    enriched_messages = _inject_system_context(body.messages, system_prompt)

    # 3. Stream routing logic
    if body.skip_routing:
        # User opted to bypass orchestrator routing (Human-in-the-Loop "Continue" path)
        token_source = _token_stream(ollama.chat(body.model, enriched_messages), request)
        return StreamingResponse(
            token_source,
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
    else:
        # Full Meta-Agent Interceptor mode (default)
        token_source = _meta_agent_interceptor(
            model=body.model,
            messages=enriched_messages,
            ollama=ollama,
            request=request,
            valid_model_names=valid_model_names,
        )
        return StreamingResponse(
            token_source,
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )


@router.post(
    "/raw",
    summary="Raw generation — streaming",
    description=(
        "Sends a raw prompt to the selected model (no chat history) and streams "
        "the completion as Server-Sent Events. Each event: "
        "``data: {\\\"token\\\": \\\"...\\\"}\\n\\n``. Terminates with ``data: [DONE]``."
    ),
)
async def raw_generate(
    body: RawRequest,
    request: Request,
    ollama: OllamaClient = Depends(get_ollama_client),
) -> StreamingResponse:
    """
    Stream a raw completion token by token.

    Args:
        body:    Model name and raw prompt string.
        request: Active request for disconnection detection.
        ollama:  Injected OllamaClient.

    Returns:
        StreamingResponse: SSE stream of token events.
    """
    source = ollama.generate(body.model, body.prompt)
    return StreamingResponse(
        _token_stream(source, request),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
