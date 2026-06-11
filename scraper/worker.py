"""Celery app definition and entry point for the scraper worker."""

import asyncio
import logging
import ssl
import sys

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from core.config import scraper_settings
from schedules.beat_schedule import CELERY_BEAT_SCHEDULE

_SSL_OPTS = (
    {"ssl_cert_reqs": ssl.CERT_NONE}
    if scraper_settings.redis_url.startswith("rediss://")
    else {}
)

# Reduce noisy request logs from HTTP clients used by Supabase/PostgREST.


logger = logging.getLogger(__name__)

_BROWSER_WORKER_QUEUES = {"rumble", "substack"}


def _should_manage_browser_pool() -> bool:
    """Return True for worker processes consuming browser-backed scrape queues."""
    return any(
        arg.startswith("--queues=")
        and any(
            queue.strip() in _BROWSER_WORKER_QUEUES
            for queue in arg.split("=", 1)[1].split(",")
        )
        for arg in sys.argv
    )

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
    broker_use_ssl=_SSL_OPTS or None,
    redis_backend_use_ssl=_SSL_OPTS or None,
    # Prevent Redis from requeuing long-running tasks (discovery can take hours).
    broker_transport_options={"visibility_timeout": 21600},
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="discovery",
    task_routes={
        "scraper.tasks.discover_channels": {"queue": "discovery"},
        "scraper.tasks.discover_keyword_expansion": {"queue": "discovery"},
        "scraper.tasks.discover_seed_expansion": {"queue": "discovery"},
"scraper.tasks.scrape_never_scraped_rumble_substack": {"queue": "discovery"},
        "scraper.tasks.run_daily_scrape": {"queue": "discovery"},
        "scraper.tasks.run_scrape_new_channels": {"queue": "discovery"},
        "scraper.tasks.dispatch_daily_scrapes": {"queue": "discovery"},
        "scraper.tasks.run_post_scrape_tasks": {"queue": "discovery"},
        "scraper.tasks.run_weekly_velocity_scrape": {"queue": "discovery"},
        "scraper.tasks.run_weekly_velocity_scrape_callback": {"queue": "discovery"},
        "scraper.tasks.compute_velocity": {"queue": "discovery"},
        "scraper.tasks.compute_velocity_all": {"queue": "discovery"},
        "scraper.tasks.clear_platform_slots": {"queue": "discovery"},
        "scraper.tasks.scrape_rumble_channel": {"queue": "rumble"},
        "scraper.tasks.scrape_rumble_all": {"queue": "rumble"},
        "scraper.tasks.scrape_substack_channel": {"queue": "substack"},
        "scraper.tasks.scrape_substack_all": {"queue": "substack"},
        "scraper.tasks.classify_channels": {"queue": "classify"},
        "scraper.tasks.run_gate0": {"queue": "gate0"},
        "scraper.tasks.run_gate0_all": {"queue": "gate0"},
    },
    # Kill hung browser sessions before they strand a worker slot indefinitely.
    task_annotations={
        "scraper.tasks.scrape_rumble_channel": {
            "time_limit": 1200,
            "soft_time_limit": 1080,
        },
        "scraper.tasks.scrape_substack_channel": {
            "time_limit": 1200,
            "soft_time_limit": 1080,
        },
        "scraper.tasks.run_gate0": {
            "time_limit": 300,
            "soft_time_limit": 270,
        },
        "scraper.tasks.classify_channels": {
            "time_limit": 7200,
            "soft_time_limit": 6900,
        },
    },
    imports=[
        "tasks.scrape_rumble",
        "tasks.scrape_substack",
        "tasks.scrape_never_scraped",
        "tasks.maintenance",
        "tasks.compute_velocity",
        "tasks.discover_channels",
        "tasks.discover_keyword_expansion",
        "tasks.discover_seed_expansion",
        "tasks.run_gate0",
"tasks.run_daily_scrape",
        "tasks.run_scrape_new_channels",
        "tasks.classify_channels",
    ],
)


# ---------------------------------------------------------------------------
# Startup proxy health validation
# ---------------------------------------------------------------------------

@worker_process_init.connect
def _on_worker_process_init(**kwargs):
    """Validate proxies and pre-warm the browser pool for browser-backed workers.

    Only runs for workers consuming the rumble or substack queues.  Discovery,
    classify, and gate0 workers skip this entirely — they never use a browser
    or the proxy pool, so importing those modules would be wasted overhead.

    worker_process_init fires in the child process after Celery's fork, so
    reset() discards anything that leaked across the fork boundary before
    any async work starts.

    Non-fatal: any failure is caught so the worker always starts.
    """
    if not _should_manage_browser_pool():
        logger.info("Worker startup: browser management skipped (non-browser queue)")
        return
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
                target_url="https://rumble.com/",
            )
            await worker_pool.ensure_browser()

        worker_pool.run(_startup())
        logger.info("Worker startup complete: proxies checked, browser pre-warmed")
    except Exception as exc:
        logger.warning(
            "Worker startup tasks failed (worker will continue): %s", exc
        )


@worker_process_shutdown.connect
def _on_worker_process_shutdown(**kwargs):
    """Cleanly close the browser pool on worker process exit."""
    if not _should_manage_browser_pool():
        return
    try:
        from core.browser_pool import worker_pool
        worker_pool.shutdown()
    except Exception:
        pass
