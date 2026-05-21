"""Celery task orchestration for the daily scrape workflow."""

import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from celery import chord
from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.circuit_breaker import is_open
from core.supabase import get_supabase_client
from core.system_settings import get_runtime_settings
from tasks.compute_velocity import compute_velocity_all
from tasks.discover_keyword_expansion import discover_keyword_expansion_now
from tasks.discover_seed_expansion import discover_seed_expansion_now
from tasks.run_gate0 import run_gate0
from tasks.scrape_bitchute import scrape_bitchute_channel
from tasks.scrape_helpers import daily_budget_bytes, get_daily_bytes_used
from tasks.scrape_rumble import scrape_rumble_channel

logger = logging.getLogger(__name__)
_GATE0_DAILY_QUEUE_LIMIT = int(os.environ.get("GATE0_DAILY_QUEUE_LIMIT", "200"))
_SCRAPE_RESCRAPE_MIN_HOURS = int(os.environ.get("SCRAPE_RESCRAPE_MIN_HOURS", "72"))
_SCRAPE_COMPUTE_VELOCITY_AFTER_RUN = (
    os.environ.get("SCRAPE_COMPUTE_VELOCITY_AFTER_RUN", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)
_SCRAPE_NEW_CHANNELS_ONLY = (
    os.environ.get("SCRAPE_NEW_CHANNELS_ONLY", "1").strip().lower()
    in {"1", "true", "yes", "on"}
)
_SCRAPE_ONLY_NEW_OR_MISSING_METRICS = (
    os.environ.get("SCRAPE_ONLY_NEW_OR_MISSING_METRICS", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)
_KEYWORD_DISCOVERY_HOLD_SOURCE = "auto_keyword_hold"


def _parse_datetime(value: object) -> datetime | None:
    """Parse a Supabase timestamp into an aware datetime."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _gate0_priority(channel: dict[str, object]) -> int | None:
    """Return Gate 0 priority for due channels, or None when not due."""
    status = channel.get("gate0_status")
    if status in {"dirty", "pending"}:
        return None

    checked_at = _parse_datetime(channel.get("gate0_checked_at"))
    if checked_at is None:
        return 0

    if status == "clean" and datetime.now(timezone.utc) - checked_at >= timedelta(days=7):
        return 1

    return None


def _queue_due_gate0_checks() -> int:
    """Queue due Gate 0 checks with new channels first."""
    runtime = get_runtime_settings()
    if not runtime.gate0_enabled:
        return 0

    client = get_supabase_client()
    result = (
        client.table("channels")
        .select("id,gate0_status,gate0_checked_at")
        .eq("is_active", True)
        .execute()
    )
    due_channels: list[tuple[int, str]] = []
    for channel in result.data or []:
        priority = _gate0_priority(channel)
        if priority is None:
            continue
        due_channels.append((priority, str(channel["id"])))

    for _, channel_id in sorted(due_channels)[:_GATE0_DAILY_QUEUE_LIMIT]:
        run_gate0.delay(channel_id, False)

    return min(len(due_channels), _GATE0_DAILY_QUEUE_LIMIT)


def _latest_snapshot_by_channel_id(channel_ids: list[str]) -> dict[str, datetime]:
    """Return latest scraped_at timestamp per channel id."""
    if not channel_ids:
        return {}

    client = get_supabase_client()
    snapshots_result = (
        client.table("channel_snapshots")
        .select("channel_id,scraped_at")
        .in_("channel_id", channel_ids)
        .order("channel_id")
        .order("scraped_at", desc=True)
        .execute()
    )

    latest: dict[str, datetime] = {}
    for row in snapshots_result.data or []:
        channel_id = str(row.get("channel_id") or "")
        if not channel_id or channel_id in latest:
            continue
        parsed = _parse_datetime(row.get("scraped_at"))
        if parsed is not None:
            latest[channel_id] = parsed
    return latest


def _prioritize_channels_for_scrape(
    channels: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Prioritize never-scraped channels first, then stalest channels."""
    def has_all_core_metrics_na(row: dict[str, object]) -> bool:
        """Return True when all dashboard-critical metrics are missing (N/A)."""
        return all(
            row.get(metric) is None
            for metric in ("subscriber_count", "avg_views", "avg_comments")
        )

    channel_ids: list[str] = []
    for row in channels:
        raw_id = row.get("id")
        try:
            channel_ids.append(str(UUID(str(raw_id))))
        except (TypeError, ValueError):
            continue

    latest_by_id = _latest_snapshot_by_channel_id(channel_ids)
    now = datetime.now(timezone.utc)
    min_age = timedelta(hours=max(0, _SCRAPE_RESCRAPE_MIN_HOURS))
    prioritized: list[tuple[bool, datetime, dict[str, object]]] = []

    for row in channels:
        channel_id = str(row.get("id") or "")
        latest = latest_by_id.get(channel_id)
        missing_metrics = has_all_core_metrics_na(row)

        if _SCRAPE_ONLY_NEW_OR_MISSING_METRICS and latest is not None and not missing_metrics:
            continue
        if (
            _SCRAPE_NEW_CHANNELS_ONLY
            and not _SCRAPE_ONLY_NEW_OR_MISSING_METRICS
            and latest is not None
        ):
            continue
        if latest is not None and not missing_metrics and now - latest < min_age:
            continue
        if latest is None:
            prioritized.append((True, datetime.min.replace(tzinfo=timezone.utc), row))
        else:
            prioritized.append((False, latest, row))

    runtime = get_runtime_settings()
    platform_rank = {
        platform: index for index, platform in enumerate(runtime.scrape_platform_priority)
    }
    # never scraped first, then oldest scrape first, then platform priority
    prioritized.sort(
        key=lambda item: (
            not item[0],
            item[1],
            platform_rank.get(str(item[2].get("platform") or ""), 99),
        )
    )
    return [item[2] for item in prioritized]


@celery_app.task(name="scraper.tasks.run_post_scrape_tasks")
def run_post_scrape_tasks() -> dict[str, object]:
    """Queue due Gate 0 checks and velocity computation after scraping."""
    runtime = get_runtime_settings()
    discovery_failed = False
    if runtime.discovery_enabled:
        try:
            discovery_result = discover_seed_expansion_now()
        except Exception as exc:
            discovery_failed = True
            logger.error("Failed to run seed expansion discovery: %s", exc, exc_info=True)
            discovery_result = {
                "source_channels": 0,
                "discovered": 0,
                "staged": 0,
                "already_staged": 0,
                "duplicates": 0,
                "invalid": 1,
                "error": str(exc),
            }

        try:
            keyword_expansion_result = discover_keyword_expansion_now()
        except Exception as exc:
            discovery_failed = True
            logger.error("Failed to run keyword expansion discovery: %s", exc, exc_info=True)
            keyword_expansion_result = {
                "searched_queries": 0,
                "pages_fetched": 0,
                "raw_links": 0,
                "discovered": 0,
                "staged": 0,
                "already_staged": 0,
                "duplicates": 0,
                "invalid": 1,
                "staged_rumble": 0,
                "staged_bitchute": 0,
                "feedback_terms": [],
                "error": str(exc),
            }

        promotion_result = {"disabled": True, "reason": "direct_channel_insert"}
    else:
        discovery_result = {"disabled": True}
        keyword_expansion_result = {"disabled": True}
        promotion_result = {"disabled": True}

    try:
        gate0_queued = _queue_due_gate0_checks()
    except APIError as exc:
        logger.error("Failed to queue Gate 0 checks: %s", exc, exc_info=True)
        gate0_queued = 0

    velocity_task_id: str | None = None
    if _SCRAPE_COMPUTE_VELOCITY_AFTER_RUN:
        velocity_task = compute_velocity_all.delay()
        velocity_task_id = velocity_task.id
    if discovery_failed:
        logger.warning("Post-scrape discovery completed with failures")
    return {
        "seed_expansion": discovery_result,
        "keyword_expansion": keyword_expansion_result,
        "discovery_promotion": promotion_result,
        "discovery_failed": discovery_failed,
        "gate0_queued": gate0_queued,
        "velocity_task_id": velocity_task_id,
    }


@celery_app.task(name="scraper.tasks.run_daily_scrape")
def run_daily_scrape() -> dict[str, object]:
    """Queue active channel scrapes and compute velocity after completion."""
    logger.info("Starting daily scrape workflow")
    try:
        client = get_supabase_client()
        result = (
            client.table("channels")
            .select("id,channel_url,platform,subscriber_count,avg_views,avg_comments")
            .or_(f"is_active.eq.true,discovery_source.eq.{_KEYWORD_DISCOVERY_HOLD_SOURCE}")
            .execute()
        )
        channels = _prioritize_channels_for_scrape(result.data or [])
    except APIError as exc:
        logger.error("Failed to fetch active channel URLs: %s", exc, exc_info=True)
        return {"queued": 0, "error": str(exc)}

    scrape_signatures = []
    for channel in channels:
        channel_url = str(channel.get("channel_url") or "")
        platform = str(channel.get("platform") or "")
        if not channel_url:
            continue
        if platform in {"rumble", "bitchute"} and is_open(platform):
            logger.warning(
                "Skipping %s scrape due to open circuit breaker: %s",
                platform,
                channel_url,
            )
            continue
        if platform == "rumble":
            scrape_signatures.append(scrape_rumble_channel.s(channel_url))
        elif platform == "bitchute":
            scrape_signatures.append(scrape_bitchute_channel.s(channel_url))
        else:
            logger.warning("Unsupported platform skipped: %s", platform)

    max_channels = scraper_settings.scrape_run_max_channels
    if max_channels > 0:
        scrape_signatures = scrape_signatures[:max_channels]

    if not scrape_signatures:
        post_task = run_post_scrape_tasks.delay()
        return {
            "queued": 0,
            "post_scrape_task_id": post_task.id,
        }

    batch_size = max(1, scraper_settings.scrape_dispatch_batch_size)
    pause_s = max(0.0, scraper_settings.scrape_dispatch_pause_seconds)
    budget = daily_budget_bytes()
    if budget > 0 and get_daily_bytes_used() >= budget:
        logger.warning(
            "Skipping daily run due to byte budget cap: used=%d budget=%d",
            get_daily_bytes_used(),
            budget,
        )
        return {"queued": 0, "skipped": "budget_exhausted"}

    staged: list[object] = []
    for idx, sig in enumerate(scrape_signatures):
        stage = idx // batch_size
        delay = int(stage * pause_s)
        staged.append(sig.set(countdown=delay))

    queued = len(staged)
    workflow = chord(staged)(run_post_scrape_tasks.si())
    logger.info(
        "Queued daily scrape workflow: scrapes=%d velocity_callback=%s",
        queued,
        workflow.id,
    )
    return {
        "queued": queued,
        "workflow_task_id": workflow.id,
    }
