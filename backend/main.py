"""
Ollama Dashboard — FastAPI application entry point.

Responsibilities:
  - Instantiate the FastAPI app with metadata.
  - Configure CORS to allow the Vite frontend (http://localhost:5173)
    to communicate with this API during development.
  - Register all routers under the /api prefix.
  - Expose a root health-check endpoint.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import chat, models, status

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ollama Dashboard API",
    description=(
        "REST and SSE backend for the Ollama administration panel. "
        "Manages local models, streams inference results, and reports "
        "system connectivity status."
    ),
    version="1.0.0",
    docs_url="/docs",    # Swagger UI
    redoc_url="/redoc",  # ReDoc UI
)

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server and common production origins
# ---------------------------------------------------------------------------

# Add any additional origins here (e.g. a production domain) as needed.
ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Vite default dev server
    "http://localhost:4173",   # Vite preview server
    "http://127.0.0.1:5173",
    "http://127.0.0.1:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],    # GET, POST, DELETE, OPTIONS, etc.
    allow_headers=["*"],    # Authorization, Content-Type, etc.
)

# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------

# All application routes are mounted under /api to make it trivial to reverse-
# proxy the API alongside a static frontend without path collisions.
app.include_router(status.router, prefix="/api", tags=["Status"])
app.include_router(models.router, prefix="/api", tags=["Models"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])


# ---------------------------------------------------------------------------
# Root health-check
# ---------------------------------------------------------------------------


@app.get("/", tags=["Health"], summary="Root health check")
async def root() -> dict:
    """
    Lightweight endpoint to verify the API process is alive.

    Returns:
        dict: A static message confirming the service is running.
    """
    return {"message": "Ollama Dashboard API is running", "docs": "/docs"}
