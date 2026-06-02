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

from services.channel_service import (
    _canonical_niche_tags_for_row,
    _channel_from_discovery_row,
    _row_matches_category_tags,
)


def test_discovery_row_maps_velocity_and_gate0_models() -> None:
    row = {
        "id": "00000000-0000-0000-0000-000000000001",
        "platform": "rumble",
        "channel_url": "https://rumble.com/c/test",
        "name": "Test",
        "description": "",
        "subscriber_count": None,
        "avg_views": None,
        "avg_comments": None,
        "comment_tier": "active",
        "posts_per_week": None,
        "last_active_date": None,
        "contact_info": [],
        "niche_tags": [],
        "video_titles": [],
        "is_active": True,
        "gate0_status": "clean",
        "gate0_checked_at": "2026-05-01T00:00:00+00:00",
        "secondary_urls": [],
        "do_not_contact": "Current Partner",
        "created_at": "2026-05-01T00:00:00+00:00",
        "updated_at": "2026-05-01T00:00:00+00:00",
        "velocity_id": "00000000-0000-0000-0000-000000000002",
        "velocity_computed_at": "2026-05-01T01:00:00+00:00",
        "view_velocity_30d": None,
        "view_velocity_90d": 12.5,
        "comment_velocity_30d": None,
        "comment_velocity_90d": -2.5,
        "gate0_result_id": "00000000-0000-0000-0000-000000000003",
        "gate0_result_checked_at": "2026-05-01T02:00:00+00:00",
        "gate0_search_query": '"Test" "gold IRA"',
        "gate0_result_status": "clean",
        "gate0_flagged_brand": None,
        "gate0_source_url": None,
    }

    channel = _channel_from_discovery_row(row)

    assert channel.velocity is not None
    assert channel.velocity.view_velocity_90d == 12.5
    assert channel.gate0 is not None
    assert channel.gate0.result_status.value == "clean"
    assert channel.do_not_contact is not None
    assert channel.do_not_contact.value == "Current Partner"


def test_canonical_niche_tags_maps_unknown_bucket() -> None:
    assert _canonical_niche_tags_for_row({"niche_tags": []}) == {"Unknown / Needs Review"}
    assert _canonical_niche_tags_for_row({"niche_tags": ["Non Canonical Tag"]}) == {
        "Unknown / Needs Review"
    }


def test_row_matches_category_tags_uses_canonical_mapping() -> None:
    row = {"niche_tags": ["Non Canonical Tag"]}
    assert _row_matches_category_tags(row, ["Unknown / Needs Review"]) is True
    assert _row_matches_category_tags(row, ["Financial / Macro"]) is False
