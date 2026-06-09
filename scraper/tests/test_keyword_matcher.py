import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import utils.runtime_taxonomy as runtime_taxonomy
from utils.keyword_matcher import (
    compute_channel_demographic,
    compute_comment_tier,
    match_keywords,
)
from utils.runtime_taxonomy import get_runtime_keyword_taxonomy

_SAMPLE_TAXONOMY = {
    "Financial / Macro": ["gold", "retirement", "social security", "fixed income", "recession"],
    "Conservative Politics": ["free speech", "censorship", "constitutional"],
    "Prepper / Survival": ["emergency preparedness", "food storage", "self reliance"],
    "Crypto / Alternative Assets": ["bitcoin", "crypto", "ethereum"],
    "Homesteading": ["homestead"],
}


def test_comment_tier_thresholds() -> None:
    assert compute_comment_tier(None) is None
    assert compute_comment_tier(9.99) is None
    assert compute_comment_tier(10) == "active"
    assert compute_comment_tier(19.99) == "active"
    assert compute_comment_tier(20) == "sweet_spot"
    assert compute_comment_tier(100) == "sweet_spot"
    assert compute_comment_tier(100.01) == "whale"


def test_match_keywords_word_boundaries(monkeypatch) -> None:
    """Word-boundary matching prevents substring false positives."""
    monkeypatch.setattr(
        "utils.keyword_matcher.get_runtime_keyword_taxonomy",
        lambda: {"Prepper / Survival": ["prep"], "Financial / Macro": ["gold"]},
    )
    # "prep" should NOT match "preparation"
    assert match_keywords("I love preparation and cooking") == ["Unknown / Needs Review"]
    # "prep" SHOULD match standalone "prep"
    assert match_keywords("a great prep channel") == ["Prepper / Survival"]
    # "gold" should NOT match "marigold"
    assert match_keywords("plant marigolds in your garden") == ["Unknown / Needs Review"]
    # "gold" SHOULD match standalone "gold"
    assert match_keywords("physical gold is important") == ["Financial / Macro"]


def test_demographic_description_match_assigns_category(monkeypatch) -> None:
    monkeypatch.setattr(
        "utils.keyword_matcher.get_runtime_keyword_taxonomy",
        lambda: _SAMPLE_TAXONOMY,
    )
    result = compute_channel_demographic(
        "Market show",
        "Retirement planning and social security",
        ["Physical gold protects fixed income"],
    )
    assert "Financial / Macro" in set(result["niche_tags"])


def test_demographic_multi_keyword_titles_assign_category(monkeypatch) -> None:
    """Two distinct title keywords are enough to assign a category."""
    monkeypatch.setattr(
        "utils.keyword_matcher.get_runtime_keyword_taxonomy",
        lambda: _SAMPLE_TAXONOMY,
    )
    result = compute_channel_demographic(
        "Independent journalism",
        "Free speech, censorship, and constitutional rights coverage",
        ["Emergency preparedness and food storage for self reliance"],
    )
    assert set(result["niche_tags"]) >= {"Conservative Politics", "Prepper / Survival"}


def test_demographic_single_title_keyword_not_assigned(monkeypatch) -> None:
    """A single coincidental keyword in one title does not trigger a tag."""
    monkeypatch.setattr(
        "utils.keyword_matcher.get_runtime_keyword_taxonomy",
        lambda: {"Crypto / Alternative Assets": ["bitcoin"]},
    )
    result = compute_channel_demographic(
        "Cooking Channel",
        "Healthy recipes for the whole family",
        ["I bought bitcoin once but mainly cook now"],
    )
    assert result["niche_tags"] == ["Unknown / Needs Review"]


def test_demographic_name_match_alone_assigns_category(monkeypatch) -> None:
    """A keyword in the channel name alone is sufficient."""
    monkeypatch.setattr(
        "utils.keyword_matcher.get_runtime_keyword_taxonomy",
        lambda: _SAMPLE_TAXONOMY,
    )
    result = compute_channel_demographic(
        "Modern Homestead Living",
        "Family life and farm updates",
        [],
    )
    assert result["niche_tags"] == ["Homesteading"]


def test_demographic_categories_sorted_by_score(monkeypatch) -> None:
    """Categories with higher scores appear first."""
    monkeypatch.setattr(
        "utils.keyword_matcher.get_runtime_keyword_taxonomy",
        lambda: _SAMPLE_TAXONOMY,
    )
    # Name hit for Financial (3.0), title-only hit for Prepper (0.5+0.5=1.0)
    result = compute_channel_demographic(
        "Gold investing show",
        "Market commentary",
        ["Emergency preparedness and food storage tips"],
    )
    tags = result["niche_tags"]
    assert isinstance(tags, list)
    assert tags[0] == "Financial / Macro"


def test_demographic_uses_runtime_taxonomy(monkeypatch) -> None:
    monkeypatch.setattr(
        "utils.keyword_matcher.get_runtime_keyword_taxonomy",
        lambda: {"News / Commentary": ["special phrase"]},
    )
    result = compute_channel_demographic(
        "Channel",
        "Special phrase appears in description",
        [],
    )
    assert result["niche_tags"] == ["News / Commentary"]


def test_runtime_taxonomy_falls_back_to_baked_default(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_taxonomy,
        "_load_runtime_keyword_taxonomy_from_db",
        lambda: {},
    )
    monkeypatch.setattr(
        runtime_taxonomy,
        "_taxonomy_cache",
        {"loaded_at": 0.0, "taxonomy": None},
    )

    taxonomy = get_runtime_keyword_taxonomy(force_refresh=True)

    assert "Financial / Macro" in taxonomy
    assert taxonomy["Financial / Macro"]


def test_match_keywords_uses_baked_default_when_db_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_taxonomy,
        "_load_runtime_keyword_taxonomy_from_db",
        lambda: {},
    )
    monkeypatch.setattr(
        runtime_taxonomy,
        "_taxonomy_cache",
        {"loaded_at": 0.0, "taxonomy": None},
    )

    assert match_keywords("gold and retirement planning") == ["Financial / Macro"]
