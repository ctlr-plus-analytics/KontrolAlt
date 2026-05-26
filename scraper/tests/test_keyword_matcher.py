import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.keyword_matcher import (
    compute_channel_demographic,
    compute_comment_tier,
)


def test_comment_tier_thresholds() -> None:
    assert compute_comment_tier(None) is None
    assert compute_comment_tier(9.99) is None
    assert compute_comment_tier(10) == "active"
    assert compute_comment_tier(19.99) == "active"
    assert compute_comment_tier(20) == "sweet_spot"
    assert compute_comment_tier(100) == "sweet_spot"
    assert compute_comment_tier(100.01) == "whale"


def test_demographic_uses_combined_channel_text() -> None:
    result = compute_channel_demographic(
        "Market show",
        "Retirement planning and social security",
        ["Physical gold protects fixed income"],
    )

    assert set(result["niche_tags"]) >= {"gold_investment", "retirement"}


def test_demographic_matches_new_keyword_categories() -> None:
    result = compute_channel_demographic(
        "Independent journalism",
        "Free speech, censorship, and constitutional rights coverage",
        ["Emergency preparedness and food storage for self reliance"],
    )

    assert set(result["niche_tags"]) >= {
        "alternative_media_politics",
        "preparedness_self_reliance",
    }
