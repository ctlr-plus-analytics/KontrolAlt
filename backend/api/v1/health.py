"""Health endpoint — GET /health (no auth required)."""

from datetime import datetime, timezone

import httpx
import redis
from fastapi import APIRouter
from postgrest.exceptions import APIError

from core.config import settings
from core.logging import get_logger
from core.supabase import supabase_admin
from models.scrape import HealthResponse

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service health status with Supabase and Redis connectivity.

    No authentication required.
    """
    supabase_ok = False
    redis_ok = False

    # Check Supabase connectivity
    try:
        supabase_admin.table("channels").select("id").limit(1).execute()
        supabase_ok = True
    except (APIError, httpx.HTTPError) as exc:
        logger.warning("Supabase health check failed: %s", exc)

    # Check Redis connectivity
    try:
        r = redis.from_url(settings.redis_url, socket_connect_timeout=3)
        r.ping()
        redis_ok = True
    except redis.RedisError as exc:
        logger.warning("Redis health check failed: %s", exc)

    overall = "ok" if (supabase_ok and redis_ok) else "degraded"

    return HealthResponse(
        status=overall,
        timestamp=datetime.now(timezone.utc),
        supabase=supabase_ok,
        redis=redis_ok,
        environment=settings.app_env,
    )
