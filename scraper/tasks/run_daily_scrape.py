"""Celery task orchestration for the daily scrape workflow."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from celery import chord
from postgrest.exceptions import APIError

from worker import celery_app
from core.circuit_breaker import is_open
from core.supabase import get_supabase_client
from core.system_settings import get_runtime_settings
from tasks.compute_velocity import compute_velocity_all
from tasks.discover_channels import discover_channels_now
from tasks.run_gate0 import run_gate0
from tasks.scrape_bitchute import scrape_bitchute_channel
from tasks.scrape_rumble import scrape_rumble_channel

logger = logging.getLogger(__name__)


class _ScrapeSignature(Protocol):
    def set(self, **options: int) -> "_ScrapeSignature": ...


def _stage_scrape_signatures(
    scrape_signatures: list[tuple[str, _ScrapeSignature]],
) -> list[_ScrapeSignature]:
    """Apply configured dispatch pacing to a scrape signature list."""
    runtime = get_runtime_settings()
    batch_size = max(1, runtime.scrape_dispatch_batch_size)
    pause_s = max(0.0, runtime.scrape_dispatch_pause_seconds)
    # BitChute is currently far more block-sensitive; pace starts to avoid
    # simultaneous challenge hits across multiple workers.
    platform_min_gap_s: dict[str, int] = {
        "bitchute": 20,
        "rumble": 4,
    }
    platform_seen: dict[str, int] = {}
    staged: list[object] = []
    for idx, (platform, sig) in enumerate(scrape_signatures):
        stage = idx // batch_size
        batch_delay = int(stage * pause_s)
        seen_count = platform_seen.get(platform, 0)
        gap = platform_min_gap_s.get(platform, 0)
        platform_delay = seen_count * gap
        delay = max(batch_delay, platform_delay)
        platform_seen[platform] = seen_count + 1
        staged.append(sig.set(countdown=delay))
    return staged


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

    runtime = get_runtime_settings()
    if status == "clean" and datetime.now(timezone.utc) - checked_at >= timedelta(
        days=runtime.gate0_clean_recheck_days
    ):
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

    limit = get_runtime_settings().gate0_daily_queue_limit
    for _, channel_id in sorted(due_channels)[:limit]:
        run_gate0.delay(channel_id, False)

    return min(len(due_channels), limit)


def _latest_snapshot_by_channel_id(channel_ids: list[str]) -> dict[str, datetime]:
    """Return latest scraped_at timestamp per channel id."""
    if not channel_ids:
        return {}

    unique_ids = list(dict.fromkeys(channel_ids))
    chunk_size = 200
    client = get_supabase_client()
    latest: dict[str, datetime] = {}
    try:
        for idx in range(0, len(unique_ids), chunk_size):
            chunk_ids = unique_ids[idx : idx + chunk_size]
            snapshots_result = (
                client.table("channel_snapshots")
                .select("channel_id,scraped_at")
                .in_("channel_id", chunk_ids)
                .order("channel_id")
                .order("scraped_at", desc=True)
                .execute()
            )
            for row in snapshots_result.data or []:
                channel_id = str(row.get("channel_id") or "")
                if not channel_id or channel_id in latest:
                    continue
                parsed = _parse_datetime(row.get("scraped_at"))
                if parsed is not None:
                    latest[channel_id] = parsed
    except APIError as exc:
        logger.warning(
            "Failed to fetch latest channel snapshots; falling back to no-history mode: %s",
            exc,
            exc_info=True,
        )
        return {}
    return latest


def _prioritize_channels_for_scrape(
    channels: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Prioritize never-scraped channels first, then stalest channels."""
    def has_missing_core_metrics(row: dict[str, object]) -> bool:
        """Return True when any dashboard-critical metric is missing (N/A)."""
        return any(
            row.get(metric) is None
            for metric in (
                "subscriber_count",
                "avg_views",
                "avg_comments",
                "last_active_date",
            )
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
    runtime = get_runtime_settings()
    min_age = timedelta(hours=max(0, runtime.scrape_rescrape_min_hours))
    prioritized: list[tuple[bool, datetime, dict[str, object]]] = []

    for row in channels:
        channel_id = str(row.get("id") or "")
        latest = latest_by_id.get(channel_id)
        never_scraped = (row.get("has_been_scraped") is False) or latest is None
        missing_metrics = has_missing_core_metrics(row)
        discovery_status = row.get("discovery_status")
        discovered_unresolved = discovery_status in {"new", "queued"}

        if (
            runtime.scrape_only_new_or_missing_metrics
            and not never_scraped
            and not missing_metrics
            and not discovered_unresolved
        ):
            continue
        if not never_scraped and latest is not None and not missing_metrics and now - latest < min_age:
            continue
        if never_scraped or discovered_unresolved:
            prioritized.append((True, datetime.min.replace(tzinfo=timezone.utc), row))
        else:
            prioritized.append((False, latest, row))

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
            discovery_result = discover_channels_now(queue_scrapes=True)
        except Exception as exc:
            discovery_failed = True
            logger.error("Failed to run channel discovery: %s", exc, exc_info=True)
            discovery_result = {
                "seed_expansion": {"error": str(exc)},
                "keyword_expansion": {"error": str(exc)},
                "inserted": 0,
                "refreshed": 0,
                "duplicates": 0,
                "invalid": 1,
                "new_urls": [],
                "scrape_queued": 0,
                "error": str(exc),
            }
    else:
        discovery_result = {"disabled": True}

    try:
        gate0_queued = _queue_due_gate0_checks()
    except APIError as exc:
        logger.error("Failed to queue Gate 0 checks: %s", exc, exc_info=True)
        gate0_queued = 0

    if discovery_failed:
        logger.warning("Post-scrape discovery completed with failures")
    return {
        "discovery": discovery_result,
        "discovery_failed": discovery_failed,
        "gate0_queued": gate0_queued,
        "velocity_task_id": None,
    }


def _passes_weekly_velocity_threshold(channel: dict[str, object]) -> bool:
    """Return True when a clean channel is worth weekly velocity scraping."""
    runtime = get_runtime_settings()
    if channel.get("comment_tier") in {"sweet_spot", "whale"}:
        return True

    avg_comments = channel.get("avg_comments")
    avg_views = channel.get("avg_views")
    subscribers = channel.get("subscriber_count")

    try:
        if float(avg_comments or 0) >= runtime.velocity_weekly_min_avg_comments:
            return True
        if (
            runtime.velocity_weekly_min_avg_views > 0
            and float(avg_views or 0) >= runtime.velocity_weekly_min_avg_views
        ):
            return True
        if (
            runtime.velocity_weekly_min_subscribers > 0
            and int(subscribers or 0) >= runtime.velocity_weekly_min_subscribers
        ):
            return True
    except (TypeError, ValueError):
        return False

    return False


def _select_weekly_velocity_channels(
    channels: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Select clean, scraped, metric-rich channels for weekly velocity snapshots."""
    channel_ids: list[str] = []
    for row in channels:
        raw_id = row.get("id")
        try:
            channel_ids.append(str(UUID(str(raw_id))))
        except (TypeError, ValueError):
            continue

    latest_by_id = _latest_snapshot_by_channel_id(channel_ids)
    now = datetime.now(timezone.utc)
    runtime = get_runtime_settings()
    stale_age = timedelta(hours=max(0, runtime.velocity_weekly_stale_hours))
    selected: list[tuple[datetime, dict[str, object]]] = []

    for row in channels:
        channel_id = str(row.get("id") or "")
        latest = latest_by_id.get(channel_id)
        if latest is not None and now - latest < stale_age:
            continue
        if _passes_weekly_velocity_threshold(row):
            selected.append((latest or datetime.min.replace(tzinfo=timezone.utc), row))

    platform_rank = {
        platform: index for index, platform in enumerate(runtime.scrape_platform_priority)
    }
    selected.sort(
        key=lambda item: (
            item[0],
            platform_rank.get(str(item[1].get("platform") or ""), 99),
        )
    )
    return [item[1] for item in selected]


@celery_app.task(name="scraper.tasks.run_weekly_velocity_scrape_callback")
def run_weekly_velocity_scrape_callback() -> dict[str, object]:
    """Compute velocity after the weekly clean-lead scrape finishes."""
    velocity_task = compute_velocity_all.delay(qualified_only=True)
    return {"velocity_task_id": velocity_task.id}


@celery_app.task(name="scraper.tasks.run_weekly_velocity_scrape")
def run_weekly_velocity_scrape() -> dict[str, object]:
    """Queue weekly scrapes for clean leads with stronger engagement metrics."""
    logger.info("Starting weekly clean-lead velocity scrape workflow")
    runtime = get_runtime_settings()
    if not runtime.weekly_velocity_enabled:
        return {"queued": 0, "skipped": "weekly_velocity_disabled"}

    try:
        client = get_supabase_client()
        result = (
            client.table("channels")
            .select(
                "id,channel_url,platform,subscriber_count,avg_views,avg_comments,"
                "comment_tier,has_been_scraped,discovery_status,gate0_status"
            )
            .eq("is_active", True)
            .eq("gate0_status", "clean")
            .eq("has_been_scraped", True)
            .eq("discovery_status", "scraped")
            .not_.is_("subscriber_count", "null")
            .not_.is_("avg_views", "null")
            .not_.is_("avg_comments", "null")
            .execute()
        )
        channels = _select_weekly_velocity_channels(result.data or [])
    except APIError as exc:
        logger.error("Failed to fetch weekly velocity channels: %s", exc, exc_info=True)
        return {"queued": 0, "error": str(exc)}

    scrape_signatures: list[tuple[str, _ScrapeSignature]] = []
    for channel in channels:
        channel_url = str(channel.get("channel_url") or "")
        platform = str(channel.get("platform") or "")
        if not channel_url:
            continue
        if platform in {"rumble", "bitchute"} and is_open(platform):
            logger.warning(
                "Skipping %s weekly velocity scrape due to open circuit breaker: %s",
                platform,
                channel_url,
            )
            continue
        if platform == "rumble":
            scrape_signatures.append((platform, scrape_rumble_channel.s(channel_url)))
        elif platform == "bitchute":
            scrape_signatures.append((platform, scrape_bitchute_channel.s(channel_url)))
        else:
            logger.warning("Unsupported platform skipped: %s", platform)

    max_channels = get_runtime_settings().scrape_run_max_channels
    if max_channels > 0:
        scrape_signatures = scrape_signatures[:max_channels]

    if not scrape_signatures:
        velocity_task = compute_velocity_all.delay(qualified_only=True)
        return {
            "queued": 0,
            "velocity_task_id": velocity_task.id,
        }

    staged = _stage_scrape_signatures(scrape_signatures)

    workflow = chord(staged)(run_weekly_velocity_scrape_callback.si())
    logger.info(
        "Queued weekly clean-lead velocity workflow: scrapes=%d callback=%s",
        len(staged),
        workflow.id,
    )
    return {
        "queued": len(staged),
        "workflow_task_id": workflow.id,
    }


@celery_app.task(name="scraper.tasks.run_daily_scrape")
def run_daily_scrape() -> dict[str, object]:
    """Queue active channel scrapes and compute velocity after completion."""
    logger.info("Starting daily scrape workflow")
    try:
        client = get_supabase_client()
        result = (
            client.table("channels")
            .select(
                "id,channel_url,platform,subscriber_count,avg_views,avg_comments,"
                "last_active_date,has_been_scraped,discovery_status,discovery_source"
            )
            .eq("is_active", True)
            .execute()
        )
        channels = _prioritize_channels_for_scrape(result.data or [])
    except APIError as exc:
        logger.error("Failed to fetch active channel URLs: %s", exc, exc_info=True)
        return {"queued": 0, "error": str(exc)}

    scrape_signatures: list[tuple[str, _ScrapeSignature]] = []
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
            scrape_signatures.append((platform, scrape_rumble_channel.s(channel_url)))
        elif platform == "bitchute":
            scrape_signatures.append((platform, scrape_bitchute_channel.s(channel_url)))
        else:
            logger.warning("Unsupported platform skipped: %s", platform)

    max_channels = get_runtime_settings().scrape_run_max_channels
    if max_channels > 0:
        scrape_signatures = scrape_signatures[:max_channels]

    if not scrape_signatures:
        post_task = run_post_scrape_tasks.delay()
        return {
            "queued": 0,
            "post_scrape_task_id": post_task.id,
        }

    staged = _stage_scrape_signatures(scrape_signatures)

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
