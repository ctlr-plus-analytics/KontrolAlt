"""Celery task for AI-powered channel category classification using Groq."""

import json
import logging
import time
from datetime import datetime, timezone

from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.supabase import get_supabase_client

logger = logging.getLogger(__name__)

_CLASSIFY_MODEL = "llama-3.1-8b-instant"

_VALID_CATEGORIES = frozenset({
    "Prepper / Survival",
    "Financial / Macro",
    "Conservative Politics",
    "Health / Wellness",
    "Homesteading",
    "Crypto / Alternative Assets",
    "Religious / Values-Based",
    "News / Commentary",
    "Unknown / Needs Review",
})

_SYSTEM_PROMPT = (
    "You are an expert analyst of alternative media channels for a research platform. "
    "You always respond with valid JSON only — no prose, no explanation outside the JSON object."
)

_CATEGORY_DESCRIPTIONS = """\
- Prepper / Survival: Emergency preparedness, survival skills, bug-out plans, food storage, doomsday readiness, self-reliance against societal collapse
- Financial / Macro: Macroeconomics, investing, precious metals (gold/silver), inflation/recession/dollar-collapse, debt, retirement, financial freedom
- Conservative Politics: Right-leaning political commentary, MAGA, election integrity, constitutional rights, anti-establishment politics, patriot content
- Health / Wellness: Alternative or holistic health, natural medicine, anti-vaccine sentiment, nutrition, detox, wellness lifestyle
- Homesteading: Off-grid living, small-scale farming, gardening, raising livestock, rural self-sufficiency, land stewardship
- Crypto / Alternative Assets: Cryptocurrency, Bitcoin, DeFi, hard money, alternative store of value outside fiat
- Religious / Values-Based: Christian or faith-based worldview, biblical teaching, traditional family values, pro-life, spiritual content
- News / Commentary: Broad news analysis, current events commentary, political/cultural criticism, independent journalism"""


def _build_prompt(channel: dict[str, object]) -> str:
    platform = str(channel.get("platform") or "unknown")
    name = str(channel.get("name") or "")
    description = str(channel.get("description") or "")
    subscriber_count = channel.get("subscriber_count")

    video_titles = channel.get("video_titles")
    titles: list[str] = []
    if isinstance(video_titles, list):
        titles = [str(t) for t in video_titles[:20] if t]

    secondary_urls = channel.get("secondary_urls") or []
    contact_info = channel.get("contact_info") or ""

    content_type = "post" if platform == "substack" else "video"
    subscriber_str = f"{subscriber_count:,}" if isinstance(subscriber_count, int) else "unknown"

    secondary_str = ""
    if isinstance(secondary_urls, list) and secondary_urls:
        urls = [str(u) for u in secondary_urls[:5] if u]
        if urls:
            secondary_str = f"Other links: {', '.join(urls)}\n"
    if contact_info:
        secondary_str += f"Contact/links: {contact_info}\n"

    titles_block = "\n".join(f"  • {t}" for t in titles) if titles else "  (none available)"

    return (
        f"CATEGORIES (assign 1–3 that best fit):\n{_CATEGORY_DESCRIPTIONS}\n\n"
        "CHANNEL DATA:\n"
        f"Platform: {platform}\n"
        f"Name: {name}\n"
        f"Subscribers: {subscriber_str}\n"
        f"Description: {description or '(none)'}\n"
        f"{secondary_str}"
        f"Recent {content_type} titles:\n{titles_block}\n\n"
        "INSTRUCTIONS:\n"
        "- Assign 1–3 categories based on the channel's PRIMARY and CONSISTENT focus.\n"
        "- Do not tag a category for one isolated mention; the channel must regularly cover it.\n"
        '- Use "Unknown / Needs Review" only as a last resort when nothing fits.\n'
        "- Write a 2–3 sentence plain-English summary of what this channel covers. "
        "Focus on the content niche, tone/angle, and intended audience. "
        "Do not mention the platform or subscriber count.\n"
        "- Respond with ONLY a JSON object.\n\n"
        '{"categories": ["Category Name"], "summary": "2-3 sentence description."}'
    )


def _parse_response(raw_text: str) -> tuple[list[str], str | None]:
    """Parse categories and summary from Groq's JSON-mode response.

    Returns:
        (categories, summary) — categories falls back to ["Unknown / Needs Review"]
        and summary to None on any parse failure.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning("JSON parse failure in Groq response: %.200s", raw_text)
        return ["Unknown / Needs Review"], None

    if not isinstance(data, dict):
        return ["Unknown / Needs Review"], None

    raw_cats = data.get("categories")
    valid = (
        [c for c in raw_cats if isinstance(c, str) and c in _VALID_CATEGORIES]
        if isinstance(raw_cats, list)
        else []
    )
    categories = valid if valid else ["Unknown / Needs Review"]

    raw_summary = data.get("summary")
    summary = str(raw_summary).strip() if isinstance(raw_summary, str) and raw_summary.strip() else None

    return categories, summary


def _classify_one(channel: dict[str, object], client) -> tuple[list[str], str | None]:
    prompt = _build_prompt(channel)
    completion = client.chat.completions.create(
        model=_CLASSIFY_MODEL,
        max_tokens=300,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return _parse_response(completion.choices[0].message.content)


def _needs_classification(channel: dict[str, object]) -> bool:
    tags = channel.get("niche_tags")
    if not isinstance(tags, list) or len(tags) == 0:
        return True
    return tags == ["Unknown / Needs Review"]


@celery_app.task(name="scraper.tasks.classify_channels", bind=True)
def classify_channels(
    self,
    channel_ids: list[str] | None = None,
    reclassify: bool = False,
) -> dict[str, object]:
    """Classify channel niche_tags using Groq (llama-3.1-8b-instant).

    Args:
        channel_ids: Explicit list of channel UUIDs to classify.
                     None = auto-select based on reclassify flag.
        reclassify:  When True with channel_ids=None, reclassify every active
                     scraped channel. When False, only process channels that
                     have no tags or are tagged "Unknown / Needs Review".
    """
    api_key = scraper_settings.groq_api_key
    if not api_key:
        logger.error("GROQ_API_KEY not configured; cannot run channel classification")
        return {"error": "GROQ_API_KEY not set", "classified": 0}

    try:
        from groq import Groq
    except ImportError:
        logger.error("groq package not installed")
        return {"error": "groq package not installed", "classified": 0}

    client = Groq(api_key=api_key)
    supabase = get_supabase_client()

    try:
        query = (
            supabase.table("channels")
            .select(
                "id,platform,name,description,subscriber_count,"
                "niche_tags,video_titles,secondary_urls,contact_info"
            )
            .eq("is_active", True)
            .eq("has_been_scraped", True)
        )
        if channel_ids is not None:
            query = query.in_("id", channel_ids)
        result = query.execute()
        fetched = result.data or []
    except APIError as exc:
        logger.error("Failed to fetch channels for classification: %s", exc)
        return {"error": str(exc), "classified": 0}

    if channel_ids is None and not reclassify:
        channels = [ch for ch in fetched if _needs_classification(ch)]
    else:
        channels = fetched

    logger.info(
        "classify_channels: total_fetched=%d to_process=%d reclassify=%s",
        len(fetched), len(channels), reclassify,
    )

    classified = 0
    errors = 0
    now = datetime.now(timezone.utc).isoformat()

    for channel in channels:
        channel_id = str(channel.get("id") or "")
        channel_name = str(channel.get("name") or channel_id)
        if not channel_id:
            continue

        try:
            categories, summary = _classify_one(channel, client)
        except Exception as exc:
            logger.warning(
                "Classification API call failed for '%s' (%s): %s",
                channel_name, channel_id, exc, exc_info=True,
            )
            errors += 1
            time.sleep(1.0)
            continue

        update_payload: dict[str, object] = {
            "niche_tags": categories,
            "updated_at": now,
        }
        if summary is not None:
            update_payload["ai_summary"] = summary

        try:
            supabase.table("channels").update(update_payload).eq("id", channel_id).execute()
            classified += 1
            logger.info("Classified '%s' → %s | summary=%s", channel_name, categories, bool(summary))
        except APIError as exc:
            logger.warning(
                "Failed to update channel '%s' (%s): %s",
                channel_name, channel_id, exc,
            )
            errors += 1

        time.sleep(0.15)

    logger.info(
        "classify_channels complete: classified=%d errors=%d candidates=%d",
        classified, errors, len(channels),
    )
    return {
        "classified": classified,
        "errors": errors,
        "total_candidates": len(channels),
    }
