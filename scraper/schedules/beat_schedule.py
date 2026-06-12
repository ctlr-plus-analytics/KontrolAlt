"""Celery Beat schedule — daily scrape and velocity computation."""

from celery.schedules import crontab
from core.runtime_settings import get_runtime_settings


def _daily_scrape_crontab() -> crontab:
    settings = get_runtime_settings()
    try:
        hour_str, minute_str = settings.daily_scrape_utc_time.split(":")
        return crontab(hour=int(hour_str), minute=int(minute_str))
    except (TypeError, ValueError):
        return crontab(hour=2, minute=0)


def _weekly_velocity_crontab() -> crontab:
    settings = get_runtime_settings()
    try:
        hour_str, minute_str = settings.weekly_velocity_utc_time.split(":")
        return crontab(
            hour=int(hour_str),
            minute=int(minute_str),
            day_of_week=settings.weekly_velocity_utc_day,
        )
    except (TypeError, ValueError):
        return crontab(hour=3, minute=0, day_of_week="sun")

CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {
    # Disabled — re-add entries to re-enable scheduled runs
}
