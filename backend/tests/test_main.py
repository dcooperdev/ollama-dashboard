"""
Tests for main.py — FastAPI application entry point.

Imports the `app` instance directly from main.py to cover all module-level
statements (FastAPI instantiation, CORS middleware, router registration,
and the root health-check endpoint).
"""

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestRootEndpoint:
    """Tests for GET / (root health-check)."""

    def test_returns_200(self):
        """Root endpoint must return HTTP 200."""
        response = client.get("/")
        assert response.status_code == 200

    def test_returns_message_key(self):
        """Response body must contain a 'message' key."""
        response = client.get("/")
        data = response.json()
        assert "message" in data

    def test_message_is_string(self):
        """The message value must be a non-empty string."""
        response = client.get("/")
        assert isinstance(response.json()["message"], str)
        assert len(response.json()["message"]) > 0

    def test_returns_docs_key(self):
        """Response body must contain a 'docs' key pointing to /docs."""
        response = client.get("/")
        data = response.json()
        assert "docs" in data
        assert data["docs"] == "/docs"


class TestRoutersRegistered:
    """Verify that all routers have been mounted under /api."""

    def test_status_route_exists(self):
        """GET /api/status must be a registered route (may 503 without Ollama)."""
        response = client.get("/api/status")
        # 200 or 503 — either means the route is registered
        assert response.status_code in (200, 503)

    def test_models_route_exists(self):
        """GET /api/models must be a registered route."""
        response = client.get("/api/models")
        assert response.status_code in (200, 503)

    def test_docs_route_exists(self):
        """Swagger UI must be accessible at /docs."""
        response = client.get("/docs")
        assert response.status_code == 200
