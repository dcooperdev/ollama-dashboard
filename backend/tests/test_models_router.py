"""
Unit tests for routers/models.py.

OllamaClient is replaced via FastAPI's dependency_overrides mechanism —
no real Ollama calls are ever made, and tests are fully isolated.

SSE responses are read as plain text and parsed into event dicts so we can
assert on individual event payloads without a real SSE client.
"""

import json
from unittest.mock import MagicMock, AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from deps import get_ollama_client
from routers.models import router

# ---------------------------------------------------------------------------
# Test application
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router, prefix="/api")


# ---------------------------------------------------------------------------
# Mock OllamaClient implementations
# ---------------------------------------------------------------------------


class MockOllamaClient:
    """
    A happy-path mock that returns predictable data for every OllamaClient method.
    Methods that are async generators are defined as such so FastAPI's streaming
    code path exercises the real generator protocol.
    """

    async def list_models(self) -> list:
        return [
            {"name": "llama3:latest", "size": 4_700_000_000, "modified_at": "2024-01-01T00:00:00Z"},
            {"name": "mistral:latest", "size": 4_100_000_000, "modified_at": "2024-01-01T00:00:00Z"},
        ]

    async def delete_model(self, name: str) -> None:
        # Simulates a successful deletion — returns nothing.
        pass

    async def pull_model(self, name: str):
        # Async generator that yields a realistic Ollama pull sequence.
        yield {"status": "pulling manifest"}
        yield {"status": "downloading", "completed": 512, "total": 1024}
        yield {"status": "verifying sha256 digest"}
        yield {"status": "success"}

    async def chat(self, model: str, messages: list):
        yield "Hello"

    async def generate(self, model: str, prompt: str):
        yield "Generated"


class ErrorListOllamaClient(MockOllamaClient):
    """Mock that raises an exception when listing models."""

    async def list_models(self):
        raise Exception("Connection refused by Ollama")


class ErrorDeleteOllamaClient(MockOllamaClient):
    """Mock that raises an httpx.HTTPStatusError (404) on delete."""

    async def delete_model(self, name: str) -> None:
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "model not found"
        raise httpx.HTTPStatusError(
            "404 Not Found",
            request=mock_request,
            response=mock_response,
        )


class ErrorPullOllamaClient(MockOllamaClient):
    """Mock whose pull_model generator raises mid-stream."""

    async def pull_model(self, name: str):
        yield {"status": "pulling manifest"}
        raise Exception("Disk full")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse(body: str) -> list[dict]:
    """
    Parse a raw SSE text body into a list of event dicts.

    Only lines starting with 'data: ' are considered; blank lines and
    comment lines are ignored.

    Args:
        body: Raw SSE response body as returned by TestClient.

    Returns:
        List of parsed JSON dicts, one per event.
    """
    events = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: ") and line != "data: [DONE]":
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """
    Ensure dependency_overrides are cleared after every test so that
    individual tests don't leak state to subsequent ones.
    """
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/models — list installed models
# ---------------------------------------------------------------------------


class TestListModels:
    """Tests for GET /api/models."""

    def test_returns_installed_models(self):
        """The models list from OllamaClient is forwarded as-is."""
        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
        response = TestClient(app).get("/api/models")

        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) == 2
        assert data["models"][0]["name"] == "llama3:latest"

    def test_returns_503_when_ollama_unreachable(self):
        """A connection error from OllamaClient must surface as HTTP 503."""
        app.dependency_overrides[get_ollama_client] = lambda: ErrorListOllamaClient()
        response = TestClient(app).get("/api/models")

        assert response.status_code == 503
        assert "detail" in response.json()


# ---------------------------------------------------------------------------
# GET /api/models/available — curated model catalogue
# ---------------------------------------------------------------------------


class TestAvailableModels:
    """Tests for GET /api/models/available."""

    def test_returns_list_of_models(self):
        """The static catalogue must be returned without modification."""
        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
        response = TestClient(app).get("/api/models/available")

        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) > 0

    def test_each_model_has_required_keys(self):
        """Every catalogue entry must have name, description, size, and tags."""
        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
        response = TestClient(app).get("/api/models/available")

        for model in response.json()["models"]:
            assert "name" in model
            assert "description" in model
            assert "size" in model
            assert "tags" in model


# ---------------------------------------------------------------------------
# POST /api/models/pull — SSE model download
# ---------------------------------------------------------------------------


class TestPullModel:
    """Tests for POST /api/models/pull."""

    def test_returns_sse_content_type(self):
        """Pull endpoint must return text/event-stream media type."""
        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
        response = TestClient(app).post("/api/models/pull", json={"name": "llama3:latest"})

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_streams_sse_events(self):
        """Each progress dict yielded by pull_model must appear as a data event."""
        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
        response = TestClient(app).post("/api/models/pull", json={"name": "llama3:latest"})

        events = _parse_sse(response.text)
        # We expect 4 events from MockOllamaClient.pull_model
        assert len(events) == 4
        assert events[0]["status"] == "pulling manifest"
        assert events[1]["status"] == "downloading"
        assert events[1]["completed"] == 512
        assert events[3]["status"] == "success"

    def test_streams_error_event_on_exception(self):
        """
        If pull_model raises mid-stream, an error event must be emitted
        rather than crashing the server with an unhandled exception.
        """
        app.dependency_overrides[get_ollama_client] = lambda: ErrorPullOllamaClient()
        response = TestClient(app).post("/api/models/pull", json={"name": "llama3:latest"})

        # Server must remain healthy (no 500)
        assert response.status_code == 200
        events = _parse_sse(response.text)
        # At minimum, one progress event before the error
        assert any("error" in e for e in events), "An error event must be emitted"

    def test_requires_name_field(self):
        """Omitting the 'name' field must result in HTTP 422 Unprocessable Entity."""
        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
        response = TestClient(app).post("/api/models/pull", json={})

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/models/update — re-pull to update
# ---------------------------------------------------------------------------


class TestUpdateModel:
    """Tests for POST /api/models/update."""

    def test_returns_sse_stream(self):
        """Update is a pull under the hood; same SSE format expected."""
        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
        response = TestClient(app).post("/api/models/update", json={"name": "llama3:latest"})

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = _parse_sse(response.text)
        assert len(events) > 0


# ---------------------------------------------------------------------------
# DELETE /api/models/{name} — remove installed model
# ---------------------------------------------------------------------------


class TestDeleteModel:
    """Tests for DELETE /api/models/{name}."""

    def test_returns_200_on_success(self):
        """Successful deletion returns 200 with name and status confirmation."""
        app.dependency_overrides[get_ollama_client] = lambda: MockOllamaClient()
        response = TestClient(app).delete("/api/models/llama3:latest")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["name"] == "llama3:latest"

    def test_returns_404_when_model_not_found(self):
        """When Ollama reports 404, the router must relay it as HTTP 404."""
        app.dependency_overrides[get_ollama_client] = lambda: ErrorDeleteOllamaClient()
        response = TestClient(app).delete("/api/models/nonexistent:latest")

        assert response.status_code == 404
        assert "detail" in response.json()
