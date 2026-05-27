"""BitChute scraper with resilient channel-card extraction."""

import logging
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from time import perf_counter
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.async_api import Error as PlaywrightError

from core.browser import (
    BrowserTelemetry,
    guarded_goto,
    human_delay,
    is_cold_session,
    launch_browser,
    pre_warm_homepage,
    wait_for_content,
)
from core.cf_bypass import human_scroll, inter_request_jitter
from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from core.runtime_settings import get_runtime_settings
from scrapers.base import BaseScraper
from utils.contact_extractor import extract_emails, extract_urls
from utils.keyword_matcher import compute_channel_demographic, compute_comment_tier

logger = logging.getLogger(__name__)

BITCHUTE_BASE_URL = "https://www.bitchute.com"
_EXCLUDED_CONTACT_DOMAINS = {
    "bitchute.com",
    "www.bitchute.com",
    "support.bitchute.com",
}

BITCHUTE_CHANNEL = {
    "channel_name": {
        "primary": "div.q-card__section.q-card__section--vert.q-pt-none > div.row.text-bold.text-h4",
        "fallbacks": [
            "span.q-btn__content span.block"
        ],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
    "channel_description": {
        "primary": "div[style*=\"white-space: pre-line\"]",
        "fallbacks": [
            "div.text-grey-8.bc-text-break.bc-description"
        ],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
    "subscriber_count": {
        "primary": "div.text-caption.text-grey-8 span[style*=\"cursor: pointer\"]",
        "fallbacks": [
            "div.q-item__section.q-item__section--main.justify-center div.q-item__label.text-bold",
            "div.q-item__label.q-item__label--caption.text-caption.ellipsis span[style*=\"cursor: pointer\"]"
        ],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "video_card": {
        "primary": "#video-card",
        "fallbacks": [
            "#video-card a[href^=\"/video/\"]",
            "a[href^=\"/video/\"]",
        ],
        "extract": "node",
        "normalize": "none",
        "js_required": False,
    },
    "video_urls": {
        "primary": "#video-card a[href^=\"/video/\"]",
        "fallbacks": [
            "a[href^=\"/video/\"]",
        ],
        "extract": "attr(href)",
        "normalize": "urljoin(base)+canonicalize",
        "js_required": False,
    },
    "video_titles": {
        "primary": "div.q-item__label.bc-text-break.ellipsis-2-lines.bc-responsive-font",
        "fallbacks": [
            "div.col-xs-12.col-sm-8.col-10 div.bc-text-break.bc-responsive-font",
            "div.q-item__label.bc-text-break.ellipsis-2-lines.text-subtitle2",
            "div.q-item__label.bc-text-break.ellipsis-2-lines",
            "div.q-item__label.bc-text-break.bc-responsive-font",
        ],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
    "video_view_counts": {
        "primary": "div.q-chip__content div.text-caption",
        "fallbacks": [
            "div.col-xs-12.col-sm-4.col-2 div.q-item__label.text-right.text-weight-medium.text-subtitle1"
        ],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "video_upload_dates": {
        "primary": "div.q-item__label.q-item__label--caption.text-caption",
        "fallbacks": [
            "div.col-xs-12.col-sm-4.col-2 div.q-item__label.text-right.text-weight-medium.text-subtitle1 > span"
        ],
        "extract": "text()",
        "normalize": "parse_bitchute_datetime()",
        "js_required": False,
    },
    "external_links": {
        "primary": "div.row.q-mt-sm a[target=\"_blank\"]",
        "fallbacks": [
            "div.text-grey-8.bc-text-break.bc-description a[target=\"_blank\"]"
        ],
        "extract": "attr(href)",
        "normalize": "exclude_bitchute_domain",
        "js_required": False,
    },
    "email_addresses": {
        "primary": "a[href^='mailto:']",
        "fallbacks": [],
        "extract": "href_text",
        "normalize": "lower+dedupe",
        "js_required": False,
    },
}

BITCHUTE_VIDEO = {
    "title": {
        "primary": "div.col-xs-12.col-sm-8.col-10 div.bc-text-break.bc-responsive-font",
        "fallbacks": [
            "meta[property=\"og:title\"]"
        ],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
    "view_count": {
        "primary": "div.col-xs-12.col-sm-4.col-2 div.q-item__label.text-right.text-weight-medium.text-subtitle1",
        "fallbacks": [
            "div.q-chip__content div.text-caption"
        ],
        "extract": "text()",
        "normalize": "parse_bitchute_views()",
        "js_required": False,
    },
    "comment_count": {
        "primary": "#comments-container span.item.count span.value",
        "fallbacks": [
            "#comments-container .navigation .item.count .value",
            "#comments-container span.item.count",
            "span.item.count span.value",
        ],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "upload_date": {
        "primary": "div.col-xs-12.col-sm-4.col-2 div.q-item__label.text-right.text-weight-medium.text-subtitle1 > span",
        "fallbacks": [
            "div.col-xs-12.col-sm-4.col-2 div.q-item__label.text-right.text-weight-medium.text-subtitle1"
        ],
        "extract": "text()",
        "normalize": "parse_bitchute_datetime()",
        "js_required": False,
    },
    "subscriber_count": {
        "primary": "div.q-item__label.q-item__label--caption.text-caption.ellipsis span[style*=\"cursor: pointer\"]",
        "fallbacks": [
            "div.text-caption.text-grey-8 span[style*=\"cursor: pointer\"]",
            "div.q-item__section.q-item__section--main.justify-center div.q-item__label.text-bold"
        ],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "external_links": {
        "primary": "div.text-grey-8.bc-text-break.bc-description a[target=\"_blank\"]",
        "fallbacks": [
            "div.row.q-mt-sm a[target=\"_blank\"]"
        ],
        "extract": "attr(href)",
        "normalize": "exclude_bitchute_domain",
        "js_required": False,
    },
    "description": {
        "primary": "div.text-grey-8.bc-text-break.bc-description",
        "fallbacks": [
            "div[style*=\"white-space: pre-line\"]"
        ],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
}


def parse_count_text(text: str) -> int | None:
    """Parse generic count strings like '1,234', '12.5K', '3M comments'."""
    if not text:
        return None
    cleaned = (
        text.lower()
        .replace(",", "")
        .replace("\xa0", " ")
        .replace("subscribers", "")
        .replace("subscriber", "")
        .replace("comments", "")
        .replace("comment", "")
        .replace("views", "")
        .replace("view", "")
        .strip()
    )
    # Collapse whitespace introduced by get_text() element boundaries (e.g. "3 .2K" → "3.2K").
    cleaned = re.sub(r"\s+", "", cleaned)
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmb])?", cleaned)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    suffix = match.group(2)
    if suffix == "k":
        return int(value * 1_000)
    if suffix == "m":
        return int(value * 1_000_000)
    if suffix == "b":
        return int(value * 1_000_000_000)
    return int(value)


def parse_bitchute_views(text: str) -> int | None:
    """Parse the views count from BitChute video page detail text node."""
    if not text:
        return None
    match = re.search(r"([\d\.,\s]+[kmb]?)\s*views", text, re.I)
    if match:
        return parse_count_text(match.group(1))
    return parse_count_text(text)


def parse_bitchute_datetime(dt_str: str) -> datetime | None:
    """Parse BitChute absolute, HTTP-date, and relative date strings."""
    if not dt_str:
        return None
    text = dt_str.strip()
    now = datetime.now()
    try:
        parsed = datetime.fromisoformat(re.sub(r"Z$", "+00:00", text))
        return parsed.replace(tzinfo=None)
    except (ValueError, TypeError):
        pass
    try:
        return parsedate_to_datetime(text).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(year=now.year)
        except ValueError:
            continue

    lowered = text.lower()
    if "yesterday" in lowered:
        return now - timedelta(days=1)
    if "just now" in lowered:
        return now
    match = re.search(
        r"(\d+)\s+("
        r"second|minute|hour|day|week|month|year|"
        r"sec|min|hr|wk|mo|yr"
        r")s?\s+ago",
        lowered,
    )
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit in {"second", "sec"}:
        return now - timedelta(seconds=value)
    if unit in {"minute", "min"}:
        return now - timedelta(minutes=value)
    if unit in {"hour", "hr"}:
        return now - timedelta(hours=value)
    if unit == "day":
        return now - timedelta(days=value)
    if unit in {"week", "wk"}:
        return now - timedelta(weeks=value)
    if unit in {"month", "mo"}:
        return now - timedelta(days=value * 30)
    if unit in {"year", "yr"}:
        return now - timedelta(days=value * 365)
    return None


class BitChuteScraper(BaseScraper):
    """Scraper for BitChute channels using Patchright and BeautifulSoup."""

    VIDEO_COLLECTION_LIMIT = 3
    COMMENT_VIDEO_PAGE_SAMPLE_LIMIT = 3
    DEMOGRAPHIC_TITLE_LIMIT = 20
    CHANNEL_NAV_TIMEOUT_MS = 45000
    PRIMARY_CONTENT_TIMEOUT_S = 14.0
    RELOAD_CONTENT_TIMEOUT_S = 12.0
    SECOND_CYCLE_CONTENT_TIMEOUT_S = 16.0
    CARD_SELECTOR_TIMEOUT_MS = 9000
    ABOUT_NAV_TIMEOUT_MS = 22000
    ABOUT_CONTENT_TIMEOUT_S = 7.0
    ABOUT_FETCH_ATTEMPTS = 2
    VIDEO_PAGE_TIMEOUT_MS = 30000
    VIDEO_PAGE_CONTENT_TIMEOUT_S = 10.0
    VIDEO_PAGE_COMMENT_TIMEOUT_MS = 15000
    VIDEO_PAGE_COMMENT_SHORT_TIMEOUT_MS = 5000
    _EMPTY_CHANNEL_MARKERS = (
        "0 videos",
        "no videos",
        "this channel has no videos",
        "nothing here yet",
        "no uploads yet",
    )
    VIDEO_CARD_SELECTOR = BITCHUTE_CHANNEL["video_card"]["primary"]
    VIDEO_LINK_SELECTOR = BITCHUTE_CHANNEL["video_urls"]["primary"]
    VIDEO_TITLE_SELECTOR = BITCHUTE_CHANNEL["video_titles"]["primary"]
    VIDEO_TIME_SELECTOR = BITCHUTE_CHANNEL["video_upload_dates"]["primary"]
    VIDEO_VIEWS_SELECTOR = BITCHUTE_CHANNEL["video_view_counts"]["primary"]
    CHANNEL_NAME_SELECTOR = BITCHUTE_CHANNEL["channel_name"]["primary"]
    CHANNEL_FOLLOWERS_SELECTOR = BITCHUTE_CHANNEL["subscriber_count"]["primary"]
    ABOUT_DESCRIPTION_SELECTOR = BITCHUTE_CHANNEL["channel_description"]["primary"]
    ABOUT_SOCIAL_LINKS_SELECTOR = BITCHUTE_CHANNEL["external_links"]["primary"]
    VIDEO_PAGE_TITLE_SELECTOR = BITCHUTE_VIDEO["title"]["primary"]
    VIDEO_PAGE_VIEW_SELECTOR = BITCHUTE_VIDEO["view_count"]["primary"]
    VIDEO_PAGE_DATE_SELECTOR = BITCHUTE_VIDEO["upload_date"]["primary"]
    VIDEO_PAGE_COMMENT_SELECTOR = BITCHUTE_VIDEO["comment_count"]["primary"]
    VIDEO_PAGE_SUBSCRIBERS_SELECTOR = BITCHUTE_VIDEO["subscriber_count"]["primary"]
    VIDEO_PAGE_LINKS_SELECTOR = BITCHUTE_VIDEO["external_links"]["primary"]

    async def scrape(self, channel_url: str) -> dict[str, object]:
        """Scrape a single BitChute channel."""
        try:
            stage_t0 = perf_counter()
            stage_marks: list[tuple[str, float]] = []
            telemetry = BrowserTelemetry()
            channel_base_url = self._channel_base_url(channel_url)
            videos_url = self._channel_tab_url(channel_base_url, "videos")
            about_url = self._channel_tab_url(channel_base_url, "about")
            session_key = self._session_key or channel_base_url
            async with launch_browser(session_key=session_key, telemetry=telemetry) as context:
                page = await context.new_page()
                # Warm-up: visit the homepage first on cold sessions (no cf_clearance).
                # Real users arrive at channel URLs via navigation history, not cold direct access.
                # Sessions restored from persistent storage already have cookies; skip warm-up.
                if await is_cold_session(context):
                    await pre_warm_homepage(
                        page, BITCHUTE_BASE_URL + "/", session_key=session_key
                    )
                response = await guarded_goto(
                    page,
                    channel_base_url,
                    session_key=session_key,
                    wait_until="domcontentloaded",
                    timeout=self.CHANNEL_NAV_TIMEOUT_MS,
                )
                stage_marks.append(("goto_domcontentloaded", perf_counter() - stage_t0))
                content_ok = await wait_for_content(
                    page, min_bytes=5000, timeout_s=self.PRIMARY_CONTENT_TIMEOUT_S
                )
                if not content_ok:
                    logger.warning("BitChute: content not ready, reloading %s", channel_url)
                    await page.reload(
                        wait_until="domcontentloaded", timeout=self.CHANNEL_NAV_TIMEOUT_MS
                    )
                    await human_delay(0.15, 0.35)
                    content_ok = await wait_for_content(
                        page, min_bytes=5000, timeout_s=self.RELOAD_CONTENT_TIMEOUT_S
                    )
                runtime = get_runtime_settings()
                if not content_ok and runtime.scraper_challenge_second_cycle_enabled:
                    logger.warning(
                        "BitChute: second settle cycle for potential CF challenge %s",
                        channel_url,
                    )
                    second_pre = max(
                        0.0, runtime.scraper_challenge_second_cycle_pre_reload_delay_seconds
                    )
                    second_post = max(
                        0.0, runtime.scraper_challenge_second_cycle_post_reload_delay_seconds
                    )
                    second_wait = max(
                        0.1, runtime.scraper_challenge_second_cycle_wait_timeout_seconds
                    )
                    await human_delay(second_pre * 0.7, second_pre * 1.4)
                    await page.reload(
                        wait_until="domcontentloaded", timeout=self.CHANNEL_NAV_TIMEOUT_MS
                    )
                    await human_delay(second_post * 0.7, second_post * 1.4)
                    content_ok = await wait_for_content(
                        page,
                        min_bytes=5000,
                        timeout_s=max(
                            0.1, min(second_wait, self.SECOND_CYCLE_CONTENT_TIMEOUT_S)
                        ),
                    )
                stage_marks.append(("challenge_resolution", perf_counter() - stage_t0))

                await self.ensure_not_blocked(page, channel_url)
                if not content_ok:
                    raise ScraperBlockedError(f"BitChute page empty after reload: {channel_url}")
                current_html = await page.content()
                if len(current_html) < 1000:
                    raise ScraperBlockedError(
                        f"BitChute page appears unresolved challenge stub: {channel_url} bytes={len(current_html)}"
                    )
                home_soup = BeautifulSoup(current_html, "lxml")
                home_page_title = await page.title() or ""
                response_status = response.status if response is not None else None
                home_body_text = home_soup.get_text(" ", strip=True).lower()
                self.classify_terminal_page_state(
                    channel_url=channel_base_url,
                    page_title=home_page_title,
                    current_url=page.url,
                    body_text=home_body_text,
                    response_status=response_status,
                )
                # Since videos tab URL is identical to the base URL on BitChute,
                # we don't need to perform an extra goto navigation if we are already there.
                if page.url != videos_url:
                    await guarded_goto(
                        page,
                        videos_url,
                        session_key=session_key,
                        wait_until="domcontentloaded",
                        timeout=self.CHANNEL_NAV_TIMEOUT_MS,
                    )
                    videos_content_ok = await wait_for_content(
                        page, min_bytes=5000, timeout_s=self.PRIMARY_CONTENT_TIMEOUT_S
                    )
                    await self.ensure_not_blocked(page, videos_url)
                    if not videos_content_ok:
                        raise ScraperBlockedError(f"BitChute videos tab empty after load: {videos_url}")
                await self._ensure_videos_tab_active(page)

                try:
                    await page.wait_for_selector(
                        self.VIDEO_CARD_SELECTOR,
                        timeout=self.CARD_SELECTOR_TIMEOUT_MS,
                    )
                except PlaywrightError:
                    logger.warning(
                        "BitChute: video grid did not render before parsing %s",
                        channel_url,
                    )

                video_data_map, soup = await self._collect_videos_with_scroll(page)
                if not video_data_map:
                    logger.warning(
                        "BitChute: no videos parsed from videos-tab selectors for %s",
                        videos_url,
                    )
                stage_marks.append(("fast_path_card_parse", perf_counter() - stage_t0))
                page_title = await page.title() or ""
                body_text = soup.get_text(" ", strip=True).lower()
                self.classify_terminal_page_state(
                    channel_url=channel_base_url,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=None,
                )

                about_profile = await self._fetch_about_profile_data(
                    page, about_url, session_key, channel_base_url, page_title
                )
                about_fetch_ok = bool(about_profile.get("fetch_ok"))
                name = str(about_profile.get("name") or "").strip()
                description = str(about_profile.get("description") or "")
                subscriber_count = about_profile.get("subscriber_count")
                stage_marks.append(("about_page_description", perf_counter() - stage_t0))
                about_socials = list(about_profile.get("external_links") or [])
                about_contact_soup = about_profile.get("soup") or soup
                if not about_fetch_ok:
                    # Optional resilience fallback only when About navigation fails.
                    name = self._extract_name(soup, channel_base_url, page_title)
                    subscriber_count = self._extract_subscribers(soup)

                (
                    comment_pages_attempted,
                    comment_pages_blocked,
                    comment_pages_parsed_success,
                    comment_selectors_hit,
                    comment_selector_hits_by_video,
                    video_page_subscribers,
                    video_page_links,
                    video_page_title,
                    video_page_description,
                ) = await self._enrich_latest_video_page_comments(context, video_data_map)
                stage_marks.append(("video_page_comments", perf_counter() - stage_t0))

                if subscriber_count is None:
                    if video_page_subscribers is not None:
                        subscriber_count = video_page_subscribers

                description_fallback_used = self._is_generic_description(description)
                if description_fallback_used:
                    logger.info(
                        "BitChute description is generic fallback text for %s; persisting empty description",
                        channel_url,
                    )
                    description = ""

                all_secondary = sorted(set(about_socials + video_page_links))
                combined_text = f"{description}\n{about_contact_soup.get_text(' ', strip=True) if about_contact_soup else ''}"
                emails = self._extract_mailto_emails(about_contact_soup) if about_contact_soup else []
                emails.extend(extract_emails(combined_text))
                urls = extract_urls(combined_text)
                contact_info = self._filter_contact_info(
                    sorted(set(emails + urls + all_secondary))
                )
                stage_marks.append(("about_and_contact", perf_counter() - stage_t0))

                video_titles = [
                    str(video["title"])
                    for video in video_data_map.values()
                    if video.get("title")
                ][: self.VIDEO_COLLECTION_LIMIT]
                # Sample view counts from the first 3 video cards only (no video-page navigation).
                view_counts = [
                    float(video["views"])
                    for video in list(video_data_map.values())[:3]
                    if video.get("views") is not None
                ]
                comment_counts = [
                    float(video["comments"])
                    for video in self._last_comment_page_items(video_data_map)
                    if video.get("comments") is not None
                ]
                upload_dates = [
                    video["date"]
                    for video in video_data_map.values()
                    if isinstance(video.get("date"), datetime)
                ][: self.VIDEO_COLLECTION_LIMIT]

                # Mean of up to 3 card view samples, rounded to nearest integer.
                avg_views = round(sum(view_counts) / len(view_counts)) if view_counts else None
                # Mean of up to 3 video-page comment samples; 0s included, Nones excluded.
                avg_comments = round(sum(comment_counts) / len(comment_counts)) if comment_counts else None
                is_empty_channel = (
                    not video_titles and self._has_empty_channel_marker(body_text)
                )
                if not video_titles and not is_empty_channel:
                    # Let require_scrape_quality handle empty videos
                    pass
                elif avg_comments is None:
                    reason = (
                        "parse_missing_avg_comments_cf_blocked"
                        if comment_pages_attempted > 0 and comment_pages_attempted == comment_pages_blocked
                        else "parse_missing_avg_comments_selector_miss"
                    )
                    raise ScraperClassifiedError(
                        reason,
                        f"No comment counts extracted from latest video pages for {channel_base_url}",
                        terminal=False,
                        retryable=True,
                    )
                comment_tier = compute_comment_tier(avg_comments)
                demographic = compute_channel_demographic(
                    name, description, video_titles[: self.DEMOGRAPHIC_TITLE_LIMIT]
                )
                posts_per_week = self.compute_posting_cadence(upload_dates)
                if posts_per_week is None:
                    # Covers: no dates, single date, or multiple dates all on the
                    # same day (total_days == 0). Can't derive a weekly cadence
                    # from the card-level sample in any of these cases.
                    posts_per_week = 0.0
                last_active_date = max(upload_dates).date() if upload_dates else None
                is_empty_channel = (
                    not video_titles and self._has_empty_channel_marker(body_text)
                )
                if is_empty_channel:
                    raise ScraperClassifiedError(
                        "no_videos_found",
                        f"Channel has no videos: {channel_base_url}",
                        terminal=True,
                        retryable=False,
                    )
                logger.info(
                    "BitChute extraction quality for %s: videos=%d views=%d comments=%d dates=%d",
                    channel_base_url,
                    min(self.VIDEO_COLLECTION_LIMIT, len(video_data_map)),
                    len(view_counts),
                    len(comment_counts),
                    len(upload_dates),
                )

                missing_fields: list[str] = []
                if subscriber_count is None:
                    missing_fields.append("subscriber_count")
                if not video_titles:
                    missing_fields.append("video_titles")
                if avg_views is None:
                    missing_fields.append("avg_views")
                if avg_comments is None:
                    missing_fields.append("avg_comments")
                if posts_per_week is None:
                    missing_fields.append("posts_per_week")
                if last_active_date is None:
                    missing_fields.append("last_active_date")

                self.require_scrape_quality(
                    channel_url=channel_base_url,
                    video_titles=video_titles,
                    subscriber_count=subscriber_count,
                    avg_views=avg_views,
                    avg_comments=avg_comments,
                    posts_per_week=posts_per_week,
                    last_active_date=last_active_date,
                    contact_info=contact_info,
                    secondary_urls=all_secondary,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=None,
                    allow_empty_channel=False,
                )

                channel_data = {
                    "platform": "bitchute",
                    "channel_url": channel_base_url,
                    "name": name,
                    "description": description,
                    "subscriber_count": subscriber_count,
                    "avg_views": avg_views,
                    "avg_comments": avg_comments,
                    "comment_tier": comment_tier,
                    "posts_per_week": posts_per_week,
                    "last_active_date": last_active_date.isoformat()
                    if last_active_date
                    else None,
                    "contact_info": contact_info,
                    "niche_tags": demographic["niche_tags"],
                    "video_titles": video_titles,
                    "secondary_urls": all_secondary,
                }

                channel_id = await self.save_to_supabase(channel_data)
                if channel_id:
                    warning = (
                        "reason=parse_partial_data; terminal=false; retryable=false; "
                        f"detail=Missing fields: {', '.join(missing_fields)}"
                        if missing_fields
                        else None
                    )
                    await self.log_scrape_attempt(channel_id, "success", warning)

                logger.info("BitChute scrape complete for %s (%s)", name, channel_base_url)
                stage_marks.append(("persist", perf_counter() - stage_t0))
                stage_log = ", ".join(
                    f"{stage}={elapsed:.2f}s" for stage, elapsed in stage_marks
                )
                logger.info("BitChute stage timings for %s: %s", channel_base_url, stage_log)
                total_duration_s = perf_counter() - stage_t0
                logger.info(
                    "SCRAPE_PERF_SUMMARY platform=%s channel=%s duration_s=%.2f "
                    "bytes_est=%d responses=%d videos_considered=%d view_samples=%d "
                    "comment_samples=%d date_samples=%d",
                    "bitchute",
                    channel_base_url,
                    total_duration_s,
                    telemetry.total_bytes_est,
                    telemetry.response_count,
                    min(self.VIDEO_COLLECTION_LIMIT, len(video_data_map)),
                    len(view_counts),
                    len(comment_counts),
                    len(upload_dates),
                )
                logger.info(
                    "BitChute transfer estimate for %s: responses=%d bytes_est=%d",
                    channel_base_url,
                    telemetry.response_count,
                    telemetry.total_bytes_est,
                )
                channel_data["_scrape_metrics"] = {
                    "bytes_est": telemetry.total_bytes_est,
                    "responses": telemetry.response_count,
                    "geoip_enabled": telemetry.geoip_enabled,
                    "description_fallback_used": description_fallback_used,
                    "comment_pages_attempted": comment_pages_attempted,
                    "comment_pages_blocked": comment_pages_blocked,
                    "comment_pages_parsed_success": comment_pages_parsed_success,
                    "comment_selectors_hit": sorted(comment_selectors_hit),
                    "comment_selector_hits_by_video": comment_selector_hits_by_video,
                }
                return channel_data

        except (PlaywrightError, ScraperBlockedError, ScraperClassifiedError) as exc:
            logger.error("BitChute scrape failed for %s: %s", channel_url, exc)
            raise

    def _channel_base_url(self, channel_url: str) -> str:
        """Return the canonical BitChute channel surface without tab suffixes."""
        parsed = urlsplit(channel_url.strip())
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or "www.bitchute.com"
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[-1].lower() in {"videos", "about", "shorts", "livestreams", "live"}:
            parts = parts[:-1]
        path = "/" + "/".join(parts) if parts else "/"
        return urljoin(f"{scheme}://{netloc}", path).rstrip("/")

    def _channel_tab_url(self, channel_base_url: str, tab: str) -> str:
        """Build an explicit BitChute channel tab URL."""
        if tab.strip().lower() == "videos":
            return channel_base_url
        return f"{channel_base_url.rstrip('/')}/{tab.strip('/')}"

    async def _fetch_about_profile_data(
        self,
        page,
        about_url: str,
        session_key: str,
        channel_url: str,
        page_title: str,
    ) -> dict[str, object]:
        """Navigate to the About tab and extract profile fields from that surface."""
        try:
            await inter_request_jitter()
            about_opened = await self._open_about_tab(page)
            if not about_opened:
                await guarded_goto(
                    page,
                    about_url,
                    session_key=session_key,
                    wait_until="domcontentloaded",
                    timeout=self.ABOUT_NAV_TIMEOUT_MS,
                )
            await wait_for_content(page, min_bytes=3000, timeout_s=self.ABOUT_CONTENT_TIMEOUT_S)
            about_html = await page.content()
            # Targets: <div style="white-space: pre-line;">channel bio text</div>
            # Only present on the /about/ tab, not the videos page.
            about_soup = BeautifulSoup(about_html, "lxml")
            return {
                "fetch_ok": True,
                "name": self._extract_name(about_soup, channel_url, page_title),
                "description": self._extract_description(about_soup),
                "subscriber_count": self._extract_subscribers(about_soup),
                "external_links": self._extract_external_links(about_soup, channel_url),
                "soup": about_soup,
            }
        except Exception as exc:
            logger.warning(
                "BitChute: about page fetch failed, profile fields will use fallbacks for %s: %s",
                about_url,
                exc,
            )
            return {
                "fetch_ok": False,
                "name": "",
                "description": "",
                "subscriber_count": None,
                "external_links": [],
                "soup": None,
            }

    async def _open_about_tab(self, page) -> bool:
        """Open About tab via client-side tab switch when available."""
        clicked = False
        for action in (
            lambda: page.get_by_role("tab", name="About").click(timeout=3500),
            lambda: page.locator("div.q-tab__label", has_text="About").first.click(timeout=3500),
            lambda: page.locator("text=About").first.click(timeout=3500),
        ):
            try:
                await action()
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            return False
        await human_delay(0.1, 0.3)
        try:
            await page.wait_for_function(
                """() => {
                    const text = (document.body?.innerText || "").toLowerCase();
                    return text.includes("channel detail") || text.includes("description");
                }""",
                timeout=3500,
            )
        except Exception:
            pass
        return True

    def _extract_name(self, soup: BeautifulSoup, channel_url: str, page_title: str) -> str:
        """Extract channel name from the channel-home header selector."""
        node = soup.select_one(self.CHANNEL_NAME_SELECTOR)
        if node is not None:
            name = node.get_text(" ", strip=True)
            if name:
                return name
        for fallback in BITCHUTE_CHANNEL["channel_name"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                name = node.get_text(" ", strip=True)
                if name:
                    return name

        title = re.sub(r"\s*[-|]\s*BitChute\s*$", "", page_title, flags=re.I).strip()
        if title:
            return title
        return channel_url.rstrip("/").split("/")[-1]

    def _extract_subscribers(self, soup: BeautifulSoup) -> int | None:
        """Extract subscriber count from the subscriber count selector or fallbacks."""
        node = soup.select_one(self.CHANNEL_FOLLOWERS_SELECTOR)
        if node is not None:
            return parse_count_text(node.get_text(" ", strip=True))
        for fallback in BITCHUTE_CHANNEL["subscriber_count"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                return parse_count_text(node.get_text(" ", strip=True))
        return None

    async def _collect_videos_with_scroll(self, page) -> tuple[dict[str, dict[str, object]], BeautifulSoup]:
        """Collect a deeper recent-video window across scrolls and paginated pages."""
        collected: dict[str, dict[str, object]] = {}
        visited_pages: set[str] = set()
        max_pages = 3

        last_soup = BeautifulSoup(await page.content(), "lxml")
        for _ in range(max_pages):
            current_page_url = page.url
            if current_page_url in visited_pages:
                break
            visited_pages.add(current_page_url)

            stagnant_rounds = 0
            next_page_url: str | None = None
            for _ in range(4):
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")
                last_soup = soup
                parsed = self._extract_videos(soup)
                before = len(collected)
                for video_id, payload in parsed.items():
                    if video_id not in collected:
                        collected[video_id] = payload

                if len(collected) >= self.VIDEO_COLLECTION_LIMIT:
                    break

                next_page_url = self._extract_next_page_url(soup, page.url)
                stagnant_rounds = stagnant_rounds + 1 if len(collected) == before else 0
                if stagnant_rounds >= 1 and next_page_url:
                    break
                if stagnant_rounds >= 2:
                    break

                prev_count = len(collected)
                await human_scroll(page, direction="down", steps=4)
                try:
                    await page.wait_for_function(
                        "(selector, prev) => document.querySelectorAll(selector).length > prev",
                        self.VIDEO_CARD_SELECTOR,
                        prev_count,
                        timeout=2500,
                    )
                except Exception:
                    await human_delay(0.05, 0.2)

            if len(collected) >= self.VIDEO_COLLECTION_LIMIT:
                break
            if not next_page_url or next_page_url in visited_pages:
                break
            try:
                await guarded_goto(
                    page,
                    next_page_url,
                    session_key=self._session_key or next_page_url,
                    wait_until="domcontentloaded",
                    timeout=self.CHANNEL_NAV_TIMEOUT_MS,
                )
                await page.wait_for_selector(self.VIDEO_CARD_SELECTOR, timeout=2500)
            except PlaywrightError as exc:
                logger.debug("BitChute: Could not follow next page %s: %s", next_page_url, exc)
                break

        return self._trim_video_map(collected), last_soup

    async def _ensure_videos_tab_active(self, page) -> None:
        """Open the Videos tab when channel home renders without video cards."""
        try:
            has_video_cards = await page.locator(self.VIDEO_LINK_SELECTOR).count()
        except Exception:
            has_video_cards = 0
        if has_video_cards > 0:
            return

        clicked = False
        try:
            await page.get_by_role("tab", name="Videos").click(timeout=4000)
            clicked = True
        except Exception:
            try:
                await page.locator("div.q-tab__label", has_text="Videos").first.click(timeout=4000)
                clicked = True
            except Exception:
                clicked = False

        if clicked:
            await human_delay(0.2, 0.6)
            try:
                await page.wait_for_selector(self.VIDEO_LINK_SELECTOR, timeout=6000)
            except Exception:
                pass

    def _extract_next_page_url(self, soup: BeautifulSoup, base_url: str) -> str | None:
        """Extract the next pagination URL (not applicable for infinite scroll)."""
        return None

    def _trim_video_map(
        self, video_map: dict[str, dict[str, object]]
    ) -> dict[str, dict[str, object]]:
        """Keep insertion order while limiting the extracted recent-video window."""
        if len(video_map) <= self.VIDEO_COLLECTION_LIMIT:
            return video_map
        trimmed: dict[str, dict[str, object]] = {}
        for idx, (video_id, payload) in enumerate(video_map.items()):
            if idx >= self.VIDEO_COLLECTION_LIMIT:
                break
            trimmed[video_id] = payload
        return trimmed

    def _extract_videos(self, soup: BeautifulSoup) -> dict[str, dict[str, object]]:
        """Extract recent videos from the videos tab using the supplied card selectors."""
        video_map: dict[str, dict[str, object]] = {}
        cards = soup.select(self.VIDEO_CARD_SELECTOR)
        if not cards:
            for fallback in BITCHUTE_CHANNEL["video_card"]["fallbacks"]:
                cards = soup.select(fallback)
                if cards:
                    break

        for card in cards:
            if len(video_map) >= self.VIDEO_COLLECTION_LIMIT or not isinstance(card, Tag):
                break
            if card.name == "a" and card.has_attr("href") and self._is_video_href(str(card.get("href") or "")):
                link = card
            else:
                link = card.select_one("a[href^=\"/video/\"], a[href*=\"/video/\"]")
            if not isinstance(link, Tag):
                continue
            href = str(link.get("href") or "")
            if not self._is_video_href(href):
                continue
            video_url = urljoin(BITCHUTE_BASE_URL, href)
            video_id = urlsplit(video_url).path.rstrip("/").split("/")[-1]
            if not video_id or video_id in video_map:
                continue

            title = self._extract_video_title(card, link)
            views = self._extract_card_views(card)
            date_val = self._extract_card_date(card)

            video_map[video_id] = {
                "title": title or "Unknown Title",
                "views": views,
                "comments": None,
                "date": date_val,
                "url": video_url,
            }
        return video_map

    def _is_video_href(self, href: str) -> bool:
        """Return True for canonical BitChute video links, excluding nav paths."""
        path = urlsplit(urljoin(BITCHUTE_BASE_URL, href)).path.rstrip("/")
        return "/video/" in path

    def _merge_video_page_signals(
        self,
        *,
        item: dict[str, object],
        needs_title: bool,
        needs_views: bool,
        needs_comment: bool,
        needs_date: bool,
        title: str | None,
        views: int | None,
        comments: int | None,
        publish_date: datetime | None,
    ) -> None:
        """Merge deeper video-page metadata without overwriting card data."""
        if (needs_title or self._is_invalid_video_title(item.get("title"))) and title:
            item["title"] = title
        if needs_views and views is not None:
            item["views"] = views
        if needs_comment and comments is not None:
            item["comments"] = comments
        if needs_date and publish_date is not None:
            item["date"] = publish_date

    def _is_invalid_video_title(self, title: object) -> bool:
        """Detect overlay metric text accidentally captured from video thumbnails."""
        text = str(title or "").strip()
        if not text or text == "Unknown Title":
            return True
        compact = " ".join(text.lower().split())
        if not compact:
            return True
        if compact.startswith("visibility ") and re.search(r"\d", compact):
            return True
        return bool(re.fullmatch(r"(?:\d[\d,\.]*\s+)?\d{1,2}:\d{2}(?::\d{2})?", compact))

    def _video_signal_counts(
        self, video_data_map: dict[str, dict[str, object]]
    ) -> dict[str, int]:
        """Count extracted signals to gate fallback work conservatively."""
        items = list(video_data_map.values())[: self.VIDEO_COLLECTION_LIMIT]
        valid_titles = sum(1 for item in items if item.get("title"))
        valid_views = sum(
            1
            for item in items
            if isinstance(item.get("views"), (int, float))
            and float(item["views"]) > 0
        )
        valid_comments = sum(
            1
            for item in items
            if isinstance(item.get("comments"), (int, float))
            and float(item["comments"]) >= 0
        )
        valid_dates = sum(
            1 for item in items if isinstance(item.get("date"), datetime)
        )
        return {
            "valid_titles": valid_titles,
            "valid_views": valid_views,
            "valid_comments": valid_comments,
            "valid_dates": valid_dates,
        }

    def _last_comment_page_items(
        self, video_data_map: dict[str, dict[str, object]]
    ) -> list[dict[str, object]]:
        """Return exactly the latest N videos to open for comment extraction."""
        items = list(video_data_map.values())[: self.VIDEO_COLLECTION_LIMIT]
        return items[: self.COMMENT_VIDEO_PAGE_SAMPLE_LIMIT]

    async def _enrich_latest_video_page_comments(
        self,
        context,
        video_data_map: dict[str, dict[str, object]],
    ) -> tuple[
        int,
        int,
        int,
        set[str],
        list[dict[str, object]],
        int | None,
        list[str],
        str | None,
        str | None,
    ]:
        """Fetch video-page comments for the latest three uploaded videos."""
        attempted = 0
        blocked = 0
        parsed_success = 0
        selectors_hit: set[str] = set()
        per_video_selector_hits: list[dict[str, object]] = []
        extracted_subs: int | None = None
        extracted_links: list[str] = []
        extracted_title: str | None = None
        extracted_desc: str | None = None
        for item in self._last_comment_page_items(video_data_map):
            video_url = str(item.get("url") or "").strip()
            if not video_url:
                continue
            views, comments, publish_date, subscribers, links, title, description, comment_hit_selector, blocked_stub = (
                await self._extract_video_page_signals(context, video_url)
            )
            attempted += 1
            if blocked_stub:
                blocked += 1
            if comment_hit_selector:
                selectors_hit.add(comment_hit_selector)
            if comments is not None:
                parsed_success += 1
            per_video_selector_hits.append(
                {
                    "video_url": video_url,
                    "blocked_stub": blocked_stub,
                    "comment_selector": comment_hit_selector,
                    "comment_found": comments is not None,
                    "views_found": views is not None,
                    "date_found": publish_date is not None,
                    "subscribers_found": subscribers is not None,
                    "title_found": bool(title),
                    "description_found": bool(description),
                }
            )
            if subscribers is not None and extracted_subs is None:
                extracted_subs = subscribers
            if links:
                extracted_links.extend(links)
            if title and not extracted_title:
                extracted_title = title
            if description and not extracted_desc:
                extracted_desc = description
            self._merge_video_page_signals(
                item=item,
                needs_title=self._is_invalid_video_title(item.get("title")),
                needs_views=item.get("views") is None,
                needs_comment=item.get("comments") is None,
                needs_date=item.get("date") is None,
                title=title,
                views=views,
                comments=comments,
                publish_date=publish_date,
            )
        return (
            attempted,
            blocked,
            parsed_success,
            selectors_hit,
            per_video_selector_hits,
            extracted_subs,
            sorted(set(extracted_links)),
            extracted_title,
            extracted_desc,
        )

    def _is_generic_description(self, description: str) -> bool:
        return False

    def _filter_contact_info(self, values: list[str]) -> list[str]:
        filtered: list[str] = []
        for value in values:
            stripped = (value or "").strip()
            if not stripped:
                continue
            host = (urlsplit(stripped).hostname or "").lower()
            if host in _EXCLUDED_CONTACT_DOMAINS:
                continue
            filtered.append(stripped)
        return sorted(set(filtered))

    async def _extract_video_page_signals(
        self, context, video_url: str
    ) -> tuple[int | None, int | None, datetime | None, int | None, list[str], str | None, str | None, str | None, bool]:
        """Open a BitChute video page and extract missing views, comments, date, subscribers, and links."""
        page = await context.new_page()
        try:
            await inter_request_jitter()
            await guarded_goto(
                page,
                video_url,
                session_key=self._session_key or video_url,
                wait_until="domcontentloaded",
                timeout=self.VIDEO_PAGE_TIMEOUT_MS,
            )
            content_ok = await wait_for_content(
                page, min_bytes=5000, timeout_s=self.VIDEO_PAGE_CONTENT_TIMEOUT_S
            )
            html_now = await page.content()
            if not content_ok or len(html_now) < 1000:
                raise ScraperBlockedError(
                    f"BitChute video page unresolved challenge stub: {video_url} bytes={len(html_now)}"
                )
            try:
                await human_scroll(page, direction="down", steps=2)
                await self._wait_for_video_page_comment_state(page)
            except Exception:
                pass
            html_now = await page.content()

            soup = BeautifulSoup(html_now, "lxml")
            views = self._extract_video_page_views(soup)
            comments, comment_hit_selector = self._extract_video_page_comments(soup)
            if comments is None:
                # CommentFreely occasionally hydrates late and first-pass snapshots
                # only contain placeholder "( ? )" counters.
                try:
                    await human_delay(0.4, 0.9)
                    await human_scroll(page, direction="down", steps=1)
                    await self._wait_for_video_page_comment_state(page)
                except Exception:
                    pass
                html_now = await page.content()
                soup = BeautifulSoup(html_now, "lxml")
                comments, comment_hit_selector = self._extract_video_page_comments(soup)
            if (
                comments is None
                and self._has_unresolved_comment_placeholder(soup)
            ):
                # One extra targeted re-check for unresolved "( ? )" counter states.
                try:
                    await human_delay(0.5, 1.0)
                    await human_scroll(page, direction="down", steps=1)
                    await self._wait_for_video_page_comment_state(page)
                except Exception:
                    pass
                html_now = await page.content()
                soup = BeautifulSoup(html_now, "lxml")
                comments, comment_hit_selector = self._extract_video_page_comments(soup)
            publish_date = self._extract_video_page_upload_date(soup)
            subscribers = self._extract_video_page_subscribers(soup)
            links = self._extract_video_page_external_links(soup)
            title = self._extract_video_page_title(soup)
            description = self._extract_video_page_description(soup)

            return views, comments, publish_date, subscribers, links, title, description, comment_hit_selector, False
        except ScraperBlockedError:
            return None, None, None, None, [], None, None, None, True
        except Exception as exc:
            logger.debug("BitChute: Could not extract video signals from %s: %s", video_url, exc)
            return None, None, None, None, [], None, None, None, False
        finally:
            await page.close()

    async def _wait_for_video_page_comment_state(self, page) -> None:
        """Wait until comments resolve to a usable state."""
        # A usable state is any of:
        # 1) numeric comment count value appears,
        # 2) rendered comment nodes are present,
        # 3) explicit no-comments marker/text is visible.
        predicate = """() => {
            const container = document.querySelector("#comments-container");
            if (!container) return false;
            const valueNodes = container.querySelectorAll("span.item.count span.value");
            for (const node of valueNodes) {
                const text = (node.textContent || "").trim();
                if (/\\d/.test(text)) return true;
            }
            if (container.querySelector("#comment-list .comment")) return true;
            const lowered = (container.textContent || "").toLowerCase();
            if (lowered.includes("no comments") || lowered.includes("be the first to comment")) return true;
            if (container.querySelector("div.no-comments.no-data")) return true;
            return false;
        }"""
        try:
            await page.wait_for_function(
                predicate,
                timeout=self.VIDEO_PAGE_COMMENT_SHORT_TIMEOUT_MS,
            )
        except Exception:
            await page.wait_for_function(
                predicate,
                timeout=self.VIDEO_PAGE_COMMENT_TIMEOUT_MS,
            )

    def _extract_video_page_views(self, soup: BeautifulSoup) -> int | None:
        # Try specific CSS selectors FIRST — these are scoped to the main video
        # detail area and won't be confused by related-video cards that also
        # carry visibility chips on the full page.
        node = soup.select_one(self.VIDEO_PAGE_VIEW_SELECTOR)
        if node is not None:
            text = node.get_text(" ", strip=True)
            if "view" in text.lower():
                parsed = parse_bitchute_views(text)
                if parsed is not None:
                    return parsed
        for fallback in BITCHUTE_VIDEO["view_count"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                text = node.get_text(" ", strip=True)
                if "view" in text.lower():
                    parsed = parse_bitchute_views(text)
                    if parsed is not None:
                        return parsed
        # Chip scan as last resort — operates on the full page soup so it can
        # accidentally pick up related-video chips; only reached if the specific
        # selectors above found nothing.
        return self._extract_views_from_visibility_chip(soup)

    def _extract_video_page_comments(self, soup: BeautifulSoup) -> tuple[int | None, str | None]:
        selectors = [
            self.VIDEO_PAGE_COMMENT_SELECTOR,
            *BITCHUTE_VIDEO["comment_count"]["fallbacks"],
        ]
        seen_selectors: set[str] = set()
        for selector in selectors:
            if selector in seen_selectors:
                continue
            seen_selectors.add(selector)
            for node in soup.select(selector):
                parsed = parse_count_text(node.get_text(" ", strip=True))
                if parsed is not None:
                    return parsed, selector

        container = soup.select_one("#comments-container")
        if container is not None:
            for selector in (
                ".navigation .item.count .value",
                ".navigation .item.count",
                "span.item.count span.value",
                "span.item.count",
            ):
                node = container.select_one(selector)
                if node is not None:
                    parsed = parse_count_text(node.get_text(" ", strip=True))
                    if parsed is not None:
                        return parsed, f"#comments-container {selector}"

            text = container.get_text(" ", strip=True)
            match = re.search(
                r"\(\s*([\d,]+(?:\.\d+)?\s*[kmbKMB]?)\s*\)\s*(?:Newest|Oldest|Popular)",
                text,
            )
            if match:
                parsed = parse_count_text(match.group(1))
                if parsed is not None:
                    return parsed, "#comments-container text-count"

            comment_nodes = container.select("#comment-list .comment")
            if comment_nodes:
                return len(comment_nodes), "#comment-list .comment"

            lowered = text.lower()
            if "no comments" in lowered or "be the first to comment" in lowered:
                return 0, "#comments-container"

        marker = soup.select_one("#comments-container div.no-comments.no-data, div.no-comments.no-data")
        if marker is not None and soup.select_one("#comment-list .comment") is None:
            return 0, "div.no-comments.no-data"
        return None, None

    def _has_unresolved_comment_placeholder(self, soup: BeautifulSoup) -> bool:
        container = soup.select_one("#comments-container")
        if container is None:
            return False
        if container.select_one("#comment-list .comment") is not None:
            return False
        value_nodes = container.select("span.item.count span.value")
        if not value_nodes:
            return False
        for node in value_nodes:
            text = node.get_text(" ", strip=True)
            if "?" in text:
                return True
        return False

    def _extract_video_page_upload_date(self, soup: BeautifulSoup) -> datetime | None:
        node = soup.select_one(self.VIDEO_PAGE_DATE_SELECTOR)
        if node is not None:
            text = node.get_text(" ", strip=True).lstrip("-").strip()
            parsed = parse_bitchute_datetime(text)
            if parsed is not None:
                return parsed
        for fallback in BITCHUTE_VIDEO["upload_date"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                text = node.get_text(" ", strip=True).lstrip("-").strip()
                # Common pattern: "<views> Views - <relative date> ...Show more"
                if " - " in text:
                    text = text.split(" - ", 1)[1].split("...Show more", 1)[0].strip()
                parsed = parse_bitchute_datetime(text)
                if parsed is not None:
                    return parsed
        return None

    def _extract_video_page_subscribers(self, soup: BeautifulSoup) -> int | None:
        node = soup.select_one(self.VIDEO_PAGE_SUBSCRIBERS_SELECTOR)
        if node is not None:
            return parse_count_text(node.get_text(" ", strip=True))
        for fallback in BITCHUTE_VIDEO["subscriber_count"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                return parse_count_text(node.get_text(" ", strip=True))
        return None

    def _extract_video_page_external_links(self, soup: BeautifulSoup) -> list[str]:
        links: set[str] = set()
        for anchor in soup.select(self.VIDEO_PAGE_LINKS_SELECTOR):
            href = str(anchor.get("href") or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            absolute = urljoin(BITCHUTE_BASE_URL, href)
            if "bitchute.com" not in absolute:
                links.add(absolute)
        return sorted(links)

    def _extract_video_page_title(self, soup: BeautifulSoup) -> str:
        node = soup.select_one(self.VIDEO_PAGE_TITLE_SELECTOR)
        if node is not None:
            title = node.get_text(" ", strip=True)
            if title:
                return title
        for fallback in BITCHUTE_VIDEO["title"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                if node.name == "meta":
                    title = str(node.get("content") or "").strip()
                else:
                    title = node.get_text(" ", strip=True)
                if title:
                    return title
        return ""

    def _extract_video_page_description(self, soup: BeautifulSoup) -> str:
        node = soup.select_one(BITCHUTE_VIDEO["description"]["primary"])
        if node is not None:
            return node.get_text("\n", strip=True)
        for fallback in BITCHUTE_VIDEO["description"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                return node.get_text("\n", strip=True)
        return ""

    def _extract_video_title(self, card: Tag, link: Tag) -> str:
        candidates: list[str] = []
        node = card.select_one(self.VIDEO_TITLE_SELECTOR)
        if node is not None:
            candidates.append(str(node.get("title") or node.get_text(" ", strip=True)).strip())
        for fallback in BITCHUTE_CHANNEL["video_titles"]["fallbacks"]:
            node = card.select_one(fallback)
            if node is not None:
                candidates.append(str(node.get("title") or node.get_text(" ", strip=True)).strip())
        for attr in ["title", "aria-label"]:
            text = str(link.get(attr) or "").strip()
            if text:
                candidates.append(text)
        for text in candidates:
            if text and not self._is_invalid_video_title(text):
                return text
        return ""

    def _extract_card_views(self, card: Tag) -> int | None:
        # 1. Visibility chip: icon-validated, most accurate.
        parsed = self._extract_views_from_visibility_chip(card)
        if parsed is not None:
            return parsed
        # 2. Primary chip-content selector — only accept if "view" keyword present.
        #    BitChute view chips often show a bare number ("324K") without the word
        #    "views"; the chip scan above handles that.  This selector is kept as a
        #    keyword-gated safety net for alternate chip text like "324K Views".
        node = card.select_one(self.VIDEO_VIEWS_SELECTOR)
        if node is not None:
            text = node.get_text(" ", strip=True)
            if "view" in text.lower() and not self._is_duration_text(text):
                parsed = parse_count_text(text)
                if parsed is not None:
                    return parsed
        # 3. Broader text-caption scan — "view" keyword required throughout.
        #    Deliberately avoid a bare parse_count_text() fallback here: other
        #    div.text-caption nodes in the card (date labels, subscriber counts,
        #    duration chips that slipped through) would produce false view counts.
        for node in card.select("div.text-caption"):
            text = node.get_text(" ", strip=True)
            if self._is_duration_text(text):
                continue
            if "view" in text.lower():
                # Handle mixed strings like "324 Views - 3 weeks ago".
                left_segment = text.split("-", 1)[0].strip()
                parsed = parse_count_text(left_segment)
                if parsed is not None:
                    return parsed
        return None

    def _extract_card_date(self, card: Tag) -> datetime | None:
        node = card.select_one(self.VIDEO_TIME_SELECTOR)
        if node is not None:
            parsed = parse_bitchute_datetime(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed
        for node in card.select("div.q-item__label.q-item__label--caption.text-caption"):
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            parsed = parse_bitchute_datetime(text)
            if parsed is not None:
                return parsed
        return None

    def _extract_description(self, soup: BeautifulSoup) -> str:
        node = soup.select_one(self.ABOUT_DESCRIPTION_SELECTOR)
        if node is not None:
            text = node.get_text("\n", strip=True)
            text = re.sub(r"^Description\s*", "", text, flags=re.I).strip()
            if text and len(text) >= 10 and text.lower() not in {"comment", "comments"}:
                return text
        for fallback in BITCHUTE_CHANNEL["channel_description"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                text = node.get_text("\n", strip=True)
                text = re.sub(r"^Description\s*", "", text, flags=re.I).strip()
                if text and len(text) >= 10 and text.lower() not in {"comment", "comments"}:
                    return text
        return ""

    def _extract_external_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        links: set[str] = set()
        for anchor in soup.select(self.ABOUT_SOCIAL_LINKS_SELECTOR):
            href = str(anchor.get("href") or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            absolute = urljoin(base_url, href)
            if "bitchute.com" not in absolute:
                links.add(absolute)
        return sorted(links)

    def _extract_mailto_emails(self, soup: BeautifulSoup) -> list[str]:
        emails: list[str] = []
        for node in soup.select(BITCHUTE_CHANNEL["email_addresses"]["primary"]):
            href = str(node.get("href") or "").strip()
            if href.lower().startswith("mailto:"):
                addr = href.split(":", 1)[1].split("?", 1)[0].strip().lower()
                if addr:
                    emails.append(addr)
        return sorted(set(emails))

    def _has_empty_channel_marker(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        return any(marker in lowered for marker in self._EMPTY_CHANNEL_MARKERS)

    # Regex that matches ONLY a bare count: "324", "1.2K", "333.335K", "2.1M"
    # No letters other than k/m/b suffix, no colons (duration), no words (date).
    _BARE_COUNT_RE = re.compile(r"^[\d,\.]+\s*[kmb]?$", re.I)

    def _extract_views_from_visibility_chip(self, scope: Tag | BeautifulSoup) -> int | None:
        # Pass 1 — icon-validated: requires the Quasar chip to carry a Material
        # Icons ligature with text "visibility".  Most accurate; fails when
        # BitChute renders icons as SVG or Unicode codepoints instead of ligatures.
        for chip in scope.select("div.q-chip"):
            icon = chip.select_one("i.q-chip__icon")
            icon_text = (icon.get_text(" ", strip=True).lower() if icon is not None else "")
            if icon_text != "visibility":
                continue
            value_node = chip.select_one("div.q-chip__content div.text-caption")
            if value_node is None:
                continue
            text = value_node.get_text(" ", strip=True)
            parsed = parse_count_text(text)
            if parsed is not None:
                return parsed

        # Pass 2 — numeric-only chip fallback: when icon text is absent or a
        # codepoint, identify the view-count chip by its content shape.
        # BitChute view-count chips show only a bare number ("324", "333.335K").
        # Duration chips ("10:23") are filtered by _is_duration_text.
        # Date/text nodes ("3 weeks ago") don't match the bare-count pattern.
        for chip in scope.select("div.q-chip"):
            value_node = chip.select_one("div.q-chip__content div.text-caption")
            if value_node is None:
                continue
            text = value_node.get_text(" ", strip=True)
            if self._is_duration_text(text):
                continue
            if self._BARE_COUNT_RE.match(text.strip()):
                parsed = parse_count_text(text)
                if parsed is not None:
                    return parsed
        return None

    def _is_duration_text(self, text: str) -> bool:
        return bool(re.fullmatch(r"\d+:\d{2}(?::\d{2})?", (text or "").strip()))
