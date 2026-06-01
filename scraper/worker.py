"""Celery app definition and entry point for the scraper worker."""

import asyncio
import logging

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from core.config import scraper_settings
from schedules.beat_schedule import CELERY_BEAT_SCHEDULE

# Reduce noisy request logs from HTTP clients used by Supabase/PostgREST.


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
        "tasks.scrape_substack",
        "tasks.maintenance",
        "tasks.compute_velocity",
        "tasks.discover_channels",
        "tasks.discover_keyword_expansion",
        "tasks.discover_seed_expansion",
        "tasks.run_gate0",
        "tasks.find_lookalikes",
        "tasks.run_daily_scrape",
        "tasks.classify_channels",
    ],
)


# ---------------------------------------------------------------------------
# Startup proxy health validation
# ---------------------------------------------------------------------------

@worker_process_init.connect
def _on_worker_process_init(**kwargs):
    """Validate proxies and pre-warm the browser pool inside each forked worker.

    worker_process_init fires in the child process after Celery's fork, so
    there are no inherited broken event-loop or browser-websocket handles.
    reset() discards anything that leaked across the fork boundary before
    any async work starts.

    Non-fatal: any failure is caught so the worker always starts.
    """
    try:
        from core.proxy import (
            proxy_rotator,
            proxy_health_tracker,
            validate_proxy_pool_on_startup,
        )
        from core.browser_pool import worker_pool

        worker_pool.reset()

        async def _startup():
            await validate_proxy_pool_on_startup(
                proxy_rotator,
                proxy_health_tracker,
                timeout=12.0,
                concurrency=4,
            )
            await worker_pool.ensure_browser()

        worker_pool.run(_startup())
        logger.info("Worker process startup complete: proxies checked, browser pre-warmed")
    except Exception as exc:
        logger.warning(
            "Worker startup tasks failed (worker will continue): %s", exc
        )


@worker_process_shutdown.connect
def _on_worker_process_shutdown(**kwargs):
    """Cleanly close the browser pool on worker process exit."""
    try:
        from core.browser_pool import worker_pool
        worker_pool.shutdown()
    except Exception:
        pass
