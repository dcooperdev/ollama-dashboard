"""
Connectivity checks for internet and Ollama service availability.

This module is intentionally side-effect-free: it makes no assumptions about
the framework layer (FastAPI, CLI, tests, etc.) — it only returns booleans.
"""

import httpx

# Cloudflare's public DNS resolver is used as a lightweight, reliable probe.
# It responds quickly and requires no DNS resolution itself.
INTERNET_PROBE_URL = "https://1.1.1.1"

# Default Ollama service address — configurable via dependency injection in tests.
OLLAMA_BASE_URL = "http://localhost:11434"

# Maximum seconds to wait before declaring a connectivity check as failed.
TIMEOUT_SECONDS = 3.0


async def check_internet(probe_url: str = INTERNET_PROBE_URL) -> bool:
    """
    Return True if an active internet connection is detected.

    A GET request is sent to `probe_url` with a short timeout.
    Any network-level exception (timeout, DNS failure, connection refused)
    is caught and results in False being returned — no exceptions are raised.

    Args:
        probe_url: URL to send the probe request to. Override in tests.

    Returns:
        True if the server responds with any HTTP status, False otherwise.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(probe_url, timeout=TIMEOUT_SECONDS)
            # Any HTTP response (even 4xx/5xx) means the network is reachable.
            return response.status_code < 600
    except Exception:
        return False


async def check_ollama(base_url: str = OLLAMA_BASE_URL) -> bool:
    """
    Return True if the local Ollama service is running and accessible.

    Sends a GET to the Ollama root endpoint. Ollama responds with a plain-text
    "Ollama is running" body and HTTP 200 when healthy.

    Args:
        base_url: Ollama base URL. Override in tests or for custom Ollama ports.

    Returns:
        True if Ollama responds successfully, False otherwise.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, timeout=TIMEOUT_SECONDS)
            return response.status_code < 600
    except Exception:
        return False
