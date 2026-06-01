"""Keyword matching and comment tier logic."""

import re

from utils.runtime_taxonomy import get_runtime_keyword_taxonomy

_SCORE_NAME = 3.0
_SCORE_DESC = 2.0
_SCORE_TITLE = 0.5
_ASSIGNMENT_THRESHOLD = 1.0


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(keyword) + r"\b")


def match_keywords(text: str) -> list[str]:
    """Return matched category names from the keyword taxonomy.

    Args:
        text: Text to scan (case-insensitive word-boundary matching).

    Returns:
        Deduplicated list of matched category names.
    """
    text_lower = text.lower()
    matched: list[str] = []
    keyword_taxonomy = get_runtime_keyword_taxonomy()
    for category, keywords in keyword_taxonomy.items():
        for keyword in keywords:
            if _keyword_pattern(keyword).search(text_lower):
                matched.append(category)
                break
    return matched if matched else ["Unknown / Needs Review"]


def compute_channel_demographic(
    channel_name: str, description: str, video_titles: list[str]
) -> dict[str, object]:
    """Compute demographic signals using source-weighted keyword scoring.

    Each keyword is scored per source:
      - Channel name match: 3.0 pts  (name is the strongest signal)
      - Description match:  2.0 pts
      - Any title match:    0.5 pts  (binary — same keyword in 1 or 20 titles counts once)

    A category is assigned when its total score >= 1.0, which requires either
    one description/name hit or two distinct title-matched keywords. This
    prevents a single coincidental keyword mention from triggering a tag.

    Args:
        channel_name: Channel display name.
        description: Channel description.
        video_titles: List of recent video titles.

    Returns:
        Dict with matched_categories and niche_tags sorted by descending score.
    """
    keyword_taxonomy = get_runtime_keyword_taxonomy()
    scores: dict[str, float] = {}

    name_lower = channel_name.lower()
    desc_lower = description.lower()
    title_lowers = [t.lower() for t in video_titles]

    for category, keywords in keyword_taxonomy.items():
        score = 0.0
        for keyword in keywords:
            pattern = _keyword_pattern(keyword)
            if pattern.search(name_lower):
                score += _SCORE_NAME
            if pattern.search(desc_lower):
                score += _SCORE_DESC
            if any(pattern.search(title) for title in title_lowers):
                score += _SCORE_TITLE

        if score > 0:
            scores[category] = score

    categories = [
        cat
        for cat, s in sorted(scores.items(), key=lambda x: -x[1])
        if s >= _ASSIGNMENT_THRESHOLD
    ]
    result = categories if categories else ["Unknown / Needs Review"]
    return {"matched_categories": result, "niche_tags": result}


def compute_comment_tier(avg_comments: float | None) -> str | None:
    """Assign comment engagement tier.

    Args:
        avg_comments: Average comments per video.

    Returns:
        Tier string or None if below threshold.
    """
    if avg_comments is None:
        return None
    if avg_comments > 100:
        return "whale"
    if avg_comments >= 20:
        return "sweet_spot"
    if avg_comments >= 10:
        return "active"
    return None
