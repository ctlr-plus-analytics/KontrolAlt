"""Celery Beat schedule — daily scrape and velocity computation."""

from celery.schedules import crontab
from core.system_settings import get_runtime_settings


def _daily_scrape_crontab() -> crontab:
    settings = get_runtime_settings()
    try:
        hour_str, minute_str = settings.daily_scrape_utc_time.split(":")
        return crontab(hour=int(hour_str), minute=int(minute_str))
    except (TypeError, ValueError):
        return crontab(hour=2, minute=0)

CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    "daily-scrape-and-velocity": {
        "task": "scraper.tasks.run_daily_scrape",
        "schedule": _daily_scrape_crontab(),
    },
}
