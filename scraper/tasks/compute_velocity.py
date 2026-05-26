"""Celery tasks: compute velocity scores."""

import logging
from datetime import datetime, timedelta, timezone

from celery import Task
from postgrest.exceptions import APIError

from worker import celery_app
from core.supabase import get_supabase_client
from core.runtime_settings import get_runtime_settings
from models import VelocityTaskResult

logger = logging.getLogger(__name__)


def _find_snapshot_for_date(
    snapshots: list[dict[str, object]], target_dt: datetime
) -> dict[str, object] | None:
    """Find a snapshot captured on or near the target UTC date (±1 day)."""
    if target_dt.tzinfo is None:
        target_dt = target_dt.replace(tzinfo=timezone.utc)
    target_date = target_dt.astimezone(timezone.utc).date()
    candidates: list[tuple[int, dict[str, object]]] = []

    for snap in snapshots:
        scraped_at = snap.get("scraped_at", "")
        if isinstance(scraped_at, str):
            try:
                snap_dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
            except ValueError:
                continue
        elif isinstance(scraped_at, datetime):
            snap_dt = scraped_at
        else:
            continue

        if snap_dt.tzinfo is None:
            snap_dt = snap_dt.replace(tzinfo=timezone.utc)
        snap_date = snap_dt.astimezone(timezone.utc).date()
        delta = abs((snap_date - target_date).days)
        if delta <= 1:
            candidates.append((delta, snap))

    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def _parse_snapshot_datetime(snapshot: dict[str, object]) -> datetime:
    """Parse a snapshot timestamp, falling back to now for malformed rows."""
    scraped_at = snapshot.get("scraped_at", "")
    if isinstance(scraped_at, str):
        try:
            parsed = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    elif isinstance(scraped_at, datetime):
        parsed = scraped_at
    else:
        return datetime.now(timezone.utc)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _as_float(value: object) -> float | None:
    """Convert stored numeric values into floats for velocity math."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None




def _safe_velocity(current: object, past: object) -> float | None:
    """Compute velocity percentage, guarding against missing or zero history."""
    current_float = _as_float(current)
    past_float = _as_float(past)
    if current_float is None or past_float is None or past_float == 0:
        return None
    return round(((current_float - past_float) / past_float) * 100, 2)


def _empty_velocity_data(channel_id: str) -> dict[str, object]:
    """Build a null velocity row for channels still collecting history."""
    return {
        "channel_id": channel_id,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "view_velocity_30d": None,
        "view_velocity_90d": None,
        "comment_velocity_30d": None,
        "comment_velocity_90d": None,
    }


def _compute_velocity_sync(channel_id: str) -> dict[str, object]:
    """Compute and upsert velocity for a single channel."""
    client = get_supabase_client()
    result = (
        client.table("channel_snapshots")
        .select("*")
        .eq("channel_id", channel_id)
        .order("scraped_at", desc=False)
        .execute()
    )
    snapshots = result.data or []

    velocity_data = _empty_velocity_data(channel_id)
    if snapshots:
        current = snapshots[-1]
        current_dt = _parse_snapshot_datetime(current)
        historical = snapshots[:-1]
        snap_30d = _find_snapshot_for_date(
            historical, current_dt - timedelta(days=30)
        )
        snap_90d = _find_snapshot_for_date(
            historical, current_dt - timedelta(days=90)
        )

        velocity_data.update(
            {
                "view_velocity_30d": _safe_velocity(
                    current.get("avg_views"),
                    snap_30d.get("avg_views") if snap_30d else None,
                ),
                "view_velocity_90d": _safe_velocity(
                    current.get("avg_views"),
                    snap_90d.get("avg_views") if snap_90d else None,
                ),
                "comment_velocity_30d": _safe_velocity(
                    current.get("avg_comments"),
                    snap_30d.get("avg_comments") if snap_30d else None,
                ),
                "comment_velocity_90d": _safe_velocity(
                    current.get("avg_comments"),
                    snap_90d.get("avg_comments") if snap_90d else None,
                ),
            }
        )

    update_payload = {
        "view_velocity_30d": velocity_data["view_velocity_30d"],
        "view_velocity_90d": velocity_data["view_velocity_90d"],
        "comment_velocity_30d": velocity_data["comment_velocity_30d"],
        "comment_velocity_90d": velocity_data["comment_velocity_90d"],
        "velocity_computed_at": velocity_data["computed_at"],
    }
    client.table("channels").update(update_payload).eq("id", channel_id).execute()
    logger.info("Velocity computed for channel %s", channel_id)
    return VelocityTaskResult(
        status="computed",
        **velocity_data,
    ).model_dump(mode="json")


@celery_app.task(
    bind=True,
    max_retries=2,
    name="scraper.tasks.compute_velocity",
)
def compute_velocity(self: Task, channel_id: str) -> dict[str, object]:
    """Compute velocity metrics for a single channel."""
    logger.info("Computing velocity for channel %s", channel_id)
    try:
        return _compute_velocity_sync(channel_id)
    except (APIError, TypeError, ValueError) as exc:
        logger.error(
            "Velocity computation failed for %s: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="scraper.tasks.compute_velocity_all")
def compute_velocity_all(qualified_only: bool = False) -> dict[str, object]:
    """Fetch channel IDs and dispatch individual velocity tasks.

    When qualified_only is true, only clean leads with complete metrics and
    stronger engagement are included. That keeps velocity computation aligned
    with the weekly refresh lane.
    """
    logger.info("Starting batch velocity computation")
    try:
        client = get_supabase_client()
        query = client.table("channels").select(
            "id,gate0_status,has_been_scraped,discovery_status,"
            "subscriber_count,avg_views,avg_comments,comment_tier"
        ).eq("is_active", True)
        if qualified_only:
            query = (
                query.eq("gate0_status", "clean")
                .eq("has_been_scraped", True)
                .eq("discovery_status", "scraped")
                .not_.is_("subscriber_count", "null")
                .not_.is_("avg_views", "null")
                .not_.is_("avg_comments", "null")
            )
        result = query.execute()
        channel_ids = []
        for row in result.data or []:
            if qualified_only and not _is_velocity_qualified(row):
                continue
            channel_ids.append(row["id"])
    except APIError as exc:
        logger.error("Failed to fetch channel IDs: %s", exc)
        return {"queued": 0, "error": str(exc)}

    for channel_id in channel_ids:
        compute_velocity.delay(channel_id)

    logger.info("Queued %d velocity computations", len(channel_ids))
    return {"queued": len(channel_ids), "qualified_only": qualified_only}


def _is_velocity_qualified(channel: dict[str, object]) -> bool:
    """Return True for clean, scraped channels with stronger metrics."""
    runtime = get_runtime_settings()
    if channel.get("comment_tier") in {"sweet_spot", "whale"}:
        return True
    try:
        if (
            float(channel.get("avg_comments") or 0)
            >= runtime.velocity_weekly_min_avg_comments
        ):
            return True
        if (
            runtime.velocity_weekly_min_avg_views > 0
            and float(channel.get("avg_views") or 0)
            >= runtime.velocity_weekly_min_avg_views
        ):
            return True
        if (
            runtime.velocity_weekly_min_subscribers > 0
            and int(channel.get("subscriber_count") or 0)
            >= runtime.velocity_weekly_min_subscribers
        ):
            return True
    except (TypeError, ValueError):
        return False
    return False
