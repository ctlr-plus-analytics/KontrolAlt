"""Keyword matching and comment tier logic."""

from utils.runtime_taxonomy import get_runtime_keyword_taxonomy


def match_keywords(text: str) -> list[str]:
    """Return matched category names from the keyword taxonomy.

    Args:
        text: Text to scan (case-insensitive substring matching).

    Returns:
        Deduplicated list of matched category names.
    """
    text_lower = text.lower()
    matched: list[str] = []
    keyword_taxonomy = get_runtime_keyword_taxonomy()
    for category, keywords in keyword_taxonomy.items():
        for keyword in keywords:
            if keyword in text_lower:
                matched.append(category)
                break
    return matched


def compute_channel_demographic(
    channel_name: str, description: str, video_titles: list[str]
) -> dict[str, object]:
    """Compute demographic signals from combined channel text.

    Args:
        channel_name: Channel display name.
        description: Channel description.
        video_titles: List of recent video titles.

    Returns:
        Dict with matched_categories and niche_tags.
    """
    combined = channel_name + " " + description + " " + " ".join(video_titles)
    categories = match_keywords(combined)
    return {
        "matched_categories": categories,
        "niche_tags": categories,
    }


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
