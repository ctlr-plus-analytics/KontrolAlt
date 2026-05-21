"""Celery app definition and entry point for the scraper worker."""

from celery import Celery

from core.config import scraper_settings
from schedules.beat_schedule import CELERY_BEAT_SCHEDULE

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
        "tasks.compute_velocity",
        "tasks.discover_keyword_expansion",
        "tasks.discover_seed_expansion",
        "tasks.promote_discovery_candidates",
        "tasks.run_gate0",
        "tasks.find_lookalikes",
        "tasks.run_daily_scrape",
    ],
)
