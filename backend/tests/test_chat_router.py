"""
Unit tests for routers/chat.py — /api/chat and /api/raw SSE endpoints.

OllamaClient is replaced via dependency_overrides — no live Ollama connection.
All mock clients implement list_models() so the chat endpoint's graceful model
discovery path is exercised correctly.

New tests (TestMetaAgentInterceptor) cover the consultation buffering logic:
  - consulting status event emitted when primary model outputs consult JSON
  - raw consultation JSON NOT leaked to the frontend as a token
  - final primary-model response streams after consultation
  - [DONE] marker is present after the full consultation flow
"""

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deps import get_ollama_client
from routers.chat import router

# ---------------------------------------------------------------------------
# Test application
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router, prefix="/api")


# ---------------------------------------------------------------------------
# Mock OllamaClient implementations
# ---------------------------------------------------------------------------


class MockChatClient:
    """
    Happy-path mock: chat() and generate() yield a small, predictable token
    sequence. list_models() returns an empty list so no system context
    is injected, keeping existing token-content assertions stable.
    """

    async def list_models(self):
        return []

    async def chat(self, model: str, messages: list):
        yield "Hello"
        yield ", "
        yield "world!"

    async def generate(self, model: str, prompt: str):
        yield "The answer"
        yield " is "
        yield "42."


class ErrorChatClient(MockChatClient):
    """Mock that raises a generic exception during the chat stream."""

    async def chat(self, model: str, messages: list):
        yield "Partial"
        raise Exception("Ollama process crashed")

    async def generate(self, model: str, prompt: str):
        raise Exception("Model not loaded")
        yield  # noqa: unreachable


class Http400ChatClient:
    """
    Mock that raises httpx.HTTPStatusError with status 400 to simulate Ollama
    rejecting a chat request for an incompatible model type (e.g. embeddings).
    """

    async def list_models(self):
        return []

    async def chat(self, model: str, messages: list):
        request = httpx.Request("POST", "http://localhost:11434/api/chat")
        response = httpx.Response(400, text="model does not support chat", request=request)
        raise httpx.HTTPStatusError("400 Bad Request", request=request, response=response)
        yield  # noqa: unreachable

    async def generate(self, model: str, prompt: str):
        request = httpx.Request("POST", "http://localhost:11434/api/generate")
        response = httpx.Response(400, text="model does not support generate", request=request)
        raise httpx.HTTPStatusError("400 Bad Request", request=request, response=response)
        yield  # noqa: unreachable


class ConsultingChatClient:
    """
    Mock that simulates the full consultation flow:
      - First chat() call: the primary model outputs a consult JSON block.
      - generate():        the expert model returns a specialist answer.
      - Second chat() call: the primary model streams its final user-facing reply.

    list_models() returns one entry so the system context lists a specialist.
    """

    def __init__(self):
        self._chat_call_count = 0

    async def list_models(self):
        # Expose a single specialist model so the system prompt lists it.
        return [{"name": "codellama:latest", "details": {}}]

    async def chat(self, model: str, messages: list):
        self._chat_call_count += 1
        if self._chat_call_count == 1:
            # Primary model decides to delegate — emits the strict consult JSON.
            yield '{"action": "consult", "target_model": "codellama:latest", "prompt": "Write fibonacci"}'
        else:
            # Re-triggered primary model produces the final user-facing answer.
            yield "Based on the expert: "
            yield "here is the fibonacci function."

    async def generate(self, model: str, prompt: str):
        # Expert model response (collected internally by the interceptor).
        yield "def fibonacci(n):"
        yield " return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)"


class MarkdownWrappedConsultClient:
    """
    Mock where the primary model wraps its consult JSON in a markdown code fence
    (```json ... ```) — the improved scanner must strip the fence and still detect it.
    """

    def __init__(self):
        self._chat_call_count = 0

    async def list_models(self):
        return [{"name": "codellama:latest", "details": {}}]

    async def chat(self, model: str, messages: list):
        self._chat_call_count += 1
        if self._chat_call_count == 1:
            # Model wraps the JSON in a markdown code fence (common hallucination).
            yield '```json\n{"action": "consult", "target_model": "codellama:latest", "prompt": "fibonacci"}\n```'
        else:
            yield "Here is the answer after consulting the expert."

    async def generate(self, model: str, prompt: str):
        yield "def fibonacci(n): ..."


class RecommendationClient:
    """Mock where the primary model recommends installing a missing expert."""
    async def list_models(self):
        return [{"name": "llama3.2:latest", "details": {}}]

    async def chat(self, model: str, messages: list):
        yield '{"action": "recommend_install", "target_model": "qwen2.5-coder:7b", "reason": "Better for coding"}'

    async def generate(self, model: str, prompt: str):
        pass


class RegexFallbackClient:
    """Mock where the primary model buries the action JSON inside conversational text."""
    def __init__(self):
        self._chat_call_count = 0

    async def list_models(self):
        return [{"name": "codellama:latest", "details": {}}]

    async def chat(self, model: str, messages: list):
        self._chat_call_count += 1
        if self._chat_call_count == 1:
            # Conversational filler before the JSON
            yield "Sure thing! I can help you with that. Let me just check my sources first.\n\n"
            yield "Here is the exact action I will take:\n"
            yield '{"action": "consult", "target_model": "codellama:latest", "prompt": "fibonacci"}\n\n'
            yield "Hopefully this helps!"
        else:
            yield "Here is the fibonacci code from the expert."

    async def generate(self, model: str, prompt: str):
        yield "def fibonacci(n): ..."



class HallucinatedActionClient:
    """
    Mock where the primary model emits a JSON block with an invented action name
    (e.g. "get_stock_price") — the interceptor must re-prompt it to answer directly.
    """

    def __init__(self):
        self._chat_call_count = 0

    async def list_models(self):
        return []

    async def chat(self, model: str, messages: list):
        self._chat_call_count += 1
        if self._chat_call_count == 1:
            # The model hallucinates a non-existent action.
            yield '{"action": "get_stock_price", "ticker": "AAPL"}'
        else:
            yield "Here is the direct answer."

    async def generate(self, model: str, prompt: str):
        yield ""  # never reached
        yield  # noqa: unreachable


# ---------------------------------------------------------------------------
# SSE parsing helpers
# ---------------------------------------------------------------------------


def _parse_token_events(body: str) -> list[str]:
    """
    Extract token strings from ``data: {"token": "..."}`` SSE lines.

    Args:
        body: Raw SSE response body.

    Returns:
        Ordered list of token strings emitted by the endpoint.
    """
    tokens = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                event = json.loads(line[6:])
                if "token" in event:
                    tokens.append(event["token"])
            except json.JSONDecodeError:
                pass
    return tokens


def _parse_status_events(body: str) -> list[dict]:
    """
    Extract all SSE events that carry a ``status`` key.

    Args:
        body: Raw SSE response body.

    Returns:
        List of parsed event dicts containing a ``status`` field.
    """
    events = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                event = json.loads(line[6:])
                if "status" in event:
                    events.append(event)
            except json.JSONDecodeError:
                pass
    return events


def _has_done_event(body: str) -> bool:
    """Return True if the SSE body contains the [DONE] terminator."""
    return "data: [DONE]" in body


def _has_error_event(body: str) -> bool:
    """Return True if any SSE event contains an 'error' key."""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            try:
                event = json.loads(line[6:])
                if "error" in event:
                    return True
            except json.JSONDecodeError:
                pass
    return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """Clear dependency overrides after every test to prevent state leakage."""
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/chat — agent chat mode
# ---------------------------------------------------------------------------


class TestChatEndpoint:
    """Tests for POST /api/chat (normal streaming, no consultation)."""

    _valid_payload = {
        "model": "llama3:latest",
        "messages": [{"role": "user", "content": "Hello"}],
    }

    def test_returns_sse_content_type(self):
        """Chat endpoint must return text/event-stream."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_streams_token_events(self):
        """Each token from chat() must appear as a data event with a 'token' key."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        tokens = _parse_token_events(response.text)
        assert tokens == ["Hello", ", ", "world!"]

    def test_ends_with_done_marker(self):
        """A successful stream must terminate with 'data: [DONE]'."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        assert _has_done_event(response.text), "Missing [DONE] terminator in SSE stream"

    def test_emits_error_event_on_exception(self):
        """Mid-stream exceptions must produce an error SSE event, not a 500."""
        app.dependency_overrides[get_ollama_client] = lambda: ErrorChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        assert response.status_code == 200
        assert _has_error_event(response.text), "Expected an error event in the SSE stream"

    def test_requires_model_field(self):
        """Omitting 'model' must cause HTTP 422."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post(
            "/api/chat", json={"messages": [{"role": "user", "content": "Hi"}]}
        )
        assert response.status_code == 422

    def test_requires_messages_field(self):
        """Omitting 'messages' must cause HTTP 422."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/chat", json={"model": "llama3:latest"})

        assert response.status_code == 422

    def test_assembled_text_is_correct(self):
        """Concatenating all tokens must reproduce the full expected response."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        tokens = _parse_token_events(response.text)
        assert "".join(tokens) == "Hello, world!"

    def test_emits_friendly_error_for_400(self):
        """
        When Ollama returns HTTP 400 (incompatible model type), the endpoint must
        emit an SSE error event rather than a 500 or unhandled exception.
        """
        app.dependency_overrides[get_ollama_client] = lambda: Http400ChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        assert response.status_code == 200, "HTTP layer must return 200; error is inside SSE"
        assert _has_error_event(response.text), "Expected an error SSE event for 400 rejection"

    def test_400_error_message_is_human_readable(self):
        """
        The error message emitted for a 400 must not expose httpx internals and
        must guide the user toward a resolution.
        """
        app.dependency_overrides[get_ollama_client] = lambda: Http400ChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        error_msg = ""
        for line in response.text.splitlines():
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    event = json.loads(line[6:])
                    if "error" in event:
                        error_msg = event["error"]
                        break
                except json.JSONDecodeError:
                    pass

        assert error_msg, "No error message found in SSE stream"
        assert "httpx" not in error_msg.lower(), "Error must not expose httpx internals"
        assert "HTTPStatusError" not in error_msg, "Error must not expose exception class names"
        assert any(
            kw in error_msg.lower() for kw in ("embedding", "chat", "model", "generation")
        ), f"Error message does not guide the user: '{error_msg}'"


# ---------------------------------------------------------------------------
# POST /api/chat — meta-agent consultation flow
# ---------------------------------------------------------------------------


class TestMetaAgentInterceptor:
    """
    Tests for the consultation logic inside _meta_agent_interceptor().

    ConsultingChatClient drives the scenario:
      1st chat() call  → emits consult JSON (should be intercepted, NOT forwarded)
      generate()       → returns expert answer (internal, NOT forwarded)
      2nd chat() call  → returns the final user-facing answer (MUST be forwarded)
    """

    _valid_payload = {
        "model": "llama3:latest",
        "messages": [{"role": "user", "content": "Write me a fibonacci function in Python"}],
    }

    def test_consulting_status_event_is_emitted(self):
        """
        When the primary model outputs a consult block, the interceptor must emit
        a ``{"status": "consulting", "target": "<model>"}`` SSE event before
        delegating to the specialist.
        """
        app.dependency_overrides[get_ollama_client] = lambda: ConsultingChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        assert response.status_code == 200
        status_events = _parse_status_events(response.text)
        assert any(
            e.get("status") == "consulting" for e in status_events
        ), "Expected a 'consulting' status SSE event"

    def test_consult_json_is_not_leaked_as_token(self):
        """
        The raw JSON consultation block emitted by the primary model must NOT
        appear as a token in the SSE stream reaching the frontend.
        The user must never see ``{"action": "consult", ...}`` as chat content.
        """
        app.dependency_overrides[get_ollama_client] = lambda: ConsultingChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        tokens = _parse_token_events(response.text)
        full_text = "".join(tokens)
        assert '"action"' not in full_text, "Raw consult JSON key leaked as token to frontend"
        assert "consult" not in full_text, "Raw consult JSON value leaked as token to frontend"

    def test_final_response_streams_after_consultation(self):
        """
        After the expert consultation is complete, the re-triggered primary model's
        answer must be streamed as token events to the frontend.
        """
        app.dependency_overrides[get_ollama_client] = lambda: ConsultingChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        tokens = _parse_token_events(response.text)
        full_text = "".join(tokens)
        assert len(tokens) > 0, "No tokens received after consultation"
        # The second-call mock yields "Based on the expert: " + "here is the fibonacci function."
        assert "expert" in full_text.lower(), (
            f"Expected final answer tokens in stream, got: '{full_text}'"
        )

    def test_done_emitted_after_consultation(self):
        """
        The [DONE] SSE marker must be present at the end of the stream after
        a full consultation round-trip.
        """
        app.dependency_overrides[get_ollama_client] = lambda: ConsultingChatClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        assert _has_done_event(response.text), "Missing [DONE] terminator after consultation"

    def test_markdown_wrapped_json_is_intercepted(self):
        """
        If the primary model wraps the consult JSON in a markdown code fence
        (```json ... ```) the improved scanner must still detect and intercept it.
        Both the consulting status event and final tokens must appear; raw JSON must not.
        """
        app.dependency_overrides[get_ollama_client] = lambda: MarkdownWrappedConsultClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        # The consulting event must still be detected despite the code fence prefix.
        status_events = _parse_status_events(response.text)
        assert any(
            e.get("status") == "consulting" for e in status_events
        ), "Markdown-wrapped consult JSON was not intercepted"

        # Raw JSON must not leak to the frontend as a token.
        tokens = _parse_token_events(response.text)
        full_text = "".join(tokens)
        assert '"action"' not in full_text, "Markdown-wrapped consult JSON leaked to frontend text stream"

    def test_regex_fallback_extracts_buried_json(self):
        """
        If the primary model buries the JSON command deep inside conversational text,
        the interceptor must still extract it using the Regex fallback and execute it,
        while flushing the conversational text up to that point.
        """
        app.dependency_overrides[get_ollama_client] = lambda: RegexFallbackClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        status_events = _parse_status_events(response.text)
        assert any(
            e.get("status") == "consulting" for e in status_events
        ), "Regex fallback failed to extract buried JSON"

        tokens = _parse_token_events(response.text)
        full_text = "".join(tokens)
        assert "Sure thing! I can help" in full_text, "Pre-JSON conversational filler was lost"
        assert '"action"' not in full_text, "Buried JSON leaked to frontend text stream"
        assert '"target_model"' not in full_text, "Buried JSON leaked to frontend text stream"

    def test_recommend_install_stops_stream(self):
        """
        If the primary model outputs the recommend_install action, the backend must
        emit the recommendation SSE event and gracefully close the stream (DONE).
        """
        app.dependency_overrides[get_ollama_client] = lambda: RecommendationClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)
        
        status_events = _parse_status_events(response.text)
        status_types = [e.get("status") for e in status_events]
        assert "recommendation" in status_types, "recommend_install did not emit recommendation event"
        
        # Verify specific fields in the event
        recommendation_event = next(e for e in status_events if e.get("status") == "recommendation")
        assert recommendation_event.get("target_model") == "qwen2.5-coder:7b"
        assert recommendation_event.get("reason") == "Better for coding"

        # Ensure no raw JSON leaked into the tokens
        tokens = _parse_token_events(response.text)
        full_text = "".join(tokens)
        assert '"action"' not in full_text, "recommend_install JSON leaked to frontend text stream"

    def test_hallucinated_action_is_intercepted_and_reprompted(self):
        """
        When the primary model emits a JSON block with an invented action name
        (a hallucination) or invalid target, the interceptor must NOT leak the JSON
        to the user. Instead, it must internally re-prompt the primary model to
        answer directly in plain language.
        No 'consulting' status event should be emitted.
        """
        app.dependency_overrides[get_ollama_client] = lambda: HallucinatedActionClient()
        response = TestClient(app).post("/api/chat", json=self._valid_payload)

        assert response.status_code == 200
        # No consulting status event should appear.
        status_events = _parse_status_events(response.text)
        assert not any(
            e.get("status") == "consulting" for e in status_events
        ), "Hallucinated action incorrectly triggered a consulting event"

        # Raw JSON must not leak.
        tokens = _parse_token_events(response.text)
        full_text = "".join(tokens)
        assert '"action"' not in full_text, "Hallucinated JSON leaked to frontend text stream"
        
        # The re-prompted answer must appear.
        assert "direct answer" in full_text, "Primary model was not successfully re-prompted"

        # The stream must still complete cleanly.
        assert _has_done_event(response.text), "Missing [DONE] after hallucinated action"


# ---------------------------------------------------------------------------
# POST /api/raw — raw generate mode (no chat history)
# ---------------------------------------------------------------------------


class TestRawEndpoint:
    """Tests for POST /api/raw."""

    _valid_payload = {"model": "mistral:latest", "prompt": "What is 6 x 7?"}

    def test_returns_sse_content_type(self):
        """Raw endpoint must return text/event-stream."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/raw", json=self._valid_payload)

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_streams_token_events(self):
        """Each token from generate() must appear as an SSE data event."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/raw", json=self._valid_payload)

        tokens = _parse_token_events(response.text)
        assert tokens == ["The answer", " is ", "42."]

    def test_ends_with_done_marker(self):
        """A successful raw stream must terminate with 'data: [DONE]'."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/raw", json=self._valid_payload)

        assert _has_done_event(response.text)

    def test_emits_error_event_on_exception(self):
        """Errors from generate() must surface as SSE error events, not 500s."""
        app.dependency_overrides[get_ollama_client] = lambda: ErrorChatClient()
        response = TestClient(app).post("/api/raw", json=self._valid_payload)

        assert response.status_code == 200
        assert _has_error_event(response.text)

    def test_requires_model_field(self):
        """Missing 'model' must cause HTTP 422."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/raw", json={"prompt": "Hello"})

        assert response.status_code == 422

    def test_requires_prompt_field(self):
        """Missing 'prompt' must cause HTTP 422."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/raw", json={"model": "mistral:latest"})

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/chat — skip_routing mode (Human-in-the-Loop Continue path)
# ---------------------------------------------------------------------------


class TestSkipRoutingMode:
    """Tests for POST /api/chat with skip_routing=True."""

    _payload = {
        "model": "llama3:latest",
        "messages": [{"role": "user", "content": "Hello"}],
        "skip_routing": True,
    }

    def test_skip_routing_streams_tokens_directly(self):
        """skip_routing bypasses the interceptor and streams tokens via _token_stream."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        tokens = _parse_token_events(response.text)
        assert tokens == ["Hello", ", ", "world!"]

    def test_skip_routing_ends_with_done(self):
        """skip_routing stream must terminate with [DONE]."""
        app.dependency_overrides[get_ollama_client] = lambda: MockChatClient()
        response = TestClient(app).post("/api/chat", json=self._payload)
        assert _has_done_event(response.text)

    def test_skip_routing_emits_error_on_http_400(self):
        """HTTP 400 in skip_routing path must emit friendly SSE error event."""
        app.dependency_overrides[get_ollama_client] = lambda: Http400ChatClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_error_event(response.text)

    def test_skip_routing_emits_error_on_http_non400(self):
        """HTTP 503 in skip_routing path must emit a generic SSE error event."""

        class Http503ChatClient:
            async def list_models(self):
                return []

            async def chat(self, model, messages):
                request = httpx.Request("POST", "http://localhost:11434/api/chat")
                response = httpx.Response(503, text="Service unavailable", request=request)
                raise httpx.HTTPStatusError("503", request=request, response=response)
                yield

        app.dependency_overrides[get_ollama_client] = lambda: Http503ChatClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_error_event(response.text)

    def test_skip_routing_emits_error_on_generic_exception(self):
        """Generic exceptions in skip_routing path must emit SSE error event."""
        app.dependency_overrides[get_ollama_client] = lambda: ErrorChatClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_error_event(response.text)


# ---------------------------------------------------------------------------
# Meta-agent edge cases — additional branch coverage
# ---------------------------------------------------------------------------


class TestMetaAgentEdgeCases:
    """Additional branch coverage for _meta_agent_interceptor."""

    _payload = {
        "model": "llama3:latest",
        "messages": [{"role": "user", "content": "Hello"}],
    }

    def test_list_models_exception_falls_back_to_empty(self):
        """If list_models() raises, the endpoint must still work with no system context."""

        class FailingListClient(MockChatClient):
            async def list_models(self):
                raise Exception("Ollama offline")

        app.dependency_overrides[get_ollama_client] = lambda: FailingListClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_done_event(response.text)

    def test_plain_text_no_brace_flushed(self):
        """Tokens with no '{' must be flushed immediately as text tokens."""

        class PlainTextClient(MockChatClient):
            async def chat(self, model, messages):
                yield "Hello world no braces here"

        app.dependency_overrides[get_ollama_client] = lambda: PlainTextClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        tokens = _parse_token_events(response.text)
        assert "Hello world no braces here" in "".join(tokens)

    def test_brace_not_followed_by_quote_flushed_as_text(self):
        """A '{' followed by a non-'"' character must be flushed as plain text."""

        class BraceNoQuoteClient(MockChatClient):
            async def chat(self, model, messages):
                yield "{ not a json key }"

        app.dependency_overrides[get_ollama_client] = lambda: BraceNoQuoteClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        tokens = _parse_token_events(response.text)
        assert "{" in "".join(tokens)

    def test_normal_json_without_action_flushed_as_token(self):
        """A JSON object without an 'action' key must be flushed as a text token."""

        class NoActionJsonClient(MockChatClient):
            async def chat(self, model, messages):
                yield '{"result": 42}'

        app.dependency_overrides[get_ollama_client] = lambda: NoActionJsonClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        tokens = _parse_token_events(response.text)
        full = "".join(tokens)
        assert '"result"' in full

    def test_buffer_overflow_flushed_as_text(self):
        """If the buffer grows beyond _CONSULT_BUFFER_LIMIT without a valid JSON object,
        it must be flushed as plain text tokens."""

        class OverflowClient(MockChatClient):
            async def chat(self, model, messages):
                # Start a JSON-looking sequence but never close it.
                yield '{"action": "consult"' + " " * 2_100  # exceeds 2000 char limit

        app.dependency_overrides[get_ollama_client] = lambda: OverflowClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_done_event(response.text)

    def test_consult_missing_target_model(self):
        """consult JSON missing target_model must re-prompt the primary model."""

        class MissingTargetClient:
            def __init__(self):
                self._call = 0

            async def list_models(self):
                return [{"name": "expert:latest", "details": {}}]

            async def chat(self, model, messages):
                self._call += 1
                if self._call == 1:
                    yield '{"action": "consult", "prompt": "no target here"}'
                else:
                    yield "Direct answer."

            async def generate(self, model, prompt):
                yield "Expert text"
                return
                yield

        app.dependency_overrides[get_ollama_client] = lambda: MissingTargetClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        tokens = _parse_token_events(response.text)
        assert "Direct answer." in "".join(tokens)

    def test_consult_invalid_target_model_triggers_recommendation(self):
        """consult with a target not in installed list emits a recommendation event."""

        class InvalidTargetClient:
            async def list_models(self):
                return [{"name": "installed-model:latest", "details": {}}]

            async def chat(self, model, messages):
                yield '{"action": "consult", "target_model": "ghost-model:7b", "prompt": "help"}'

            async def generate(self, model, prompt):
                return
                yield

        app.dependency_overrides[get_ollama_client] = lambda: InvalidTargetClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        status_events = _parse_status_events(response.text)
        assert any(e.get("status") == "recommendation" for e in status_events)
        assert _has_done_event(response.text)

    def test_consult_expert_value_error(self):
        """If the expert model raises ValueError, an SSE error event must be emitted."""

        class ExpertValueErrorClient:
            def __init__(self):
                self._call = 0

            async def list_models(self):
                return [{"name": "codellama:latest", "details": {}}]

            async def chat(self, model, messages):
                self._call += 1
                if self._call == 1:
                    yield '{"action": "consult", "target_model": "codellama:latest", "prompt": "help"}'

            async def generate(self, model, prompt):
                raise ValueError("Model does not support generation")
                yield

        app.dependency_overrides[get_ollama_client] = lambda: ExpertValueErrorClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert _has_error_event(response.text)
        assert _has_done_event(response.text)

    def test_consult_expert_generic_error(self):
        """If the expert model raises a generic Exception, an SSE error event must be emitted."""

        class ExpertGenericErrorClient:
            def __init__(self):
                self._call = 0

            async def list_models(self):
                return [{"name": "codellama:latest", "details": {}}]

            async def chat(self, model, messages):
                self._call += 1
                if self._call == 1:
                    yield '{"action": "consult", "target_model": "codellama:latest", "prompt": "help"}'

            async def generate(self, model, prompt):
                raise Exception("Specialist process crashed")
                yield

        app.dependency_overrides[get_ollama_client] = lambda: ExpertGenericErrorClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert _has_error_event(response.text)
        assert _has_done_event(response.text)

    def test_recommend_install_without_target_model(self):
        """recommend_install with no target_model key must emit an error event."""

        class NoTargetRecommendClient:
            async def list_models(self):
                return []

            async def chat(self, model, messages):
                yield '{"action": "recommend_install", "reason": "Need a better model"}'

            async def generate(self, model, prompt):
                return
                yield

        app.dependency_overrides[get_ollama_client] = lambda: NoTargetRecommendClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert _has_error_event(response.text)
        assert _has_done_event(response.text)

    def test_http_400_in_meta_agent(self):
        """HTTP 400 from Ollama's chat endpoint during meta-agent streaming emits friendly error."""

        class MetaHttp400Client:
            async def list_models(self):
                return []

            async def chat(self, model, messages):
                request = httpx.Request("POST", "http://localhost:11434/api/chat")
                response = httpx.Response(400, text="Bad", request=request)
                raise httpx.HTTPStatusError("400", request=request, response=response)
                yield

        app.dependency_overrides[get_ollama_client] = lambda: MetaHttp400Client()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_error_event(response.text)

    def test_http_non400_in_meta_agent(self):
        """HTTP 503 from Ollama's chat during meta-agent must emit a generic error event."""

        class MetaHttp503Client:
            async def list_models(self):
                return []

            async def chat(self, model, messages):
                request = httpx.Request("POST", "http://localhost:11434/api/chat")
                response = httpx.Response(503, text="Unavailable", request=request)
                raise httpx.HTTPStatusError("503", request=request, response=response)
                yield

        app.dependency_overrides[get_ollama_client] = lambda: MetaHttp503Client()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_error_event(response.text)

    def test_generic_exception_in_meta_agent(self):
        """Generic exception from Ollama's chat during meta-agent must emit an error event."""

        class MetaGenericErrorClient:
            async def list_models(self):
                return []

            async def chat(self, model, messages):
                raise Exception("Unexpected process crash")
                yield

        app.dependency_overrides[get_ollama_client] = lambda: MetaGenericErrorClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_error_event(response.text)

    def test_stream_reprompt_no_user_message_appends_error(self):
        """If the last message is not a user message, re-prompt appends error as new user msg."""

        class NoLastUserMsgClient:
            def __init__(self):
                self._call = 0

            async def list_models(self):
                return []

            async def chat(self, model, messages):
                self._call += 1
                if self._call == 1:
                    yield '{"action": "get_weather", "city": "London"}'
                else:
                    yield "Here is the answer."

            async def generate(self, model, prompt):
                return
                yield

        # Send a conversation where the last message is assistant (not user)
        app.dependency_overrides[get_ollama_client] = lambda: NoLastUserMsgClient()
        response = TestClient(app).post("/api/chat", json={
            "model": "llama3:latest",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        })

        assert response.status_code == 200
        assert _has_done_event(response.text)

    def test_residual_buffer_flushed_at_end(self):
        """Residual buffer content that never forms a complete JSON block is flushed at stream end."""

        class IncompleteJsonClient(MockChatClient):
            async def chat(self, model, messages):
                # Starts like JSON but never closes -- short enough to not trigger overflow
                yield '{"unfinished": '

        app.dependency_overrides[get_ollama_client] = lambda: IncompleteJsonClient()
        response = TestClient(app).post("/api/chat", json=self._payload)

        assert response.status_code == 200
        assert _has_done_event(response.text)
        tokens = _parse_token_events(response.text)
        assert '{' in "".join(tokens)

    def test_inject_system_context_skips_when_system_msg_present(self):
        """If messages already start with a system role, the injected prompt must be skipped."""
        from routers.chat import _inject_system_context

        existing_system = [{"role": "system", "content": "My custom context"}, {"role": "user", "content": "Hi"}]
        result = _inject_system_context(existing_system, "Generated context")
        # Must return the original list unchanged
        assert result[0]["content"] == "My custom context"
        assert len(result) == 2

    def test_inject_system_context_skips_when_no_prompt(self):
        """An empty system_prompt must return the messages list unchanged."""
        from routers.chat import _inject_system_context

        messages = [{"role": "user", "content": "Hello"}]
        result = _inject_system_context(messages, "")
        assert result is messages

    def test_build_system_context_with_no_models(self):
        """_build_system_context with empty list must include 'No other models' line."""
        from routers.chat import _build_system_context

        result = _build_system_context([])
        assert "No other models" in result

    def test_build_system_context_with_models(self):
        """_build_system_context with model list must include model names."""
        from routers.chat import _build_system_context

        models = [{"name": "codellama:latest", "details": {"family": "llama"}}]
        result = _build_system_context(models)
        assert "codellama:latest" in result

    def test_raw_endpoint_http_non400_emits_generic_error(self):
        """HTTP 503 in /api/raw must emit a generic error message (not the 400 one)."""

        class Http503GenerateClient(MockChatClient):
            async def generate(self, model, prompt):
                request = httpx.Request("POST", "http://localhost:11434/api/generate")
                response = httpx.Response(503, text="Service Down", request=request)
                raise httpx.HTTPStatusError("503", request=request, response=response)
                yield

        app.dependency_overrides[get_ollama_client] = lambda: Http503GenerateClient()
        response = TestClient(app).post("/api/raw", json={"model": "mistral:latest", "prompt": "test"})

        assert response.status_code == 200
        assert _has_error_event(response.text)
        # The error message should NOT say embedding
        for line in response.text.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    event = json.loads(line[6:])
                    if "error" in event:
                        assert "HTTP 503" in event["error"]
                except Exception:
                    pass
