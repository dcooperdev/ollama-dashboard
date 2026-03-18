"""
Unit tests for routers/status.py — GET /api/status endpoint.

check_internet() and check_ollama() are patched at their import site inside
the router module so no real network calls are ever made.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.status import router

# ---------------------------------------------------------------------------
# Minimal test application — uses only the status router.
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router, prefix="/api")
client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _patch_connectivity(internet: bool, ollama: bool):
    """
    Return a context manager that simultaneously patches both connectivity
    functions as AsyncMocks with the given return values.
    """
    return (
        patch("routers.status.check_internet", new_callable=AsyncMock, return_value=internet),
        patch("routers.status.check_ollama", new_callable=AsyncMock, return_value=ollama),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetStatus:
    """Tests for GET /api/status."""

    def test_both_services_online(self):
        """When both checks succeed the response body must reflect that."""
        with patch("routers.status.check_internet", new_callable=AsyncMock, return_value=True), \
             patch("routers.status.check_ollama", new_callable=AsyncMock, return_value=True):
            response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert data["internet"] is True
        assert data["ollama"] is True

    def test_internet_down_ollama_up(self):
        """Internet failure is reported independently of Ollama status."""
        with patch("routers.status.check_internet", new_callable=AsyncMock, return_value=False), \
             patch("routers.status.check_ollama", new_callable=AsyncMock, return_value=True):
            response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert data["internet"] is False
        assert data["ollama"] is True

    def test_internet_up_ollama_down(self):
        """Ollama failure is reported independently of internet status."""
        with patch("routers.status.check_internet", new_callable=AsyncMock, return_value=True), \
             patch("routers.status.check_ollama", new_callable=AsyncMock, return_value=False):
            response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert data["internet"] is True
        assert data["ollama"] is False

    def test_both_services_down(self):
        """Complete outage scenario — both keys are False."""
        with patch("routers.status.check_internet", new_callable=AsyncMock, return_value=False), \
             patch("routers.status.check_ollama", new_callable=AsyncMock, return_value=False):
            response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert data["internet"] is False
        assert data["ollama"] is False

    def test_response_schema_has_exactly_two_keys(self):
        """The contract guarantees exactly two boolean keys and nothing else."""
        with patch("routers.status.check_internet", new_callable=AsyncMock, return_value=True), \
             patch("routers.status.check_ollama", new_callable=AsyncMock, return_value=True):
            response = client.get("/api/status")

        data = response.json()
        assert set(data.keys()) == {"internet", "ollama"}
        assert isinstance(data["internet"], bool)
        assert isinstance(data["ollama"], bool)

    def test_content_type_is_json(self):
        """Response content-type must be application/json."""
        with patch("routers.status.check_internet", new_callable=AsyncMock, return_value=True), \
             patch("routers.status.check_ollama", new_callable=AsyncMock, return_value=True):
            response = client.get("/api/status")

        assert "application/json" in response.headers["content-type"]

    def test_both_checks_are_called(self):
        """Both connectivity functions must be invoked on every request."""
        mock_internet = AsyncMock(return_value=True)
        mock_ollama = AsyncMock(return_value=True)

        with patch("routers.status.check_internet", mock_internet), \
             patch("routers.status.check_ollama", mock_ollama):
            client.get("/api/status")

        mock_internet.assert_called_once()
        mock_ollama.assert_called_once()
