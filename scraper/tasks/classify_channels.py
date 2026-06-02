"""Celery task for AI-powered channel category classification using Google AI."""

import logging
import time
from datetime import datetime, timezone

from postgrest.exceptions import APIError

from worker import celery_app
from core.config import scraper_settings
from core.supabase import get_supabase_client
from utils.ai_response import extract_json_object, extract_response_text
from utils.keyword_matcher import compute_channel_demographic

logger = logging.getLogger(__name__)

_CLASSIFY_MODEL = "gemini-2.5-flash"

_VALID_CATEGORIES = frozenset({
    "Prepper / Survival",
    "Financial / Macro",
    "Conservative Politics",
    "Health / Wellness",
    "Homesteading",
    "Crypto / Alternative Assets",
    "Religious / Values-Based",
    "News / Commentary",
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
        "- Assign 1 category only based on the channel's PRIMARY and CONSISTENT focus.\n"
        "- Do not tag a category for one isolated mention; the channel must regularly cover it.\n"
        "- Always assign at least 1 category — pick the best fit even with sparse or ambiguous data.\n"
        "- Write a 2–3 sentence plain-English summary of what this channel covers. "
        "Focus on the content niche, tone/angle, and intended audience. "
        "Do not mention the platform or subscriber count.\n"
        "- Rate your confidence from 0.0 to 1.0: high when name/description/titles strongly "
        "align; low when data is sparse or ambiguous.\n"
        "- List the key evidence signals that drove the classification "
        "(e.g. name_match, description_match, titles_confirm, subscriber_count_known).\n"
        "- Respond with ONLY a JSON object.\n\n"
        '{"categories": ["Category Name"], "summary": "2-3 sentence description.", '
        '"confidence": 0.85, "signals": ["name_match", "description_match"]}'
    )


def _parse_response(
    raw_text: str | None,
) -> tuple[list[str], str | None, float, list[str]]:
    """Parse AI JSON response into (categories, summary, confidence, signals)."""
    data = extract_json_object(raw_text)
    if data is None:
        if not raw_text:
            logger.warning("AI response was empty or None")
        else:
            logger.warning("JSON parse failure in AI response: %.200s", raw_text)
        return [], None, 0.0, []

    raw_cats = data.get("categories")
    valid = (
        [c for c in raw_cats if isinstance(c, str) and c in _VALID_CATEGORIES]
        if isinstance(raw_cats, list)
        else []
    )
    categories = valid if valid else []

    raw_summary = data.get("summary")
    summary = (
        str(raw_summary).strip()
        if isinstance(raw_summary, str) and raw_summary.strip()
        else None
    )

    raw_confidence = data.get("confidence")
    try:
        confidence = float(raw_confidence) if raw_confidence is not None else 0.5
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5

    raw_signals = data.get("signals")
    signals = (
        [str(s) for s in raw_signals if isinstance(s, str)]
        if isinstance(raw_signals, list)
        else []
    )

    return categories, summary, confidence, signals

def _compute_context_score(channel: dict[str, object]) -> int:
    """Score data richness available for classification (0–3).

    0 = no usable name
    1 = name only
    2 = name + description
    3 = name + description + video titles
    """
    name = str(channel.get("name") or "").strip()
    if not name:
        return 0
    description = str(channel.get("description") or "").strip()
    video_titles = channel.get("video_titles")
    has_titles = isinstance(video_titles, list) and len(video_titles) > 0
    if description and has_titles:
        return 3
    if description:
        return 2
    return 1


def _needs_classification(channel: dict[str, object]) -> bool:
    tags = channel.get("niche_tags")
    if not isinstance(tags, list) or len(tags) == 0:
        return True
    if tags == ["Unknown / Needs Review"]:
        return True
    ai_summary = channel.get("ai_summary")
    if not ai_summary or not str(ai_summary).strip():
        return True
    # Re-classify if previously tagged with low context score and more data is now available.
    ctx_score = channel.get("classification_context_score")
    if isinstance(ctx_score, int) and ctx_score < 2:
        description = str(channel.get("description") or "").strip()
        video_titles = channel.get("video_titles")
        if description or (isinstance(video_titles, list) and video_titles):
            return True
    return False


def _classify_one(
    channel: dict[str, object], client
) -> tuple[list[str], str | None, float, list[str]]:
    from google.genai import types
    prompt = _build_prompt(channel)
    response = client.models.generate_content(
        model=_CLASSIFY_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=700,
            temperature=0.1,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return _parse_response(extract_response_text(response))


def _resolve_ensemble(
    ai_categories: list[str],
    keyword_categories: list[str],
    ai_confidence: float,
) -> tuple[list[str], bool]:
    """Reconcile AI and keyword-based classification.

    Returns (final_categories, needs_review). final_categories is empty only
    when both systems have zero signal; the caller skips the DB update in that case.
    """
    ai_set = set(ai_categories) - {"Unknown / Needs Review"}
    keyword_set = set(keyword_categories) - {"Unknown / Needs Review"}

    # Both systems found nothing — caller will skip update and retry later.
    if not ai_set and not keyword_set:
        return [], False

    # Both agree on at least one category — strong signal.
    if ai_set & keyword_set:
        return [c for c in ai_categories if c in _VALID_CATEGORIES], ai_confidence < 0.55

    # AI found something, keyword-based found nothing — trust AI, flag if low confidence.
    if ai_set and not keyword_set:
        return [c for c in ai_categories if c in _VALID_CATEGORIES], ai_confidence < 0.70

    # Keyword-based found something, AI had no valid signal — use keyword, flag for review.
    if keyword_set and not ai_set:
        return [c for c in keyword_categories if c in _VALID_CATEGORIES], True

    # Both found categories but zero overlap — flag for review, prefer AI.
    return [c for c in ai_categories if c in _VALID_CATEGORIES], True


def _record_classification_stat(channel: dict[str, object], categories: list[str]) -> None:
    """Increment the classified_known counter for the channel's discovery category."""
    if not categories:
        return
    discovery_category = str(channel.get("discovery_category") or "")
    platform = str(channel.get("platform") or "")
    if not discovery_category or not platform:
        return
    try:
        from tasks.scrape_helpers import _redis_client
        client = _redis_client()
        key = f"discovery:qstat:{discovery_category}:{platform}"
        client.hincrby(key, "classified_known", 1)
        client.expire(key, 30 * 24 * 3600)
    except Exception as exc:
        logger.debug("Failed to record classification stat: %s", exc)


@celery_app.task(name="scraper.tasks.classify_channels", bind=True)
def classify_channels(
    self,
    channel_ids: list[str] | None = None,
    reclassify: bool = False,
) -> dict[str, object]:
    """Classify channel niche_tags using AI + keyword-based ensemble.

    Args:
        channel_ids: Explicit list of channel UUIDs to classify.
                     None = auto-select based on reclassify flag.
        reclassify:  When True with channel_ids=None, reclassify every active
                     scraped channel. When False, only process channels that
                     have no tags, are tagged "Unknown / Needs Review", or were
                     previously classified with low context score.
    """
    api_key = scraper_settings.google_api_key
    if not api_key:
        logger.error("GOOGLE_API_KEY not configured; cannot run channel classification")
        return {"error": "GOOGLE_API_KEY not set", "classified": 0}

    try:
        from google import genai
    except ImportError:
        logger.error("google-genai package not installed")
        return {"error": "google-genai package not installed", "classified": 0}

    ai_client = genai.Client(api_key=api_key)
    supabase = get_supabase_client()

    _UNCLASSIFIED_FILTER = 'niche_tags.is.null,niche_tags.cs.{"Unknown / Needs Review"}'

    try:
        fetched: list[dict] = []
        if channel_ids is not None:
            result = (
                supabase.table("channels")
                .select(
                    "id,platform,name,description,subscriber_count,"
                    "niche_tags,video_titles,secondary_urls,contact_info,"
                    "classification_context_score,discovery_category,ai_summary"
                )
                .eq("is_active", True)
                .eq("has_been_scraped", True)
                .eq("dashboard_metrics_complete", True)
                .eq("dashboard_url_valid", True)
                .eq("dashboard_eligible", True)
                .or_(_UNCLASSIFIED_FILTER)
                .in_("id", channel_ids)
                .execute()
            )
            fetched = result.data or []
        else:
            page_size = 1000
            offset = 0
            while True:
                result = (
                    supabase.table("channels")
                    .select(
                        "id,platform,name,description,subscriber_count,"
                        "niche_tags,video_titles,secondary_urls,contact_info,"
                        "classification_context_score,discovery_category,ai_summary"
                    )
                    .eq("is_active", True)
                    .eq("has_been_scraped", True)
                    .eq("dashboard_metrics_complete", True)
                    .eq("dashboard_url_valid", True)
                    .eq("dashboard_eligible", True)
                    .or_(_UNCLASSIFIED_FILTER)
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                page = result.data or []
                fetched.extend(page)
                if len(page) < page_size:
                    break
                offset += page_size
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
    skipped = 0
    needs_review_count = 0
    now = datetime.now(timezone.utc).isoformat()

    for channel in channels:
        channel_id = str(channel.get("id") or "")
        channel_name = str(channel.get("name") or channel_id)
        if not channel_id:
            continue

        context_score = _compute_context_score(channel)

        try:
            ai_categories, summary, ai_confidence, _signals = _classify_one(
                channel, ai_client
            )
        except Exception as exc:
            logger.warning(
                "Classification API call failed for '%s' (%s): %s",
                channel_name, channel_id, exc, exc_info=True,
            )
            errors += 1
            time.sleep(1.0)
            continue

        # Keyword-based ensemble pass.
        name = str(channel.get("name") or "")
        description = str(channel.get("description") or "")
        video_titles = channel.get("video_titles") or []
        if not isinstance(video_titles, list):
            video_titles = []
        keyword_result = compute_channel_demographic(name, description, video_titles)
        keyword_categories: list[str] = keyword_result.get("niche_tags") or []

        final_categories, needs_review = _resolve_ensemble(
            ai_categories, keyword_categories, ai_confidence
        )

        if not final_categories:
            logger.info(
                "No classification signal for '%s' (%s); will retry when more data is available",
                channel_name, channel_id,
            )
            skipped += 1
            time.sleep(0.15)
            continue

        if needs_review:
            needs_review_count += 1

        update_payload: dict[str, object] = {
            "niche_tags": final_categories,
            "classification_confidence": ai_confidence,
            "classification_needs_review": needs_review,
            "classification_context_score": context_score,
            "updated_at": now,
        }
        if summary is not None:
            update_payload["ai_summary"] = summary

        try:
            supabase.table("channels").update(update_payload).eq("id", channel_id).execute()
            classified += 1
            logger.info(
                "Classified '%s' → %s (conf=%.2f review=%s ctx=%d)",
                channel_name, final_categories, ai_confidence, needs_review, context_score,
            )
            _record_classification_stat(channel, final_categories)
        except APIError as exc:
            logger.warning(
                "Failed to update channel '%s' (%s): %s",
                channel_name, channel_id, exc,
            )
            errors += 1

        time.sleep(0.15)

    logger.info(
        "classify_channels complete: classified=%d skipped=%d errors=%d needs_review=%d candidates=%d",
        classified, skipped, errors, needs_review_count, len(channels),
    )
    return {
        "classified": classified,
        "skipped": skipped,
        "errors": errors,
        "needs_review_count": needs_review_count,
        "total_candidates": len(channels),
    }
