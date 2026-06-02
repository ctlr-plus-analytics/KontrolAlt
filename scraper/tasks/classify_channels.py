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

_QA_KEYS = (
    "creator_about",
    "audience_relationship",
    "age_55_appeal",
    "acquisition_relevance",
    "monetization_pattern",
    "conversion_signals",
    "risk_flags",
)


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


def _build_qa_prompt(channel: dict[str, object]) -> str:
    platform = str(channel.get("platform") or "unknown")
    name = str(channel.get("name") or "")
    channel_url = str(channel.get("channel_url") or "")
    description = str(channel.get("description") or "")
    subscriber_count = channel.get("subscriber_count")
    avg_views = channel.get("avg_views")
    avg_comments = channel.get("avg_comments")
    engagement_rate = channel.get("engagement_rate")
    posts_per_week = channel.get("posts_per_week")
    last_active_date = channel.get("last_active_date")
    gate0_flagged_brand = channel.get("gate0_flagged_brand")
    contact_info = channel.get("contact_info") or ""
    secondary_urls = channel.get("secondary_urls") or []

    niche_tags = channel.get("niche_tags") or []
    category_str = ", ".join(niche_tags) if isinstance(niche_tags, list) and niche_tags else "Unclassified"
    ai_summary = str(channel.get("ai_summary") or "").strip() or "(none)"

    content_type = "post" if platform == "substack" else "video"
    subscriber_str = f"{subscriber_count:,}" if isinstance(subscriber_count, int) else "unknown"
    views_str = f"{avg_views:,.0f}" if isinstance(avg_views, (int, float)) else "unknown"
    comments_str = f"{avg_comments:,.1f}" if isinstance(avg_comments, (int, float)) else "unknown"
    engagement_str = f"{engagement_rate:.3f}%" if isinstance(engagement_rate, (int, float)) else "unknown"
    ppw_str = f"{posts_per_week:.1f}" if isinstance(posts_per_week, (int, float)) else "unknown"
    last_active_str = str(last_active_date) if last_active_date else "unknown"

    links_parts: list[str] = []
    if isinstance(secondary_urls, list) and secondary_urls:
        links_parts.extend(str(u) for u in secondary_urls[:5] if u)
    if contact_info:
        links_parts.append(str(contact_info))
    links_str = ", ".join(links_parts) if links_parts else "(none)"

    competitor_str = f"Gate0 flagged competitor brand: {gate0_flagged_brand}" if gate0_flagged_brand else "No competitor brand flagged"

    recent_videos = channel.get("recent_videos") or []
    video_lines: list[str] = []
    if isinstance(recent_videos, list):
        for v in recent_videos[:10]:
            if not isinstance(v, dict):
                continue
            title = str(v.get("title") or "").strip()
            if not title:
                continue
            v_views = v.get("views")
            v_comments = v.get("comments")
            pub = v.get("published_at") or ""
            parts = [f"  • {title}"]
            meta: list[str] = []
            if isinstance(v_views, (int, float)):
                meta.append(f"{v_views:,.0f} views")
            if isinstance(v_comments, (int, float)):
                meta.append(f"{v_comments:,.0f} comments")
            if pub:
                meta.append(str(pub)[:10])
            if meta:
                parts.append(f" ({', '.join(meta)})")
            video_lines.append("".join(parts))

    if not video_lines:
        video_titles = channel.get("video_titles") or []
        if isinstance(video_titles, list):
            video_lines = [f"  • {t}" for t in video_titles[:10] if t]

    videos_block = "\n".join(video_lines) if video_lines else "  (none available)"

    return (
        "CHANNEL INTELLIGENCE ANALYSIS\n\n"
        "Context: You are conducting acquisition due diligence for a precious-metals "
        "direct-response marketing company. The target acquisition audience is 55+ conservative "
        "Americans who respond to financial protection, national stability, and trust-based "
        "authority messaging.\n\n"
        "CHANNEL DATA:\n"
        f"Platform: {platform}\n"
        f"Name: {name}\n"
        f"URL: {channel_url or '(none)'}\n"
        f"Category: {category_str}\n"
        f"Summary: {ai_summary}\n"
        f"Subscribers: {subscriber_str}\n"
        f"Avg Views: {views_str}\n"
        f"Avg Comments: {comments_str}\n"
        f"Engagement Rate: {engagement_str}\n"
        f"Posts Per Week: {ppw_str}\n"
        f"Last Active: {last_active_str}\n"
        f"Description: {description or '(none)'}\n"
        f"External Links / Contact: {links_str}\n"
        f"{competitor_str}\n\n"
        f"Recent {content_type}s:\n{videos_block}\n\n"
        "INSTRUCTIONS:\n"
        "- Answer all 7 questions below with 3–5 sentences each.\n"
        "- Use analytical, hedged prose: 'appears to', 'suggests', 'the available data indicates'.\n"
        "- Never overclaim certainty when data is sparse or ambiguous.\n"
        "- For age_55_appeal: only state confirmed 55+ fit if the content themes, tone, or "
        "available evidence strongly support it — otherwise describe the likelihood.\n"
        "- For monetization_pattern: if no clear pattern is visible, say it requires further "
        "review rather than claiming none exists.\n"
        "- For risk_flags: always consider inactivity, competitor conflicts, contactability gaps, "
        "political polarization risk, and weak 55+ audience fit.\n"
        "- Respond with ONLY a JSON object using exactly these 7 keys.\n\n"
        '{\n'
        '  "creator_about": "What is this creator/channel really about?",\n'
        '  "audience_relationship": "What kind of audience relationship does the creator appear to have?",\n'
        '  "age_55_appeal": "Does the channel appear to include or appeal to a 55+ retirement-age audience segment?",\n'
        '  "acquisition_relevance": "Does the channel appear relevant for acquisition outreach?",\n'
        '  "monetization_pattern": "What monetization pattern is visible?",\n'
        '  "conversion_signals": "What are the main conversion signals?",\n'
        '  "risk_flags": "What are the risk flags?"\n'
        '}'
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


def _parse_qa_response(raw_text: str | None) -> dict[str, str] | None:
    """Parse AI Q&A JSON response into a dict with the 7 answer keys."""
    data = extract_json_object(raw_text)
    if data is None:
        if not raw_text:
            logger.warning("Q&A AI response was empty or None")
        else:
            logger.warning("Q&A JSON parse failure: %.200s", raw_text)
        return None

    report: dict[str, str] = {}
    for key in _QA_KEYS:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            report[key] = val.strip()

    if not report:
        return None
    return report


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


def _qa_one(channel: dict[str, object], client) -> dict[str, str] | None:
    from google.genai import types
    prompt = _build_qa_prompt(channel)
    response = client.models.generate_content(
        model=_CLASSIFY_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=2000,
            temperature=0.2,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return _parse_qa_response(extract_response_text(response))


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
    """Classify channel niche_tags and generate channel intelligence Q&A reports.

    Pipeline per channel:
      - If niche_tags are missing/unknown: run classification first, inject results.
      - If niche_tags are valid: skip classification, use existing tags + summary.
      - Always run Q&A after, unless ai_channel_report already exists (skip if exists).
      - reclassify=True forces both classification and Q&A to re-run on all channels.

    Args:
        channel_ids: Explicit list of channel UUIDs to process.
                     None = auto-select all dashboard-eligible channels.
        reclassify:  Force re-run classification and Q&A on all eligible channels.
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

    _SELECT = (
        "id,platform,channel_url,name,description,subscriber_count,"
        "avg_views,avg_comments,engagement_rate,posts_per_week,last_active_date,"
        "niche_tags,video_titles,recent_videos,secondary_urls,contact_info,"
        "gate0_flagged_brand,classification_context_score,discovery_category,"
        "ai_summary,ai_channel_report"
    )

    try:
        fetched: list[dict] = []
        if channel_ids is not None:
            result = (
                supabase.table("channels")
                .select(_SELECT)
                .eq("is_active", True)
                .eq("has_been_scraped", True)
                .eq("dashboard_metrics_complete", True)
                .eq("dashboard_url_valid", True)
                .eq("dashboard_eligible", True)
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
                    .select(_SELECT)
                    .eq("is_active", True)
                    .eq("has_been_scraped", True)
                    .eq("dashboard_metrics_complete", True)
                    .eq("dashboard_url_valid", True)
                    .eq("dashboard_eligible", True)
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

    logger.info(
        "classify_channels: total_fetched=%d reclassify=%s",
        len(fetched), reclassify,
    )

    classified = 0
    errors = 0
    skipped = 0
    needs_review_count = 0
    qa_generated = 0
    qa_skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for channel in fetched:
        channel_id = str(channel.get("id") or "")
        channel_name = str(channel.get("name") or channel_id)
        if not channel_id:
            continue

        ran_classify = False

        # --- Classification branch ---
        if reclassify or _needs_classification(channel):
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

            # Inject fresh results into channel dict so Q&A receives them without a DB round-trip.
            channel["niche_tags"] = final_categories
            if summary is not None:
                channel["ai_summary"] = summary

            classify_payload: dict[str, object] = {
                "niche_tags": final_categories,
                "classification_confidence": ai_confidence,
                "classification_needs_review": needs_review,
                "classification_context_score": context_score,
                "updated_at": now,
            }
            if summary is not None:
                classify_payload["ai_summary"] = summary

            try:
                supabase.table("channels").update(classify_payload).eq("id", channel_id).execute()
                classified += 1
                ran_classify = True
                logger.info(
                    "Classified '%s' → %s (conf=%.2f review=%s ctx=%d)",
                    channel_name, final_categories, ai_confidence, needs_review, context_score,
                )
                _record_classification_stat(channel, final_categories)
            except APIError as exc:
                logger.warning(
                    "Failed to update classification for '%s' (%s): %s",
                    channel_name, channel_id, exc,
                )
                errors += 1

            time.sleep(0.15)

        # --- Q&A branch ---
        # Skip if report already exists, unless we just reclassified or reclassify=True.
        existing_report = channel.get("ai_channel_report")
        if existing_report and not reclassify and not ran_classify:
            qa_skipped += 1
            continue

        try:
            qa_report = _qa_one(channel, ai_client)
        except Exception as exc:
            logger.warning(
                "Q&A API call failed for '%s' (%s): %s",
                channel_name, channel_id, exc, exc_info=True,
            )
            errors += 1
            time.sleep(1.0)
            continue

        if not qa_report:
            logger.info(
                "Q&A parse returned no data for '%s' (%s); skipping",
                channel_name, channel_id,
            )
            skipped += 1
            time.sleep(0.15)
            continue

        try:
            supabase.table("channels").update({
                "ai_channel_report": qa_report,
                "updated_at": now,
            }).eq("id", channel_id).execute()
            qa_generated += 1
            logger.info("Q&A report generated for '%s'", channel_name)
        except APIError as exc:
            logger.warning(
                "Failed to save Q&A report for '%s' (%s): %s",
                channel_name, channel_id, exc,
            )
            errors += 1

        time.sleep(0.15)

    logger.info(
        "classify_channels complete: classified=%d qa_generated=%d qa_skipped=%d "
        "skipped=%d errors=%d needs_review=%d total=%d",
        classified, qa_generated, qa_skipped, skipped, errors, needs_review_count, len(fetched),
    )
    return {
        "classified": classified,
        "qa_generated": qa_generated,
        "qa_skipped": qa_skipped,
        "skipped": skipped,
        "errors": errors,
        "needs_review_count": needs_review_count,
        "total_fetched": len(fetched),
    }
