"""Kontrol_Alt Backend — FastAPI application entry point."""

import time
import traceback
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from core.config import settings
from core.logging import get_logger
from core.supabase import supabase_admin
from api.v1.health import router as health_router
from api.v1.router import api_v1_router

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown events
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: verify connectivity on startup."""
    logger.info("Kontrol_Alt API started — environment=%s", settings.app_env)

    # Verify Supabase connectivity
    try:
        supabase_admin.table("channels").select("id").limit(1).execute()
        logger.info("Supabase connectivity verified.")
    except (APIError, httpx.HTTPError) as exc:
        logger.warning(
            "Supabase is unreachable on startup: %s. "
            "The API will start but database operations may fail.",
            exc,
        )

    yield  # Application runs here

    logger.info("Kontrol_Alt API shutting down.")


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Kontrol_Alt API",
    description="Intelligence and Discovery Engine for alternative media platforms.",
    version="1.0.0",
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url="/redoc" if settings.app_env == "development" else None,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the Next.js frontend origin
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Log method, path, status code, and duration for every request."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "%s %s → %s (%.2f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Global exception handler — structured JSON errors
# ---------------------------------------------------------------------------
def _error_content(error: str, detail: str) -> dict[str, str]:
    """Build the API's structured error response body."""
    return {
        "error": error,
        "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Return structured JSON for intentional HTTP errors."""
    logger.warning(
        "%s %s → %s: %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_content("HTTP error", str(exc.detail)),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return structured JSON for request validation errors."""
    logger.warning(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=_error_content("Validation error", str(exc.errors())),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch all unhandled exceptions and return structured JSON."""
    logger.error(
        "Unhandled exception on %s %s:\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content=_error_content("Internal server error", str(exc)),
    )


# ---------------------------------------------------------------------------
# Mount API v1 routes
# ---------------------------------------------------------------------------
app.include_router(health_router, tags=["health"])
app.include_router(api_v1_router, prefix="/api/v1")
