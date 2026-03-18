"""
System status router — GET /api/status.

Runs both connectivity checks concurrently with asyncio.gather so that
the combined latency equals max(internet_check, ollama_check), not the sum.
"""

import asyncio

from fastapi import APIRouter

from connectivity import check_internet, check_ollama

router = APIRouter()


@router.get(
    "/status",
    summary="System connectivity status",
    description=(
        "Returns a JSON object with two boolean fields: "
        "``internet`` (reachable public network) and "
        "``ollama`` (local Ollama service is healthy). "
        "Both checks run concurrently to minimise latency."
    ),
)
async def get_status() -> dict:
    """
    Check internet connectivity and Ollama service health in parallel.

    Returns:
        dict: ``{"internet": bool, "ollama": bool}``
    """
    # Run both checks concurrently — total time ≈ max(check1, check2) not sum.
    internet, ollama_ok = await asyncio.gather(
        check_internet(),
        check_ollama(),
    )
    return {"internet": internet, "ollama": ollama_ok}
