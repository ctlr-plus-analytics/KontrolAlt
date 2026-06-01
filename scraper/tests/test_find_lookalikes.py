import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

from tasks.find_lookalikes import (
    _append_guest_matches,
    _append_niche_matches,
    _find_seed_channel,
)


def test_guest_matches_exclude_seed_channel() -> None:
    matches: list[dict[str, object]] = []
    channels = [
        {"id": "seed", "video_titles": ["Seed Creator update"]},
        {"id": "other", "video_titles": ["Interview with Seed Creator"]},
    ]

    _append_guest_matches("s1", "seed creator", "seed", channels, matches)

    assert matches == [
        {
            "seed_id": "s1",
            "matched_channel_id": "other",
            "match_type": "guest_appearance",
            "match_detail": "Interview with Seed Creator",
        }
    ]


def test_niche_matches_require_one_overlapping_tag_and_exclude_seed() -> None:
    matches: list[dict[str, object]] = []
    seed_channel = {
        "id": "seed",
        "niche_tags": ["Financial / Macro", "News / Commentary"],
        "subscriber_count": 1000,
    }
    channels = [
        seed_channel,
        {"id": "one", "niche_tags": ["Financial / Macro"], "subscriber_count": 1050},
        {
            "id": "two",
            "niche_tags": ["Financial / Macro", "News / Commentary", "Health / Wellness"],
            "subscriber_count": 950,
        },
        {"id": "three", "niche_tags": ["Financial / Macro"], "subscriber_count": 1200},
    ]

    _append_niche_matches("s1", seed_channel, channels, matches)

    assert matches == [
        {
            "seed_id": "s1",
            "matched_channel_id": "one",
            "match_type": "niche_overlap",
            "match_detail": "Shared tags: Financial / Macro | Subscribers: 1000 vs 1050 (+5.00%)",
        },
        {
            "seed_id": "s1",
            "matched_channel_id": "two",
            "match_type": "niche_overlap",
            "match_detail": "Shared tags: Financial / Macro, News / Commentary | Subscribers: 1000 vs 950 (-5.00%)",
        }
    ]


def test_niche_matches_reject_when_subscriber_similarity_fails() -> None:
    matches: list[dict[str, object]] = []
    seed_channel = {"id": "seed", "niche_tags": ["Financial / Macro"], "subscriber_count": 1000}
    channels = [{"id": "other", "niche_tags": ["Financial / Macro"], "subscriber_count": 1110}]

    _append_niche_matches("s1", seed_channel, channels, matches)

    assert matches == []


def test_niche_matches_accept_subscriber_similarity_boundary() -> None:
    matches: list[dict[str, object]] = []
    seed_channel = {"id": "seed", "niche_tags": ["Financial / Macro"], "subscriber_count": 1000}
    channels = [
        {"id": "low", "niche_tags": ["Financial / Macro"], "subscriber_count": 900},
        {"id": "high", "niche_tags": ["Financial / Macro"], "subscriber_count": 1100},
    ]

    _append_niche_matches("s1", seed_channel, channels, matches)

    assert [m["matched_channel_id"] for m in matches] == ["low", "high"]


def test_niche_matches_reject_when_no_overlap() -> None:
    matches: list[dict[str, object]] = []
    seed_channel = {"id": "seed", "niche_tags": ["Financial / Macro"], "subscriber_count": 1000}
    channels = [{"id": "other", "niche_tags": ["Health / Wellness"], "subscriber_count": 1000}]

    _append_niche_matches("s1", seed_channel, channels, matches)

    assert matches == []


def test_find_seed_channel_normalized_exact_match() -> None:
    channels = [
        {"id": "a", "name": "Glenn   Beck!"},
        {"id": "b", "name": "Another Creator"},
    ]

    match = _find_seed_channel("glenn beck", channels)

    assert match is not None
    assert match["id"] == "a"


def test_find_seed_channel_token_overlap_fallback() -> None:
    channels = [
        {"id": "a", "name": "The Glenn Beck Program"},
        {"id": "b", "name": "Different Host"},
    ]

    match = _find_seed_channel("glenn beck", channels)

    assert match is not None
    assert match["id"] == "a"
