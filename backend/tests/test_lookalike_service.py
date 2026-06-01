import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("SERP_API_KEY", "serper-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")

from services.lookalike_service import (  # noqa: E402
    _build_niche_subscriber_matches_for_seed,
    _is_similar_subscribers,
)


def test_subscriber_similarity_accepts_boundaries() -> None:
    assert _is_similar_subscribers(1000, 900)
    assert _is_similar_subscribers(1000, 1100)


def test_subscriber_similarity_rejects_outside_band() -> None:
    assert not _is_similar_subscribers(1000, 899)
    assert not _is_similar_subscribers(1000, 1101)


def test_niche_subscriber_matching_requires_both_conditions() -> None:
    seed_channel = {
        "id": "seed",
        "niche_tags": ["Financial / Macro", "News / Commentary"],
        "subscriber_count": 1000,
    }
    channels = [
        seed_channel,
        {"id": "a", "niche_tags": ["Financial / Macro"], "subscriber_count": 1050},
        {"id": "b", "niche_tags": ["Financial / Macro"], "subscriber_count": 1200},
        {"id": "c", "niche_tags": ["Conservative Politics"], "subscriber_count": 1000},
    ]

    matches = _build_niche_subscriber_matches_for_seed("s1", seed_channel, channels)

    assert [match["matched_channel_id"] for match in matches] == ["a"]
    assert "Shared tags: Financial / Macro" in str(matches[0]["match_detail"])
