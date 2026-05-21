"""Channel service - Supabase queries for channel discovery."""

from datetime import date, datetime, timedelta, timezone
from math import ceil, floor
from uuid import UUID

from postgrest.exceptions import APIError

from core.exceptions import NotFoundError, SupabaseError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.channel import ChannelFilters, ChannelWithMetrics

logger = get_logger(__name__)

_CHANNEL_DISCOVERY_TABLE = "channel_discovery"
_CHANNEL_COLUMNS = {
    "id",
    "platform",
    "channel_url",
    "name",
    "description",
    "subscriber_count",
    "avg_views",
    "avg_comments",
    "comment_tier",
    "posts_per_week",
    "last_active_date",
    "contact_info",
    "niche_tags",
    "video_titles",
    "is_active",
    "is_55_plus",
    "gate0_status",
    "gate0_checked_at",
    "secondary_urls",
    "created_at",
    "updated_at",
}


def _channel_from_discovery_row(row: dict[str, object]) -> ChannelWithMetrics:
    """Convert a channel_discovery row into the public response model."""
    channel_data = {key: row.get(key) for key in _CHANNEL_COLUMNS}

    velocity_data = None
    if row.get("velocity_id") is not None:
        velocity_data = {
            "id": row.get("velocity_id"),
            "channel_id": row.get("id"),
            "computed_at": row.get("velocity_computed_at"),
            "view_velocity_30d": row.get("view_velocity_30d"),
            "view_velocity_90d": row.get("view_velocity_90d"),
            "comment_velocity_30d": row.get("comment_velocity_30d"),
            "comment_velocity_90d": row.get("comment_velocity_90d"),
        }

    gate0_data = None
    if row.get("gate0_result_id") is not None:
        gate0_data = {
            "id": row.get("gate0_result_id"),
            "channel_id": row.get("id"),
            "checked_at": row.get("gate0_result_checked_at"),
            "search_query": row.get("gate0_search_query"),
            "result_status": row.get("gate0_result_status"),
            "flagged_brand": row.get("gate0_flagged_brand"),
            "source_url": row.get("gate0_source_url"),
        }

    return ChannelWithMetrics(
        **channel_data,
        velocity=velocity_data,
        gate0=gate0_data,
    )


async def get_channels(
    filters: ChannelFilters,
) -> tuple[list[ChannelWithMetrics], int]:
    """Fetch paginated, filtered channels from the discovery view."""
    try:
        query = supabase_admin.table(_CHANNEL_DISCOVERY_TABLE).select(
            "*",
            count="exact",
        )
        query = query.eq("is_active", True)

        if filters.platform is not None:
            query = query.eq("platform", filters.platform.value)

        if filters.comment_tier is not None:
            query = query.eq("comment_tier", filters.comment_tier.value)
        # Removed default 'not null' filter to allow BitChute channels to show

        if filters.gate0_status is not None:
            query = query.eq("gate0_status", filters.gate0_status.value)

        if filters.is_55_plus is not None:
            query = query.eq("is_55_plus", filters.is_55_plus)

        if filters.niche_tag is not None:
            query = query.contains("niche_tags", [filters.niche_tag])

        if filters.search_query is not None:
            term = filters.search_query.replace("%", "").replace(",", "").strip()
            if term:
                pattern = f"%{term}%"
                query = query.or_(
                    f"name.ilike.{pattern},channel_url.ilike.{pattern},description.ilike.{pattern}"
                )

        if filters.min_subscriber_count is not None:
            query = query.gte(
                "subscriber_count", filters.min_subscriber_count
            )
        if filters.max_subscriber_count is not None:
            query = query.lte(
                "subscriber_count", filters.max_subscriber_count
            )
        if filters.min_avg_views is not None:
            query = query.gte("avg_views", ceil(filters.min_avg_views))
        if filters.max_avg_views is not None:
            query = query.lte("avg_views", floor(filters.max_avg_views))
        if filters.min_avg_comments is not None:
            query = query.gte("avg_comments", ceil(filters.min_avg_comments))
        if filters.max_avg_comments is not None:
            query = query.lte("avg_comments", floor(filters.max_avg_comments))

        if filters.inactive_filter:
            cutoff = (date.today() - timedelta(days=90)).isoformat()
            query = query.lte("last_active_date", cutoff)

        if filters.last_active_from is not None:
            query = query.gte(
                "last_active_date", filters.last_active_from.isoformat()
            )

        if filters.last_active_to is not None:
            query = query.lte(
                "last_active_date", filters.last_active_to.isoformat()
            )

        query = query.order(
            filters.sort_by,
            desc=(filters.sort_order == "desc"),
            nullsfirst=False,
        )

        start = (filters.page - 1) * filters.page_size
        end = start + filters.page_size - 1
        result = query.range(start, end).execute()
        total = result.count if result.count is not None else 0
        records = result.data or []

        return [_channel_from_discovery_row(row) for row in records], total

    except (APIError, TypeError, ValueError) as exc:
        logger.error("Failed to fetch channels: %s", exc, exc_info=True)
        raise SupabaseError(f"Failed to fetch channels: {exc}") from exc


async def list_niche_tags() -> list[str]:
    """Return sorted distinct niche tags across all channels."""
    try:
        result = (
            supabase_admin.table("channels")
            .select("niche_tags")
            .not_.is_("niche_tags", "null")
            .execute()
        )
        rows = result.data or []
        unique: set[str] = set()
        for row in rows:
            tags = row.get("niche_tags")
            if not isinstance(tags, list):
                continue
            for raw_tag in tags:
                if not isinstance(raw_tag, str):
                    continue
                tag = raw_tag.strip()
                if tag:
                    unique.add(tag)
        return sorted(unique, key=lambda value: value.lower())
    except (APIError, TypeError, ValueError) as exc:
        logger.error("Failed to list niche tags: %s", exc, exc_info=True)
        raise SupabaseError(f"Failed to list niche tags: {exc}") from exc


async def get_channel_by_id(channel_id: UUID) -> ChannelWithMetrics | None:
    """Fetch a single channel by ID with joined velocity, Gate 0, and logs."""
    try:
        result = (
            supabase_admin.table("channels")
            .select("*, velocity_scores(*), gate0_results(*)")
            .eq("id", str(channel_id))
            .maybe_single()
            .execute()
        )

        if result.data is None:
            raise NotFoundError(f"Channel {channel_id} not found")

        row = result.data

        velocity_data = None
        velocity_records = row.pop("velocity_scores", [])
        if velocity_records:
            velocity_records.sort(
                key=lambda v: v.get("computed_at", ""), reverse=True
            )
            velocity_data = velocity_records[0]

        gate0_data = None
        gate0_records = row.pop("gate0_results", [])
        if gate0_records:
            gate0_records.sort(
                key=lambda g: g.get("checked_at", ""), reverse=True
            )
            gate0_data = gate0_records[0]

        logs_result = (
            supabase_admin.table("scrape_logs")
            .select("*")
            .eq("channel_id", str(channel_id))
            .order("attempted_at", desc=True)
            .limit(10)
            .execute()
        )
        scrape_logs = logs_result.data or []

        return ChannelWithMetrics(
            **row,
            velocity=velocity_data,
            gate0=gate0_data,
            scrape_logs=scrape_logs,
        )

    except NotFoundError:
        raise
    except (APIError, TypeError, ValueError) as exc:
        logger.error(
            "Failed to fetch channel %s: %s", channel_id, exc, exc_info=True
        )
        raise SupabaseError(f"Failed to fetch channel: {exc}") from exc


async def update_channel_gate0_status(
    channel_id: UUID, status: str
) -> None:
    """Update a channel's Gate 0 status."""
    try:
        supabase_admin.table("channels").update(
            {
                "gate0_status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", str(channel_id)).execute()
        logger.info(
            "Updated channel %s gate0_status to %s", channel_id, status
        )
    except APIError as exc:
        logger.error(
            "Failed to update gate0 status for %s: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to update gate0 status: {exc}") from exc


async def upsert_channel(data: dict[str, object]) -> dict[str, object]:
    """Upsert a channel record using channel_url as the conflict key."""
    try:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        result = (
            supabase_admin.table("channels")
            .upsert(data, on_conflict="channel_url")
            .execute()
        )
        if result.data:
            return result.data[0]
        return {}
    except APIError as exc:
        logger.error("Failed to upsert channel: %s", exc, exc_info=True)
        raise SupabaseError(f"Failed to upsert channel: {exc}") from exc
