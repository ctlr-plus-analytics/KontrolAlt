"""Celery task: find lookalike channels for seed creators."""

import logging
import re
from datetime import datetime, timezone

from postgrest.exceptions import APIError

from worker import celery_app
from core.supabase import get_supabase_client
from core.system_settings import get_runtime_settings
from models import LookalikeTaskResult

logger = logging.getLogger(__name__)


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_name(value: str) -> str:
    """Normalize names for robust seed->channel matching."""
    return _NON_ALNUM_RE.sub(" ", value.lower()).strip()


def _tokenize(value: str) -> set[str]:
    """Tokenize normalized text and drop short/empty tokens."""
    normalized = _normalize_name(value)
    return {token for token in normalized.split() if len(token) >= 2}


def _as_string_list(value: object) -> list[str]:
    """Normalize a text[] or text value into a string list."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def _find_seed_channel(
    seed_name_lower: str, channels: list[dict[str, object]]
) -> dict[str, object] | None:
    """Return the best matching seed channel by normalized name/tokens."""
    normalized_seed = _normalize_name(seed_name_lower)
    seed_tokens = _tokenize(seed_name_lower)

    # First pass: normalized exact match.
    for channel in channels:
        channel_name = str(channel.get("name") or "")
        if _normalize_name(channel_name) == normalized_seed:
            return channel

    # Fallback: choose the strongest token overlap.
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

    # Require meaningful overlap to avoid random attachment.
    if best_channel is not None and (
        best_score >= 2.0 or (best_score >= 1.5 and len(seed_tokens) <= 2)
    ):
        return best_channel

    return None


def _append_guest_matches(
    seed_id: str,
    seed_name_lower: str,
    seed_channel_id: str | None,
    channels: list[dict[str, object]],
    matches: list[dict[str, object]],
) -> None:
    """Append guest appearance matches for one seed."""
    for channel in channels:
        if seed_channel_id is not None and channel.get("id") == seed_channel_id:
            continue

        for title in _as_string_list(channel.get("video_titles"))[:20]:
            if seed_name_lower in title.lower():
                matches.append(
                    {
                        "seed_id": seed_id,
                        "matched_channel_id": channel["id"],
                        "match_type": "guest_appearance",
                        "match_detail": title,
                    }
                )
                break


def _append_niche_matches(
    seed_id: str,
    seed_channel: dict[str, object] | None,
    channels: list[dict[str, object]],
    matches: list[dict[str, object]],
) -> None:
    """Append 1+ tag niche overlap matches for one seed."""
    if seed_channel is None:
        return

    seed_channel_id = seed_channel["id"]
    seed_tags = set(_as_string_list(seed_channel.get("niche_tags")))
    if not seed_tags:
        return

    for channel in channels:
        if channel["id"] == seed_channel_id:
            continue

        channel_tags = set(_as_string_list(channel.get("niche_tags")))
        overlap = seed_tags & channel_tags
        if len(overlap) >= 1:
            matches.append(
                {
                    "seed_id": seed_id,
                    "matched_channel_id": channel["id"],
                    "match_type": "niche_overlap",
                    "match_detail": ", ".join(sorted(overlap)),
                }
            )


def _find_lookalikes_sync(seed_ids: list[str]) -> dict[str, object]:
    """Find lookalike channels using guest appearances and niche overlap."""
    runtime = get_runtime_settings()
    if not runtime.lookalike_enabled:
        return LookalikeTaskResult(matches_found=0).model_dump(mode="json")

    client = get_supabase_client()
    all_matches: list[dict[str, object]] = []

    channels_result = client.table("channels").select("*").execute()
    channels = channels_result.data or []

    for seed_id in seed_ids:
        seed_result = (
            client.table("seed_creators")
            .select("*")
            .eq("id", seed_id)
            .maybe_single()
            .execute()
        )
        if seed_result.data is None:
            logger.warning("Seed %s not found, skipping", seed_id)
            continue

        seed_name = str(seed_result.data["name"])
        seed_name_lower = seed_name.lower()
        seed_channel = _find_seed_channel(seed_name_lower, channels)
        seed_channel_id = (
            str(seed_channel["id"]) if seed_channel is not None else None
        )

        _append_guest_matches(
            seed_id,
            seed_name_lower,
            seed_channel_id,
            channels,
            all_matches,
        )
        _append_niche_matches(seed_id, seed_channel, channels, all_matches)

    unique_matches: dict[tuple[str, str, str], dict[str, object]] = {}
    for match in all_matches:
        key = (
            str(match["seed_id"]),
            str(match["matched_channel_id"]),
            str(match["match_type"]),
        )
        # Keep first deterministic detail per unique match key.
        if key not in unique_matches:
            unique_matches[key] = match

    inserted = 0
    for match in unique_matches.values():
        try:
            match["found_at"] = datetime.now(timezone.utc).isoformat()
            client.table("lookalike_matches").upsert(
                match,
                on_conflict="seed_id,matched_channel_id,match_type",
            ).execute()
            inserted += 1
        except APIError as exc:
            logger.error("Failed to upsert lookalike match: %s", exc)

    return LookalikeTaskResult(matches_found=inserted).model_dump(mode="json")


@celery_app.task(name="scraper.tasks.find_lookalikes")
def find_lookalikes(seed_ids: list[str]) -> dict[str, object]:
    """Find lookalike channels for the given seed creator IDs."""
    logger.info("Starting lookalike search for %d seeds", len(seed_ids))
    try:
        return _find_lookalikes_sync(seed_ids)
    except (APIError, KeyError, TypeError, ValueError) as exc:
        logger.error("Lookalike search failed: %s", exc, exc_info=True)
        return LookalikeTaskResult(
            matches_found=0,
            error=str(exc),
        ).model_dump(mode="json")
