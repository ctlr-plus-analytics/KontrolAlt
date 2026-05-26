"""Lookalike service - seed persistence, synchronous matching, and result reads."""

from datetime import datetime, timezone
import re
from uuid import UUID

from postgrest.exceptions import APIError

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

logger = get_logger(__name__)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SUBSCRIBER_BAND = 0.10


def _normalize_name(value: str) -> str:
    return _NON_ALNUM_RE.sub(" ", value.lower()).strip()


def _tokenize(value: str) -> set[str]:
    normalized = _normalize_name(value)
    return {token for token in normalized.split() if len(token) >= 2}


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def _find_seed_channel(
    seed_name: str,
    channels: list[dict[str, object]],
) -> dict[str, object] | None:
    normalized_seed = _normalize_name(seed_name)
    seed_tokens = _tokenize(seed_name)

    for channel in channels:
        channel_name = str(channel.get("name") or "")
        if _normalize_name(channel_name) == normalized_seed:
            return channel

    best_channel: dict[str, object] | None = None
    best_score = 0.0
    for channel in channels:
        channel_name = str(channel.get("name") or "")
        channel_tokens = _tokenize(channel_name)
        if not channel_tokens or not seed_tokens:
            continue
        overlap = len(seed_tokens & channel_tokens)
        if overlap == 0:
            continue
        token_ratio = overlap / max(len(seed_tokens), 1)
        score = overlap + token_ratio
        if score > best_score:
            best_score = score
            best_channel = channel

    if best_channel is not None and (
        best_score >= 2.0 or (best_score >= 1.5 and len(seed_tokens) <= 2)
    ):
        return best_channel
    return None


def _is_similar_subscribers(
    seed_count: object,
    candidate_count: object,
    band: float = _SUBSCRIBER_BAND,
) -> bool:
    if not isinstance(seed_count, (int, float)) or not isinstance(
        candidate_count, (int, float)
    ):
        return False
    if seed_count <= 0 or candidate_count <= 0:
        return False
    lower = seed_count * (1 - band)
    upper = seed_count * (1 + band)
    return lower <= candidate_count <= upper


def _build_niche_subscriber_matches_for_seed(
    seed_id: str,
    seed_channel: dict[str, object],
    channels: list[dict[str, object]],
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    seed_channel_id = seed_channel["id"]
    seed_tags = set(_as_string_list(seed_channel.get("niche_tags")))
    seed_subscribers = seed_channel.get("subscriber_count")
    if not seed_tags:
        return matches

    for channel in channels:
        if channel["id"] == seed_channel_id:
            continue

        channel_tags = set(_as_string_list(channel.get("niche_tags")))
        overlap = seed_tags & channel_tags
        if len(overlap) < 1:
            continue

        candidate_subscribers = channel.get("subscriber_count")
        if not _is_similar_subscribers(seed_subscribers, candidate_subscribers):
            continue

        if not isinstance(seed_subscribers, (int, float)) or not isinstance(
            candidate_subscribers, (int, float)
        ):
            continue
        pct_delta = ((candidate_subscribers - seed_subscribers) / seed_subscribers) * 100
        detail = (
            f"Shared tags: {', '.join(sorted(overlap))} | "
            f"Subscribers: {int(seed_subscribers)} vs {int(candidate_subscribers)} "
            f"({pct_delta:+.2f}%)"
        )
        matches.append(
            {
                "seed_id": seed_id,
                "matched_channel_id": channel["id"],
                "match_type": "niche_overlap",
                "match_detail": detail,
            }
        )
    return matches


def _enrich_matches_with_channels(
    matches: list[dict[str, object]],
    seed_map: dict[str, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    if not matches:
        return []
    channel_ids = [match["matched_channel_id"] for match in matches]
    channels_result = (
        supabase_admin.table("channels")
        .select("*")
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
    """Save seeds, compute matches synchronously, and return immediate results."""
    if not admin_service.is_feature_enabled("lookalike"):
        return LookalikeSearchResponse(
            message="Lookalike workflows are disabled in system settings.",
            task_id="",
            seed_count=len(body.seed_names),
            results=[],
        )

    seed_ids: list[str] = []
    seed_map: dict[str, dict[str, object]] = {}

    for name in body.seed_names:
        try:
            result = (
                supabase_admin.table("seed_creators")
                .upsert(
                    {
                        "user_id": user_id,
                        "name": name,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    on_conflict="user_id,name",
                )
                .execute()
            )
        except APIError as exc:
            logger.error("Failed to upsert seed creator: %s", exc, exc_info=True)
            raise SupabaseError(f"Failed to save seed creator: {exc}") from exc

        if result.data:
            seed_row = result.data[0]
            seed_id = str(seed_row["id"])
            seed_ids.append(seed_id)
            seed_map[seed_id] = seed_row
        else:
            logger.warning("Seed upsert returned no row for user=%s name=%s", user_id, name)

    if not seed_ids:
        logger.error("No seed IDs resolved for lookalike search user=%s", user_id)
        return LookalikeSearchResponse(
            message=(
                "Lookalike search could not start because no valid seeds were persisted. "
                "Please retry."
            ),
            task_id="",
            seed_count=len(body.seed_names),
            results=[],
        )

    try:
        channels_result = supabase_admin.table("channels").select("*").execute()
        channels = channels_result.data or []

        all_matches: list[dict[str, object]] = []
        for seed_id in seed_ids:
            seed_name = str(seed_map.get(seed_id, {}).get("name") or "")
            if not seed_name:
                continue
            seed_channel = _find_seed_channel(seed_name, channels)
            if seed_channel is None:
                continue
            all_matches.extend(
                _build_niche_subscriber_matches_for_seed(seed_id, seed_channel, channels)
            )

        unique_matches: dict[tuple[str, str, str], dict[str, object]] = {}
        for match in all_matches:
            key = (
                str(match["seed_id"]),
                str(match["matched_channel_id"]),
                str(match["match_type"]),
            )
            if key not in unique_matches:
                unique_matches[key] = match

        persisted_matches: list[dict[str, object]] = []
        for match in unique_matches.values():
            row = dict(match)
            row["found_at"] = datetime.now(timezone.utc).isoformat()
            upsert_result = (
                supabase_admin.table("lookalike_matches")
                .upsert(
                    row,
                    on_conflict="seed_id,matched_channel_id,match_type",
                )
                .execute()
            )
            if upsert_result.data:
                persisted_matches.append(upsert_result.data[0])

        enriched = _enrich_matches_with_channels(persisted_matches, seed_map=seed_map)
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
    """Fetch all lookalike matches for a user's seed creators."""
    try:
        seeds_result = (
            supabase_admin.table("seed_creators")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        seeds = seeds_result.data or []
        if not seeds:
            return []

        seed_ids = [seed["id"] for seed in seeds]
        seed_map = {seed["id"]: seed for seed in seeds}

        matches_result = (
            supabase_admin.table("lookalike_matches")
            .select("*, channels(*)")
            .in_("seed_id", seed_ids)
            .execute()
        )
        matches = matches_result.data or []

        enriched: list[dict[str, object]] = []
        for match in matches:
            channel_data = match.pop("channels", None)
            match["channel"] = channel_data
            match["seed"] = seed_map.get(match.get("seed_id"))
            enriched.append(match)

        return enriched

    except APIError as exc:
        logger.error(
            "Failed to fetch lookalike results for user %s: %s",
            user_id,
            exc,
            exc_info=True,
        )
        raise SupabaseError(f"Failed to fetch lookalike results: {exc}") from exc


async def get_lookalikes_for_channel(channel_id: UUID) -> ChannelLookalikeResponse:
    """Compute lookalikes for one channel using niche overlap + subscriber similarity."""
    try:
        seed_result = (
            supabase_admin.table("channels")
            .select("*")
            .eq("id", str(channel_id))
            .maybe_single()
            .execute()
        )
        seed_channel = seed_result.data
        if seed_channel is None:
            return ChannelLookalikeResponse(seed_channel_id=channel_id, matches=[])

        channels_result = supabase_admin.table("channels").select("*").execute()
        channels = channels_result.data or []
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
