"""Lookalike service - seed persistence, synchronous matching, and result reads."""

from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

from postgrest.exceptions import APIError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.exceptions import SupabaseError
from core.logging import get_logger
from core.supabase import supabase_admin
from models.lookalike import (
    ChannelLookalikeMatch,
    ChannelLookalikeResponse,
    LookalikeSearchRequest,
    LookalikeSearchResponse,
)
from services import admin_service
from shared.lookalike_matching import (
    build_niche_subscriber_matches_for_seed as _build_niche_subscriber_matches_for_seed,
    dedupe_matches as _dedupe_matches,
    find_seed_channel as _find_seed_channel,
    stamp_matches as _stamp_matches,
    is_similar_subscribers as _shared_is_similar_subscribers,
)

logger = get_logger(__name__)
_LOOKALIKE_MATCH_SELECT = "id,name,niche_tags,subscriber_count"
_LOOKALIKE_CHANNEL_SELECT = (
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


def _is_similar_subscribers(
    seed_count: object,
    candidate_count: object,
    band: float = 0.10,
) -> bool:
    """Compatibility wrapper kept for existing unit tests."""
    return _shared_is_similar_subscribers(seed_count, candidate_count, band)

def _fetch_lookalike_candidate_channels() -> list[dict[str, object]]:
    """Use the same quality gates as dashboard table channels."""
    result = (
        supabase_admin.table("channels")
        .select(_LOOKALIKE_MATCH_SELECT)
        .eq("is_active", True)
        .eq("dashboard_eligible", True)
        .execute()
    )
    return result.data or []


def _fetch_seed_resolution_channels() -> list[dict[str, object]]:
    """Use all active channels for seed name resolution."""
    result = (
        supabase_admin.table("channels")
        .select(_LOOKALIKE_MATCH_SELECT)
        .eq("is_active", True)
        .execute()
    )
    return result.data or []


def _enrich_matches_with_channels(
    matches: list[dict[str, object]],
    seed_map: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    if not matches:
        return []
    channel_ids = [match["matched_channel_id"] for match in matches]
    channels_result = (
        supabase_admin.table("channels")
        .select(_LOOKALIKE_CHANNEL_SELECT)
        .in_("id", channel_ids)
        .execute()
    )
    channels = channels_result.data or []
    channel_map = {channel["id"]: channel for channel in channels}
    enriched: list[dict[str, object]] = []
    for match in matches:
        row = dict(match)
        row["channel"] = channel_map.get(row.get("matched_channel_id"))
        if seed_map is not None:
            row["seed"] = seed_map.get(str(row.get("seed_id")))
        enriched.append(row)
    return enriched


async def queue_lookalike_search(
    body: LookalikeSearchRequest,
    user_id: str,
) -> LookalikeSearchResponse:
    """Compute matches synchronously and return immediate (ephemeral) results."""
    if not admin_service.is_feature_enabled("lookalike"):
        return LookalikeSearchResponse(
            message="Lookalike workflows are disabled in system settings.",
            task_id="",
            seed_count=len(body.seed_names),
            results=[],
        )

    try:
        seed_resolution_channels = _fetch_seed_resolution_channels()
        candidate_channels = _fetch_lookalike_candidate_channels()

        all_matches: list[dict[str, object]] = []
        for seed_name in body.seed_names:
            if not seed_name:
                continue
            seed_channel = _find_seed_channel(seed_name, seed_resolution_channels)
            if seed_channel is None:
                continue
            seed_id = str(uuid4())
            all_matches.extend(
                _build_niche_subscriber_matches_for_seed(
                    seed_id,
                    seed_channel,
                    candidate_channels,
                )
            )

        unique_matches = _dedupe_matches(all_matches)
        ephemeral_matches = _stamp_matches(unique_matches)
        enriched = _enrich_matches_with_channels(ephemeral_matches, seed_map=None)
    except APIError as exc:
        logger.error("Failed synchronous lookalike compute: %s", exc, exc_info=True)
        raise SupabaseError(f"Failed to compute lookalike search: {exc}") from exc

    return LookalikeSearchResponse(
        message="Lookalike search completed",
        task_id="",
        seed_count=len(body.seed_names),
        results=enriched,
    )


async def get_lookalike_results_for_user(user_id: str) -> list[dict[str, object]]:
    """Ephemeral mode: no persisted user lookalike history."""
    return []


async def get_lookalikes_for_channel(channel_id: UUID) -> ChannelLookalikeResponse:
    """Compute lookalikes for one channel using niche overlap + subscriber similarity."""
    try:
        seed_result = (
            supabase_admin.table("channels")
            .select(_LOOKALIKE_MATCH_SELECT)
            .eq("id", str(channel_id))
            .maybe_single()
            .execute()
        )
        seed_channel = seed_result.data
        if seed_channel is None:
            return ChannelLookalikeResponse(seed_channel_id=channel_id, matches=[])

        channels = _fetch_lookalike_candidate_channels()
        synthetic_seed_id = str(channel_id)
        matches = _build_niche_subscriber_matches_for_seed(
            synthetic_seed_id,
            seed_channel,
            channels,
        )
        enriched = _enrich_matches_with_channels(matches)
        detail_matches = [
            ChannelLookalikeMatch(
                matched_channel_id=row["matched_channel_id"],
                match_type=row["match_type"],
                match_detail=row.get("match_detail"),
                channel=row["channel"],
            )
            for row in enriched
            if row.get("channel") is not None
        ]
        return ChannelLookalikeResponse(
            seed_channel_id=channel_id,
            matches=detail_matches,
        )
    except APIError as exc:
        logger.error("Failed to fetch channel lookalikes for %s: %s", channel_id, exc, exc_info=True)
        raise SupabaseError(f"Failed to fetch channel lookalikes: {exc}") from exc
