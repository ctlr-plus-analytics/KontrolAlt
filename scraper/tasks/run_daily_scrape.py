"""Celery task orchestration for the daily scrape workflow."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

from celery import chain, chord
from postgrest.exceptions import APIError

from worker import celery_app
from core.supabase import get_supabase_client
from core.runtime_settings import get_runtime_settings
from tasks.classify_channels import classify_channels
from tasks.compute_velocity import compute_velocity_all
from tasks.discover_channels import discover_channels
from tasks.run_gate0 import run_gate0
from tasks.scrape_rumble import scrape_rumble_channel
from tasks.scrape_substack import scrape_substack_channel
from tasks.task_queues import QUEUE_CLASSIFY, QUEUE_GATE0, scrape_queue_for_platform

logger = logging.getLogger(__name__)


class _ScrapeSignature(Protocol):
    def set(self, **options: object) -> "_ScrapeSignature": ...


def _stage_scrape_signatures(
    scrape_signatures: list[tuple[str, _ScrapeSignature]],
) -> list[_ScrapeSignature]:
    """Apply configured dispatch pacing to a scrape signature list."""
    runtime = get_runtime_settings()
    batch_size = max(1, runtime.scrape_dispatch_batch_size)
    pause_s = max(0.0, runtime.scrape_dispatch_pause_seconds)
    platform_min_gap_s: dict[str, int] = {
        "rumble": 2,
        "substack": 1,
    }
    platform_seen: dict[str, int] = {}
    staged: list[_ScrapeSignature] = []
    for idx, (platform, sig) in enumerate(scrape_signatures):
        stage = idx // batch_size
        batch_delay = int(stage * pause_s)
        seen_count = platform_seen.get(platform, 0)
        gap = platform_min_gap_s.get(platform, 0)
        platform_delay = seen_count * gap
        delay = max(batch_delay, platform_delay)
        platform_seen[platform] = seen_count + 1
        queue = scrape_queue_for_platform(platform)
        options: dict[str, object] = {"countdown": delay}
        if queue is not None:
            options["queue"] = queue
        staged.append(sig.set(**options))
    return staged


def _enabled_platforms() -> frozenset[str]:
    """Return the set of platform names that are not slot-disabled (limit != 0)."""
    runtime = get_runtime_settings()
    enabled: set[str] = set()
    if runtime.scrape_platform_slot_limit_rumble != 0:
        enabled.add("rumble")
    if runtime.scrape_platform_slot_limit_substack != 0:
        enabled.add("substack")
    return frozenset(enabled)


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
    base_query = (
        client.table("channels")
        .select("id,gate0_status,gate0_checked_at")
        .eq("is_active", True)
        .eq("has_been_scraped", True)
    )
    all_channels: list[dict] = []
    _page_size = 1000
    _offset = 0
    while True:
        batch = base_query.range(_offset, _offset + _page_size - 1).execute().data or []
        all_channels.extend(batch)
        if len(batch) < _page_size:
            break
        _offset += _page_size
    due_channels: list[tuple[int, str]] = []
    for channel in all_channels:
        priority = _gate0_priority(channel)
        if priority is None:
            continue
        due_channels.append((priority, str(channel["id"])))

    limit = get_runtime_settings().gate0_daily_queue_limit
    for _, channel_id in sorted(due_channels)[:limit]:
        run_gate0.apply_async(args=[channel_id, False], queue=QUEUE_GATE0)

    return min(len(due_channels), limit)


def _channel_scrape_priority(row: dict[str, object], platform_rank: dict[str, int]) -> tuple:
    """Composite sort key for daily scrape ordering (higher = scrape first).

    Weights:
      - evidence_count  : how many times independently discovered (strongest signal)
      - quality_tier    : SERP-scored tier from discovery
      - confidence      : discovery confidence score
      - niche_hint      : has a known pre-classification niche (not Unknown)
      - platform_rank   : configured platform priority (lower index = higher priority)
    """
    tier_map = {"high": 2, "medium": 1, "low": 0}
    evidence = min(int(row.get("discovery_evidence_count") or 1), 10)
    tier = tier_map.get(str(row.get("discovery_quality_tier") or ""), 0)
    confidence = float(row.get("discovery_confidence") or 0.0)
    hint = row.get("discovery_niche_hint")
    has_niche = (
        1 if isinstance(hint, list) and hint and hint != ["Unknown / Needs Review"] else 0
    )
    platform = str(row.get("platform") or "")
    p_rank = platform_rank.get(platform, 99)
    # Sort descending on quality signals, ascending on platform_rank.
    return (-evidence, -tier, -confidence, -has_niche, p_rank)


def _prioritize_channels_for_scrape(
    channels: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return never-scraped channels sorted by discovery quality (best first).

    Uses last_scraped_at from the channels row directly — no channel_snapshots
    lookup needed, eliminating N+1 Supabase queries at orchestration time.
    """
    runtime = get_runtime_settings()
    platform_rank = {
        platform: index for index, platform in enumerate(runtime.scrape_platform_priority)
    }
    never_scraped = [
        row for row in channels
        if (row.get("has_been_scraped") is False)
        or _parse_datetime(row.get("last_scraped_at")) is None
    ]
    never_scraped.sort(key=lambda row: _channel_scrape_priority(row, platform_rank))
    return never_scraped


@celery_app.task(name="scraper.tasks.run_post_scrape_tasks")
def run_post_scrape_tasks() -> dict[str, object]:
    """Run Gate 0 checks and channel classification after scraping completes."""
    try:
        gate0_queued = _queue_due_gate0_checks()
    except APIError as exc:
        logger.error("Failed to queue Gate 0 checks: %s", exc, exc_info=True)
        gate0_queued = 0

    classify_task_id = None
    try:
        classify_task = classify_channels.apply_async(queue=QUEUE_CLASSIFY)
        classify_task_id = classify_task.id
    except Exception as exc:
        logger.error("Failed to dispatch classify_channels task: %s", exc, exc_info=True)

    return {
        "gate0_queued": gate0_queued,
        "classify_task_id": classify_task_id,
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
    """Select clean, scraped, metric-rich channels for weekly velocity snapshots.

    Uses last_scraped_at from the channels row directly — no snapshot lookup.
    """
    now = datetime.now(timezone.utc)
    runtime = get_runtime_settings()
    stale_age = timedelta(hours=max(0, runtime.velocity_weekly_stale_hours))
    platform_rank = {
        platform: index for index, platform in enumerate(runtime.scrape_platform_priority)
    }
    selected: list[tuple[datetime, dict[str, object]]] = []
    for row in channels:
        last_scraped = _parse_datetime(row.get("last_scraped_at"))
        if last_scraped is not None and now - last_scraped < stale_age:
            continue
        if _passes_weekly_velocity_threshold(row):
            selected.append((last_scraped or datetime.min.replace(tzinfo=timezone.utc), row))

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
        base_q = (
            client.table("channels")
            .select(
                "id,channel_url,platform,subscriber_count,avg_views,avg_comments,"
                "comment_tier,has_been_scraped,discovery_status,gate0_status,"
                "last_scraped_at"
            )
            .eq("is_active", True)
            .eq("gate0_status", "clean")
            .eq("has_been_scraped", True)
            .eq("discovery_status", "scraped")
            .not_.is_("subscriber_count", "null")
            .not_.is_("avg_views", "null")
            .not_.is_("avg_comments", "null")
        )
        all_rows: list[dict] = []
        _page_size = 1000
        _offset = 0
        while True:
            batch = base_q.range(_offset, _offset + _page_size - 1).execute().data or []
            all_rows.extend(batch)
            if len(batch) < _page_size:
                break
            _offset += _page_size
        channels = _select_weekly_velocity_channels(all_rows)
    except APIError as exc:
        logger.error("Failed to fetch weekly velocity channels: %s", exc, exc_info=True)
        return {"queued": 0, "error": str(exc)}

    enabled_platforms = _enabled_platforms()
    scrape_signatures: list[tuple[str, _ScrapeSignature]] = []
    for channel in channels:
        channel_url = str(channel.get("channel_url") or "")
        platform = str(channel.get("platform") or "")
        if not channel_url:
            continue
        if platform not in enabled_platforms:
            continue
        if platform == "rumble":
            scrape_signatures.append((platform, scrape_rumble_channel.s(channel_url)))
        elif platform == "substack":
            scrape_signatures.append((platform, scrape_substack_channel.s(channel_url)))
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


@celery_app.task(name="scraper.tasks.dispatch_daily_scrapes")
def dispatch_daily_scrapes() -> dict[str, object]:
    """Fetch active channels and dispatch the daily scrape chord.

    Runs after discovery completes so newly found channels are included in the
    batch alongside the existing backlog, sorted by quality priority.
    """
    try:
        client = get_supabase_client()
        base_q = (
            client.table("channels")
            .select(
                "id,channel_url,platform,subscriber_count,avg_views,avg_comments,"
                "last_active_date,has_been_scraped,discovery_status,discovery_source,"
                "last_scraped_at,discovery_confidence,discovery_quality_tier,"
                "discovery_evidence_count,discovery_niche_hint"
            )
            .eq("is_active", True)
        )
        all_rows = []
        _page_size = 1000
        _offset = 0
        while True:
            batch = base_q.range(_offset, _offset + _page_size - 1).execute().data or []
            all_rows.extend(batch)
            if len(batch) < _page_size:
                break
            _offset += _page_size
        channels = _prioritize_channels_for_scrape(all_rows)
    except APIError as exc:
        logger.error("Failed to fetch active channel URLs: %s", exc, exc_info=True)
        return {"queued": 0, "error": str(exc)}

    enabled_platforms = _enabled_platforms()
    scrape_signatures: list[tuple[str, _ScrapeSignature]] = []
    for channel in channels:
        channel_url = str(channel.get("channel_url") or "")
        platform = str(channel.get("platform") or "")
        if not channel_url:
            continue
        if platform not in enabled_platforms:
            continue
        if platform == "rumble":
            scrape_signatures.append((platform, scrape_rumble_channel.s(channel_url)))
        elif platform == "substack":
            scrape_signatures.append((platform, scrape_substack_channel.s(channel_url)))
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
        "Queued daily scrape workflow: scrapes=%d callback=%s",
        queued,
        workflow.id,
    )
    return {
        "queued": queued,
        "workflow_task_id": workflow.id,
    }


@celery_app.task(name="scraper.tasks.run_daily_scrape")
def run_daily_scrape() -> dict[str, object]:
    """Kick off the daily scrape workflow.

    If discovery is enabled, dispatches a chain: discover → dispatch_daily_scrapes.
    Otherwise dispatches dispatch_daily_scrapes directly. Returns immediately so
    the worker-discovery slot is not blocked during the long discovery phase.
    """
    logger.info("Starting daily scrape workflow")
    runtime = get_runtime_settings()
    if runtime.discovery_enabled:
        workflow = chain(
            discover_channels.si(queue_scrapes=False),
            dispatch_daily_scrapes.si(),
        ).delay()
        logger.info("Dispatched discovery → scrape chain: %s", workflow.id)
        return {"chain_id": workflow.id, "discovery_enabled": True}

    task = dispatch_daily_scrapes.delay()
    logger.info("Dispatched scrape dispatch (discovery disabled): %s", task.id)
    return {"task_id": task.id, "discovery_enabled": False}

