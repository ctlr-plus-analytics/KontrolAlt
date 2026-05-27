"""Celery app definition and entry point for the scraper worker."""

import asyncio
import logging

from celery import Celery
from celery.signals import worker_init

from core.config import scraper_settings
from schedules.beat_schedule import CELERY_BEAT_SCHEDULE

# Reduce noisy request logs from HTTP clients used by Supabase/PostgREST.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# Suppress Celery per-task trace lines like:
# "Task ... succeeded in ...: {...}"
logging.getLogger("celery.app.trace").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

celery_app = Celery(
    "kontrol_alt_scraper",
    broker=scraper_settings.redis_url,
    backend=scraper_settings.redis_url,
)
# ---------------------------------------------------------------------------
# Celery configuration
# ---------------------------------------------------------------------------
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule=CELERY_BEAT_SCHEDULE,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    imports=[
        "tasks.scrape_rumble",
        "tasks.scrape_bitchute",
        "tasks.scrape_substack",
        "tasks.maintenance",
        "tasks.compute_velocity",
        "tasks.discover_channels",
        "tasks.discover_keyword_expansion",
        "tasks.discover_seed_expansion",
        "tasks.run_gate0",
        "tasks.find_lookalikes",
        "tasks.run_daily_scrape",
    ],
)


# ---------------------------------------------------------------------------
# Startup proxy health validation
# ---------------------------------------------------------------------------

@worker_init.connect
def _on_worker_init(**kwargs):
    """Validate proxy reachability once per worker process at startup.

    Runs asynchronously via asyncio.run() since Celery's worker_init signal
    fires in a synchronous context before any event loop is present.

    The check is non-fatal: any exception is caught so a Redis outage,
    network hiccup, or misconfigured proxy never prevents the worker from
    starting. Unreachable proxies receive an initial health score penalty so
    healthy proxies get priority from the very first scrape task.
    """
    try:
        from core.proxy import (
            proxy_rotator,
            proxy_health_tracker,
            validate_proxy_pool_on_startup,
        )
        asyncio.run(
            validate_proxy_pool_on_startup(
                proxy_rotator,
                proxy_health_tracker,
                timeout=12.0,
                concurrency=4,
            )
        )
    except Exception as exc:
        logger.warning(
            "Proxy startup health check failed (worker will continue): %s", exc
        )
    try:
        from tasks.scrape_helpers import clear_platform_slots

        result = clear_platform_slots()
        logger.info(
            "Worker startup platform-slot cleanup: deleted=%s keys=%s",
            result.get("deleted"),
            ",".join(result.get("keys", [])),
        )
    except Exception as exc:
        logger.warning(
            "Platform-slot startup cleanup failed (worker will continue): %s", exc
        )
