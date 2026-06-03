"""Channel service - Supabase queries for channels table."""

from datetime import date, datetime, timedelta, timezone
from math import ceil, floor
from uuid import UUID

from postgrest.exceptions import APIError

from core.exceptions import NotFoundError, SupabaseError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.channel import ChannelFilters, ChannelWithMetrics, Gate0Status

logger = get_logger(__name__)

# Canonical source table. This service must not depend on the retired
# `channel_discovery` view.
_CHANNELS_TABLE = "channels"
_CHANNEL_LIST_SELECT = (
    "id,platform,channel_url,name,subscriber_count,avg_views,avg_comments,"
    "comment_tier,posts_per_week,last_active_date,niche_tags,is_active,"
    "gate0_status,gate0_checked_at,secondary_urls,do_not_contact,"
    "has_been_scraped,discovery_status,"
    "last_scrape_error,dashboard_metrics_complete,dashboard_url_valid,"
    "dashboard_eligible,engagement_rate,view_velocity_30d,view_velocity_90d,"
    "comment_velocity_30d,comment_velocity_90d,velocity_computed_at,"
    "gate0_result_id,gate0_search_query,gate0_result_status,"
    "gate0_flagged_brand,gate0_source_url,ai_summary,created_at,updated_at"
)
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
    "recent_videos",
    "is_active",
    "gate0_status",
    "gate0_checked_at",
    "secondary_urls",
    "do_not_contact",
    "has_been_scraped",
    "discovery_status",
    "last_scrape_error",
    "dashboard_metrics_complete",
    "dashboard_url_valid",
    "dashboard_eligible",
    "engagement_rate",
    "view_velocity_30d",
    "view_velocity_90d",
    "comment_velocity_30d",
    "comment_velocity_90d",
    "velocity_computed_at",
    "gate0_result_id",
    "gate0_search_query",
    "gate0_result_status",
    "gate0_flagged_brand",
    "gate0_source_url",
    "ai_summary",
    "created_at",
    "updated_at",
}

_BROAD_CATEGORIES = {
    "Prepper / Survival",
    "Financial / Macro",
    "Conservative Politics",
    "Health / Wellness",
    "Homesteading",
    "Crypto / Alternative Assets",
    "Religious / Values-Based",
    "News / Commentary",
    "Unknown / Needs Review",
}
_NORMALIZED_BROAD_CATEGORY_LOOKUP: dict[str, str] = {
    value.lower(): value for value in _BROAD_CATEGORIES
}


def _canonicalize_niche_tag(tag: str | None) -> str:
    if not tag or not tag.strip():
        return "Unknown / Needs Review"
    normalized = tag.strip().lower()
    return _NORMALIZED_BROAD_CATEGORY_LOOKUP.get(normalized, "Unknown / Needs Review")


def _normalize_filter_niche_tags(tags: list[str]) -> list[str]:
    normalized = {_canonicalize_niche_tag(raw_tag) for raw_tag in tags}
    return sorted(normalized, key=lambda value: value.lower())


def _canonical_niche_tags_for_row(row: dict[str, object]) -> set[str]:
    tags = row.get("niche_tags")
    if not isinstance(tags, list) or len(tags) == 0:
        return {"Unknown / Needs Review"}
    return {
        _canonicalize_niche_tag(raw_tag if isinstance(raw_tag, str) else None)
        for raw_tag in tags
    }


def _row_matches_category_tags(row: dict[str, object], category_tags: list[str]) -> bool:
    filter_tags = set(_normalize_filter_niche_tags(category_tags))
    row_tags = _canonical_niche_tags_for_row(row)
    return len(filter_tags.intersection(row_tags)) > 0


def _fetch_channels_by_ids_ordered(channel_ids: list[str]) -> list[dict[str, object]]:
    if not channel_ids:
        return []
    result = (
        supabase_admin.table(_CHANNELS_TABLE)
        .select(_CHANNEL_LIST_SELECT)
        .in_("id", channel_ids)
        .execute()
    )
    rows = result.data or []
    row_by_id = {str(row.get("id")): row for row in rows}
    return [row_by_id[channel_id] for channel_id in channel_ids if channel_id in row_by_id]


def _fetch_all_rows(base_query, batch_size: int = 1000) -> list[dict]:
    """Fetch every row matching base_query by paginating in batches.

    Supabase/PostgREST caps unranged responses at max_rows (default 1000).
    Use this whenever you need the full result set rather than a single page.
    """
    all_rows: list[dict] = []
    offset = 0
    while True:
        batch: list[dict] = base_query.range(offset, offset + batch_size - 1).execute().data or []
        all_rows.extend(batch)
        if len(batch) < batch_size:
            break
        offset += batch_size
    return all_rows


def _channel_from_discovery_row(row: dict[str, object]) -> ChannelWithMetrics:
    """Convert a channels row into the public response model."""
    channel_data = {key: row.get(key) for key in _CHANNEL_COLUMNS if key in row}

    velocity_data = None
    if row.get("velocity_computed_at") is not None:
        velocity_data = {
            "id": row.get("id"),
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
            "checked_at": row.get("gate0_checked_at"),
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
    """Fetch paginated, filtered channels from the channels table."""
    try:
        query = supabase_admin.table(_CHANNELS_TABLE).select(
            _CHANNEL_LIST_SELECT,
            count="exact",
        )
        query = query.eq("is_active", True)
        if filters.incomplete_only:
            query = query.eq("dashboard_eligible", False)
        else:
            query = query.eq("dashboard_eligible", True)

        if filters.platform is not None:
            query = query.eq("platform", filters.platform.value)

        if filters.comment_tier is not None:
            query = query.eq("comment_tier", filters.comment_tier.value)

        if filters.gate0_statuses:
            query = query.in_(
                "gate0_status",
                [status.value for status in filters.gate0_statuses],
            )

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
            # Exclude channels inactive for 90+ days; keep recently active channels.
            query = query.gte("last_active_date", cutoff)

        if filters.last_active_from is not None:
            query = query.gte(
                "last_active_date", filters.last_active_from.isoformat()
            )

        if filters.last_active_to is not None:
            query = query.lte(
                "last_active_date", filters.last_active_to.isoformat()
            )

        if filters.category_tags:
            normalized_category_tags = _normalize_filter_niche_tags(filters.category_tags)
            requires_canonical_fallback = "Unknown / Needs Review" in normalized_category_tags
        else:
            normalized_category_tags = []
            requires_canonical_fallback = False

        if filters.category_tags and not requires_canonical_fallback:
            query = query.overlaps("niche_tags", normalized_category_tags)

        if filters.category_tags and requires_canonical_fallback:
            candidate_query = supabase_admin.table(_CHANNELS_TABLE).select(
                "id,niche_tags,subscriber_count,avg_comments,"
                "avg_views,last_active_date,view_velocity_30d,"
                "view_velocity_90d,engagement_rate"
            )
            candidate_query = candidate_query.eq("is_active", True)
            if filters.incomplete_only:
                candidate_query = candidate_query.eq("dashboard_eligible", False)
            else:
                candidate_query = candidate_query.eq("dashboard_eligible", True)

            if filters.platform is not None:
                candidate_query = candidate_query.eq("platform", filters.platform.value)

            if filters.comment_tier is not None:
                candidate_query = candidate_query.eq("comment_tier", filters.comment_tier.value)

            if filters.gate0_statuses:
                candidate_query = candidate_query.in_(
                    "gate0_status",
                    [status.value for status in filters.gate0_statuses],
                )

            if filters.search_query is not None:
                term = filters.search_query.replace("%", "").replace(",", "").strip()
                if term:
                    pattern = f"%{term}%"
                    candidate_query = candidate_query.or_(
                        f"name.ilike.{pattern},channel_url.ilike.{pattern},description.ilike.{pattern}"
                    )

            if filters.min_subscriber_count is not None:
                candidate_query = candidate_query.gte(
                    "subscriber_count", filters.min_subscriber_count
                )
            if filters.max_subscriber_count is not None:
                candidate_query = candidate_query.lte(
                    "subscriber_count", filters.max_subscriber_count
                )
            if filters.min_avg_views is not None:
                candidate_query = candidate_query.gte("avg_views", ceil(filters.min_avg_views))
            if filters.max_avg_views is not None:
                candidate_query = candidate_query.lte("avg_views", floor(filters.max_avg_views))
            if filters.min_avg_comments is not None:
                candidate_query = candidate_query.gte("avg_comments", ceil(filters.min_avg_comments))
            if filters.max_avg_comments is not None:
                candidate_query = candidate_query.lte("avg_comments", floor(filters.max_avg_comments))
            if filters.inactive_filter:
                cutoff = (date.today() - timedelta(days=90)).isoformat()
                candidate_query = candidate_query.gte("last_active_date", cutoff)
            if filters.last_active_from is not None:
                candidate_query = candidate_query.gte(
                    "last_active_date", filters.last_active_from.isoformat()
                )
            if filters.last_active_to is not None:
                candidate_query = candidate_query.lte(
                    "last_active_date", filters.last_active_to.isoformat()
                )

            candidate_query = candidate_query.order(
                filters.sort_by,
                desc=(filters.sort_order == "desc"),
                nullsfirst=False,
            )
            candidate_rows = _fetch_all_rows(candidate_query)
            filtered_rows = [
                row for row in candidate_rows if _row_matches_category_tags(row, filters.category_tags or [])
            ]
            total = len(filtered_rows)
            start = (filters.page - 1) * filters.page_size
            end = start + filters.page_size
            page_ids = [str(row.get("id")) for row in filtered_rows[start:end] if row.get("id") is not None]
            records = _fetch_channels_by_ids_ordered(page_ids)
        else:
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


async def list_niche_tags(filters: ChannelFilters | None = None) -> tuple[list[str], list[dict[str, int | str]]]:
    """Return sorted distinct niche tags and per-tag channel counts, optionally scoped to active filters."""
    try:
        query = supabase_admin.table(_CHANNELS_TABLE).select("niche_tags")
        query = query.eq("is_active", True)

        if filters and filters.incomplete_only:
            query = query.eq("dashboard_eligible", False)
        else:
            query = query.eq("dashboard_eligible", True)

        if filters:
            if filters.platform is not None:
                query = query.eq("platform", filters.platform.value)
            if filters.comment_tier is not None:
                query = query.eq("comment_tier", filters.comment_tier.value)
            if filters.gate0_statuses:
                query = query.in_("gate0_status", [s.value for s in filters.gate0_statuses])
            if filters.search_query is not None:
                term = filters.search_query.replace("%", "").replace(",", "").strip()
                if term:
                    pattern = f"%{term}%"
                    query = query.or_(
                        f"name.ilike.{pattern},channel_url.ilike.{pattern},description.ilike.{pattern}"
                    )
            if filters.min_subscriber_count is not None:
                query = query.gte("subscriber_count", filters.min_subscriber_count)
            if filters.max_subscriber_count is not None:
                query = query.lte("subscriber_count", filters.max_subscriber_count)
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
                query = query.gte("last_active_date", cutoff)
            if filters.last_active_from is not None:
                query = query.gte("last_active_date", filters.last_active_from.isoformat())
            if filters.last_active_to is not None:
                query = query.lte("last_active_date", filters.last_active_to.isoformat())

        rows = _fetch_all_rows(query)
        unique: set[str] = set()
        counts: dict[str, int] = {}
        for row in rows:
            tags = row.get("niche_tags")
            seen_in_channel: set[str] = set()
            if not isinstance(tags, list) or len(tags) == 0:
                unknown_tag = "Unknown / Needs Review"
                unique.add(unknown_tag)
                seen_in_channel.add(unknown_tag)
            else:
                for raw_tag in tags:
                    tag = _canonicalize_niche_tag(raw_tag if isinstance(raw_tag, str) else None)
                    unique.add(tag)
                    seen_in_channel.add(tag)
            for tag in seen_in_channel:
                counts[tag] = counts.get(tag, 0) + 1

        sorted_tags = sorted(unique, key=lambda value: value.lower())
        tag_counts = [{"tag": tag, "count": counts.get(tag, 0)} for tag in sorted_tags]
        return sorted_tags, tag_counts
    except (APIError, TypeError, ValueError) as exc:
        logger.error("Failed to list niche tags: %s", exc, exc_info=True)
        raise SupabaseError(f"Failed to list niche tags: {exc}") from exc


async def list_gate0_status_counts() -> list[dict[str, int | str]]:
    """Return gate0 status counts across active, dashboard-eligible channels."""
    try:
        rows = _fetch_all_rows(
            supabase_admin.table(_CHANNELS_TABLE)
            .select("gate0_status")
            .eq("is_active", True)
            .eq("dashboard_eligible", True)
        )
        counts: dict[str, int] = {status.value: 0 for status in Gate0Status}
        for row in rows:
            raw_status = row.get("gate0_status")
            if isinstance(raw_status, str) and raw_status in counts:
                counts[raw_status] += 1
        order = ["unchecked", "pending", "clean", "needs_review", "dirty"]
        return [{"status": status, "count": counts.get(status, 0)} for status in order]
    except (APIError, TypeError, ValueError) as exc:
        logger.error("Failed to list gate0 status counts: %s", exc, exc_info=True)
        raise SupabaseError(f"Failed to list gate0 status counts: {exc}") from exc


async def get_channel_by_id(channel_id: UUID) -> ChannelWithMetrics | None:
    """Fetch a single channel by ID with consolidated velocity, Gate 0, and logs."""
    try:
        result = (
            supabase_admin.table("channels")
            .select("*")
            .eq("id", str(channel_id))
            .maybe_single()
            .execute()
        )

        if result.data is None:
            raise NotFoundError(f"Channel {channel_id} not found")

        row = result.data

        velocity_data = None
        if row.get("velocity_computed_at") is not None:
            velocity_data = {
                "id": row.get("id"),
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
                "checked_at": row.get("gate0_checked_at"),
                "search_query": row.get("gate0_search_query"),
                "result_status": row.get("gate0_result_status"),
                "flagged_brand": row.get("gate0_flagged_brand"),
                "source_url": row.get("gate0_source_url"),
            }

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


async def update_channel_do_not_contact(
    channel_id: UUID, do_not_contact: str | None
) -> ChannelWithMetrics:
    """Update a channel's do-not-contact status."""
    try:
        existing = (
            supabase_admin.table("channels")
            .select("id")
            .eq("id", str(channel_id))
            .maybe_single()
            .execute()
        )
        if existing.data is None:
            raise NotFoundError(f"Channel {channel_id} not found")

        supabase_admin.table("channels").update(
            {
                "do_not_contact": do_not_contact,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", str(channel_id)).execute()

        updated = await get_channel_by_id(channel_id)
        if updated is None:
            raise NotFoundError(f"Channel {channel_id} not found")
        logger.info(
            "Updated channel %s do_not_contact to %s", channel_id, do_not_contact
        )
        return updated
    except NotFoundError:
        raise
    except (APIError, TypeError, ValueError) as exc:
        logger.error(
            "Failed to update do_not_contact for %s: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to update do_not_contact: {exc}") from exc


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


async def delete_channel_history(channel_id: UUID) -> None:
    """Delete historical snapshot/log data and reset computed caches for a channel."""
    try:
        existing = (
            supabase_admin.table("channels")
            .select("id")
            .eq("id", str(channel_id))
            .maybe_single()
            .execute()
        )
        if existing.data is None:
            raise NotFoundError(f"Channel {channel_id} not found")

        supabase_admin.table("channel_snapshots").delete().eq(
            "channel_id", str(channel_id)
        ).execute()
        supabase_admin.table("scrape_logs").delete().eq(
            "channel_id", str(channel_id)
        ).execute()
        supabase_admin.table("gate0_results").delete().eq(
            "channel_id", str(channel_id)
        ).execute()

        supabase_admin.table("channels").update(
            {
                "has_been_scraped": False,
                "last_scrape_error": None,
                "view_velocity_30d": None,
                "view_velocity_90d": None,
                "comment_velocity_30d": None,
                "comment_velocity_90d": None,
                "velocity_computed_at": None,
                "gate0_checked_at": None,
                "gate0_result_id": None,
                "gate0_search_query": None,
                "gate0_result_status": None,
                "gate0_flagged_brand": None,
                "gate0_source_url": None,
                "gate0_status": "unchecked",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", str(channel_id)).execute()
    except NotFoundError:
        raise
    except (APIError, TypeError, ValueError) as exc:
        logger.error(
            "Failed to delete history for channel %s: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to delete channel history: {exc}") from exc


async def delete_channel_completely(channel_id: UUID) -> None:
    """Delete a channel and all related dependent records."""
    try:
        existing = (
            supabase_admin.table("channels")
            .select("id")
            .eq("id", str(channel_id))
            .maybe_single()
            .execute()
        )
        if existing.data is None:
            raise NotFoundError(f"Channel {channel_id} not found")

        supabase_admin.table("channel_snapshots").delete().eq(
            "channel_id", str(channel_id)
        ).execute()
        supabase_admin.table("scrape_logs").delete().eq(
            "channel_id", str(channel_id)
        ).execute()
        supabase_admin.table("gate0_results").delete().eq(
            "channel_id", str(channel_id)
        ).execute()
        supabase_admin.table("channels").delete().eq("id", str(channel_id)).execute()
    except NotFoundError:
        raise
    except (APIError, TypeError, ValueError) as exc:
        logger.error(
            "Failed to delete channel %s completely: %s",
            channel_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to delete channel completely: {exc}") from exc
