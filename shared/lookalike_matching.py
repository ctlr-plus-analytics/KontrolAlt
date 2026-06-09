"""Shared lookalike matching helpers for backend and scraper code."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SUBSCRIBER_BAND = 0.10


def normalize_name(value: str) -> str:
    """Normalize a creator name for matching."""
    return _NON_ALNUM_RE.sub(" ", value.lower()).strip()


def tokenize(value: str) -> set[str]:
    """Tokenize normalized text and drop short/empty tokens."""
    normalized = normalize_name(value)
    return {token for token in normalized.split() if len(token) >= 2}


def as_string_list(value: object) -> list[str]:
    """Normalize a text[] or text value into a string list."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def find_seed_channel(
    seed_name: str,
    channels: list[dict[str, object]],
) -> dict[str, object] | None:
    """Return the best matching seed channel by normalized name/tokens."""
    normalized_seed = normalize_name(seed_name)
    seed_tokens = tokenize(seed_name)

    for channel in channels:
        channel_name = str(channel.get("name") or "")
        if normalize_name(channel_name) == normalized_seed:
            return channel

    best_channel: dict[str, object] | None = None
    best_score = 0.0
    for channel in channels:
        channel_name = str(channel.get("name") or "")
        channel_tokens = tokenize(channel_name)
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


def is_similar_subscribers(
    seed_count: object,
    candidate_count: object,
    band: float = _SUBSCRIBER_BAND,
) -> bool:
    """Return True when two subscriber counts are within the allowed band."""
    if not isinstance(seed_count, (int, float)) or not isinstance(
        candidate_count, (int, float)
    ):
        return False
    if seed_count <= 0 or candidate_count <= 0:
        return False
    lower = seed_count * (1 - band)
    upper = seed_count * (1 + band)
    return lower <= candidate_count <= upper


def build_niche_subscriber_matches_for_seed(
    seed_id: str,
    seed_channel: dict[str, object],
    channels: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return niche-overlap matches for one seed channel."""
    matches: list[dict[str, object]] = []
    seed_channel_id = seed_channel["id"]
    seed_tags = set(as_string_list(seed_channel.get("niche_tags")))
    seed_subscribers = seed_channel.get("subscriber_count")
    if not seed_tags:
        return matches

    for channel in channels:
        if channel["id"] == seed_channel_id:
            continue

        channel_tags = set(as_string_list(channel.get("niche_tags")))
        overlap = seed_tags & channel_tags
        if len(overlap) < 1:
            continue

        candidate_subscribers = channel.get("subscriber_count")
        if not is_similar_subscribers(seed_subscribers, candidate_subscribers):
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


def dedupe_matches(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    """Keep the first deterministic result for each unique match key."""
    unique_matches: dict[tuple[str, str, str], dict[str, object]] = {}
    for match in matches:
        key = (
            str(match["seed_id"]),
            str(match["matched_channel_id"]),
            str(match["match_type"]),
        )
        if key not in unique_matches:
            unique_matches[key] = match
    return list(unique_matches.values())


def stamp_matches(
    matches: list[dict[str, object]],
    *,
    at: datetime | None = None,
) -> list[dict[str, object]]:
    """Assign ephemeral ids and timestamps to raw match dictionaries."""
    timestamp = (at or datetime.now(timezone.utc)).isoformat()
    stamped: list[dict[str, object]] = []
    for match in matches:
        row = dict(match)
        row["id"] = str(uuid4())
        row["found_at"] = timestamp
        stamped.append(row)
    return stamped
