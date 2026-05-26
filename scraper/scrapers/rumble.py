"""Rumble scraper with resilient channel-card extraction."""

import asyncio
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
from core.system_settings import get_runtime_settings
from scrapers.base import BaseScraper
from utils.contact_extractor import extract_emails, extract_urls
from utils.keyword_matcher import compute_channel_demographic, compute_comment_tier

logger = logging.getLogger(__name__)

RUMBLE_BASE_URL = "https://rumble.com"
_DESCRIPTION_BOILERPLATE_RE = re.compile(
    r'^browse the most recent videos from channel ".*?" uploaded to rumble\.com$',
    re.I,
)
_EXCLUDED_CONTACT_DOMAINS = {
    "rumble.support",
    "www.rumble.cloud",
    "stickermule.com",
    "www.stickermule.com",
}
RUMBLE_CHANNEL = {
    "channel_name": {
        "primary": r"div.flex.items-center.justify-center.md\:justify-start.mb-1 > h1",
        "fallbacks": [],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
    "channel_description": {
        "primary": ".channel-about--description > p",
        "fallbacks": [],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
    "subscriber_count": {
        "primary": (
            r"span.text-fjord.dark\:text-cloud.text-\[12px\].font-semibold."
            r"flex.items-center.justify-center.md\:justify-start > span"
        ),
        "fallbacks": [],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "video_card": {
        "primary": "div.videostream.thumbnail__grid--item",
        "fallbacks": [],
        "extract": "node",
        "normalize": "none",
        "js_required": False,
    },
    "video_urls": {
        "primary": "a.title__link.link",
        "fallbacks": [],
        "extract": "attr(href)",
        "normalize": "urljoin(base)+canonicalize",
        "js_required": False,
    },
    "video_titles": {
        "primary": "a.title__link.link > h3.thumbnail__title.line-clamp-2",
        "fallbacks": [
            "div.video-header-container__title > h1.h1"
        ],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
    "video_view_counts": {
        "primary": "span.videostream__data--subitem.videostream__views--count",
        "fallbacks": [
            "div.media-description-info-views"
        ],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "video_upload_dates": {
        "primary": "time.videostream__data--subitem.videostream__time",
        "fallbacks": [
            "div.media-description-info-stream-time > div[title]"
        ],
        "extract": "attr(datetime)",
        "normalize": "parse_rumble_datetime()",
        "js_required": False,
    },
    "external_links": {
        "primary": ".channel-about--socials a.channel-about--socials-item[href]",
        "fallbacks": [],
        "extract": "attr(href)",
        "normalize": "exclude_rumble_domain",
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
RUMBLE_VIDEO = {
    "title": {
        "primary": "div.video-header-container__title > h1.h1",
        "fallbacks": [
            "a.title__link.link > h3.thumbnail__title.line-clamp-2"
        ],
        "extract": "text()",
        "normalize": "strip()",
        "js_required": False,
    },
    "view_count": {
        "primary": "div.media-description-info-views",
        "fallbacks": [
            "span.videostream__data--subitem.videostream__views--count"
        ],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "comment_count": {
        "primary": "div.comments-header > h3.comment-count",
        "fallbacks": [],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "upload_date": {
        "primary": "div.media-description-info-stream-time > div[title]",
        "fallbacks": [
            "time.videostream__data--subitem.videostream__time"
        ],
        "extract": "attr(title)",
        "normalize": "parse_rumble_datetime()",
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
        .replace("followers", "")
        .replace("follower", "")
        .replace("subscribers", "")
        .replace("subscriber", "")
        .replace("comments", "")
        .replace("comment", "")
        .replace("views", "")
        .replace("view", "")
        .strip()
    )
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


def parse_follower_count(text: str) -> int | None:
    """Parse '2.18M Followers' -> 2180000."""
    return parse_count_text(text)


def parse_rumble_datetime(dt_str: str) -> datetime | None:
    """Parse Rumble absolute, HTTP-date, and relative date strings."""
    if not dt_str:
        return None
    text = dt_str.strip()
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

    lowered = text.lower()
    now = datetime.now()
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


class RumbleScraper(BaseScraper):
    """Scraper for Rumble channels using Patchright and BeautifulSoup."""

    VIDEO_COLLECTION_LIMIT = 50
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
    VIDEO_PAGE_COMMENT_TIMEOUT_MS = 8000
    _EMPTY_CHANNEL_MARKERS = (
        "0 videos",
        "no videos",
        "this channel has no videos",
        "nothing here yet",
        "no uploads yet",
    )
    VIDEO_CARD_SELECTOR = RUMBLE_CHANNEL["video_card"]["primary"]
    VIDEO_LINK_SELECTOR = RUMBLE_CHANNEL["video_urls"]["primary"]
    VIDEO_TITLE_SELECTOR = RUMBLE_CHANNEL["video_titles"]["primary"]
    VIDEO_TIME_SELECTOR = RUMBLE_CHANNEL["video_upload_dates"]["primary"]
    VIDEO_VIEWS_SELECTOR = RUMBLE_CHANNEL["video_view_counts"]["primary"]
    CHANNEL_NAME_SELECTOR = RUMBLE_CHANNEL["channel_name"]["primary"]
    CHANNEL_FOLLOWERS_SELECTOR = RUMBLE_CHANNEL["subscriber_count"]["primary"]
    ABOUT_DESCRIPTION_SELECTOR = RUMBLE_CHANNEL["channel_description"]["primary"]
    ABOUT_SOCIAL_LINKS_SELECTOR = RUMBLE_CHANNEL["external_links"]["primary"]
    VIDEO_PAGE_TITLE_SELECTOR = RUMBLE_VIDEO["title"]["primary"]
    VIDEO_PAGE_VIEW_SELECTOR = RUMBLE_VIDEO["view_count"]["primary"]
    VIDEO_PAGE_DATE_SELECTOR = RUMBLE_VIDEO["upload_date"]["primary"]
    VIDEO_PAGE_COMMENT_SELECTOR = RUMBLE_VIDEO["comment_count"]["primary"]

    async def scrape(self, channel_url: str) -> dict[str, object]:
        """Scrape a single Rumble channel."""
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
                        page, RUMBLE_BASE_URL + "/", session_key=session_key
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
                    page, timeout_s=self.PRIMARY_CONTENT_TIMEOUT_S
                )
                if not content_ok:
                    logger.warning("Rumble: content not ready, reloading %s", channel_url)
                    await page.reload(
                        wait_until="domcontentloaded", timeout=self.CHANNEL_NAV_TIMEOUT_MS
                    )
                    await human_delay(0.15, 0.35)
                    content_ok = await wait_for_content(
                        page, timeout_s=self.RELOAD_CONTENT_TIMEOUT_S
                    )
                runtime = get_runtime_settings()
                if not content_ok and runtime.scraper_challenge_second_cycle_enabled:
                    logger.warning(
                        "Rumble: second settle cycle for potential CF challenge %s",
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
                        timeout_s=max(
                            0.1, min(second_wait, self.SECOND_CYCLE_CONTENT_TIMEOUT_S)
                        ),
                    )
                stage_marks.append(("challenge_resolution", perf_counter() - stage_t0))

                await self.ensure_not_blocked(page, channel_url)
                if not content_ok:
                    raise ScraperBlockedError(f"Rumble page empty after reload: {channel_url}")
                current_html = await page.content()
                if len(current_html) < 1000:
                    raise ScraperBlockedError(
                        f"Rumble page appears unresolved challenge stub: {channel_url} bytes={len(current_html)}"
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
                name = self._extract_name(home_soup, channel_base_url, home_page_title)
                subscriber_count = self._extract_subscribers(home_soup)
                about_task = asyncio.create_task(self._fetch_about_with_retry(context, about_url))

                await guarded_goto(
                    page,
                    videos_url,
                    session_key=session_key,
                    wait_until="domcontentloaded",
                    timeout=self.CHANNEL_NAV_TIMEOUT_MS,
                )
                videos_content_ok = await wait_for_content(
                    page, timeout_s=self.PRIMARY_CONTENT_TIMEOUT_S
                )
                await self.ensure_not_blocked(page, videos_url)
                if not videos_content_ok:
                    raise ScraperBlockedError(f"Rumble videos tab empty after load: {videos_url}")

                try:
                    await page.wait_for_selector(
                        self.VIDEO_CARD_SELECTOR,
                        timeout=self.CARD_SELECTOR_TIMEOUT_MS,
                    )
                except PlaywrightError:
                    logger.warning(
                        "Rumble: video grid did not render before parsing %s",
                        channel_url,
                    )

                video_data_map, soup = await self._collect_videos_with_scroll(page)
                if not video_data_map:
                    logger.warning(
                        "Rumble: no videos parsed from videos-tab selectors for %s",
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

                description, about_socials, about_contact_soup, about_error_reasons = await about_task

                if about_error_reasons:
                    logger.info(
                        "Rumble About fetch diagnostics for %s: %s",
                        channel_url,
                        "; ".join(about_error_reasons),
                    )

                if not description:
                    logger.info(
                        "Rumble About selector did not return description for %s",
                        channel_url,
                    )
                description_fallback_used = self._is_generic_description(description)
                if description_fallback_used:
                    logger.info(
                        "Rumble description is generic fallback text for %s; persisting empty description",
                        channel_url,
                    )
                    description = ""

                all_secondary = sorted(set(about_socials))
                combined_text = f"{description}\n{about_contact_soup.get_text(' ', strip=True)}"
                emails = self._extract_mailto_emails(about_contact_soup)
                emails.extend(extract_emails(combined_text))
                urls = extract_urls(combined_text)
                contact_info = self._filter_contact_info(
                    sorted(set(emails + urls + all_secondary))
                )
                stage_marks.append(("about_and_contact", perf_counter() - stage_t0))

                # Rumble exposes reliable comments only on individual video pages.
                # Visit the latest three videos from the videos tab and average only
                # those page-level counts.
                (
                    comment_pages_attempted,
                    comment_pages_blocked,
                    comment_pages_parsed_success,
                    comment_selectors_hit,
                ) = await self._enrich_latest_video_page_comments(context, video_data_map)
                stage_marks.append(("video_page_comments", perf_counter() - stage_t0))

                video_titles = [
                    str(video["title"])
                    for video in video_data_map.values()
                    if video.get("title")
                ][: self.VIDEO_COLLECTION_LIMIT]
                view_counts = [
                    float(video["views"])
                    for video in video_data_map.values()
                    if video.get("views") is not None
                ][: self.VIDEO_COLLECTION_LIMIT]
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

                avg_views = self.compute_avg(view_counts)
                avg_comments = self.compute_avg(comment_counts)
                if avg_comments is None:
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
                if posts_per_week is None and len(upload_dates) <= 1:
                    posts_per_week = 0.0
                last_active_date = max(upload_dates).date() if upload_dates else None
                is_empty_channel = (
                    not video_titles and self._has_empty_channel_marker(body_text)
                )
                if is_empty_channel:
                    avg_views = 0 if avg_views is None else avg_views
                    avg_comments = 0 if avg_comments is None else avg_comments
                    posts_per_week = 0.0
                logger.info(
                    "Rumble extraction quality for %s: videos=%d views=%d comments=%d dates=%d",
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
                    allow_empty_channel=is_empty_channel,
                )

                channel_data = {
                    "platform": "rumble",
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
                    "is_55_plus": demographic["is_55_plus"],
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

                logger.info("Rumble scrape complete for %s (%s)", name, channel_base_url)
                stage_marks.append(("persist", perf_counter() - stage_t0))
                stage_log = ", ".join(
                    f"{stage}={elapsed:.2f}s" for stage, elapsed in stage_marks
                )
                logger.info("Rumble stage timings for %s: %s", channel_base_url, stage_log)
                total_duration_s = perf_counter() - stage_t0
                logger.info(
                    "SCRAPE_PERF_SUMMARY platform=%s channel=%s duration_s=%.2f "
                    "bytes_est=%d responses=%d videos_considered=%d view_samples=%d "
                    "comment_samples=%d date_samples=%d",
                    "rumble",
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
                    "Rumble transfer estimate for %s: responses=%d bytes_est=%d",
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
                }
                return channel_data

        except (PlaywrightError, ScraperBlockedError, ScraperClassifiedError) as exc:
            logger.error("Rumble scrape failed for %s: %s", channel_url, exc)
            raise

    def _channel_base_url(self, channel_url: str) -> str:
        """Return the canonical Rumble channel surface without tab suffixes."""
        parsed = urlsplit(channel_url.strip())
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or "rumble.com"
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[-1].lower() in {"videos", "about", "shorts", "livestreams", "live"}:
            parts = parts[:-1]
        path = "/" + "/".join(parts) if parts else "/"
        return urljoin(f"{scheme}://{netloc}", path).rstrip("/")

    def _channel_tab_url(self, channel_base_url: str, tab: str) -> str:
        """Build an explicit Rumble channel tab URL."""
        return f"{channel_base_url.rstrip('/')}/{tab.strip('/')}"

    async def _fetch_about_with_retry(
        self, context, about_url: str
    ) -> tuple[str, list[str], BeautifulSoup, list[str]]:
        description = ""
        socials: list[str] = []
        error_reasons: list[str] = []
        about_soup = BeautifulSoup("", "lxml")
        for attempt in range(1, self.ABOUT_FETCH_ATTEMPTS + 1):
            about_page = await context.new_page()
            try:
                response = await guarded_goto(
                    about_page,
                    about_url,
                    session_key=self._session_key or about_url,
                    wait_until="domcontentloaded",
                    timeout=self.ABOUT_NAV_TIMEOUT_MS,
                )
                if response is None:
                    error_reasons.append(f"attempt={attempt}:goto_no_response")
                elif response.status >= 400:
                    error_reasons.append(f"attempt={attempt}:http_{response.status}")
                content_ok = await wait_for_content(
                    about_page, min_bytes=3000, timeout_s=self.ABOUT_CONTENT_TIMEOUT_S
                )
                if not content_ok:
                    error_reasons.append(f"attempt={attempt}:content_timeout")
                    continue
                about_html = await about_page.content()
                if len(about_html) < 1000:
                    error_reasons.append(f"attempt={attempt}:cf_stub")
                    continue
                about_soup = BeautifulSoup(about_html, "lxml")
                attempt_description = self._extract_description(about_soup)
                attempt_socials = self._extract_external_links(about_soup, about_url)
                if not attempt_description:
                    error_reasons.append(f"attempt={attempt}:description_empty")
                if not attempt_socials:
                    error_reasons.append(f"attempt={attempt}:socials_empty")
                if attempt_description:
                    description = attempt_description
                if attempt_socials:
                    socials = attempt_socials
                if description and socials:
                    break
            except Exception as exc:
                error_reasons.append(f"attempt={attempt}:exception:{type(exc).__name__}")
            finally:
                await about_page.close()
        return description, socials, about_soup, error_reasons

    def _extract_name(self, soup: BeautifulSoup, channel_url: str, page_title: str) -> str:
        """Extract channel name from the channel-home header selector."""
        node = soup.select_one(self.CHANNEL_NAME_SELECTOR)
        if node is not None:
            name = node.get_text(" ", strip=True)
            if name:
                return name

        title = re.sub(r"\s*[-|]\s*Rumble\s*$", "", page_title).strip()
        if title:
            return title
        return channel_url.rstrip("/").split("/")[-1]

    def _extract_subscribers(self, soup: BeautifulSoup) -> int | None:
        """Extract follower count from the channel-home follower selector."""
        node = soup.select_one(self.CHANNEL_FOLLOWERS_SELECTOR)
        if node is not None:
            return parse_follower_count(node.get_text(" ", strip=True))
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
                logger.debug("Rumble: Could not follow next page %s: %s", next_page_url, exc)
                break

        return self._trim_video_map(collected), last_soup

    def _extract_next_page_url(self, soup: BeautifulSoup, base_url: str) -> str | None:
        """Extract the next pagination URL from a Rumble channel page."""
        for anchor in soup.select("a[href]"):
            text = anchor.get_text(" ", strip=True).lower()
            rel_values = [str(value).lower() for value in anchor.get("rel", [])]
            if text != "next" and "next" not in rel_values:
                continue
            href = str(anchor.get("href") or "").strip()
            if not href:
                continue
            next_url = urljoin(base_url, href)
            if urlsplit(next_url).netloc.endswith("rumble.com"):
                return next_url
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

        for card in cards:
            if len(video_map) >= self.VIDEO_COLLECTION_LIMIT or not isinstance(card, Tag):
                break
            link = card.select_one(self.VIDEO_LINK_SELECTOR)
            if not isinstance(link, Tag):
                continue
            href = str(link.get("href") or "")
            if not self._is_video_href(href):
                continue
            video_url = urljoin(RUMBLE_BASE_URL, href)
            video_id = urlsplit(video_url).path.rstrip("/").split("/")[-1]
            if not video_id or video_id in video_map:
                continue

            title = self._extract_video_title(card, link)
            views = self._extract_card_views(card)
            comments = self._extract_card_comments(card)
            date_val = self._extract_card_date(card)

            video_map[video_id] = {
                "title": title or "Unknown Title",
                "views": views,
                "comments": comments,
                "date": date_val,
                "url": video_url,
            }
        return video_map

    def _is_video_href(self, href: str) -> bool:
        """Return True for canonical Rumble video links, excluding nav paths."""
        path = urlsplit(urljoin(RUMBLE_BASE_URL, href)).path.rstrip("/")
        return bool(re.search(r"/v[a-z0-9][^/]*\.html$", path, flags=re.I))

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
        if needs_title and title:
            item["title"] = title
        if needs_views and views is not None:
            item["views"] = views
        if needs_comment and comments is not None:
            item["comments"] = comments
        if needs_date and publish_date is not None:
            item["date"] = publish_date

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
    ) -> tuple[int, int, int, set[str]]:
        """Fetch video-page comments for the latest three uploaded videos."""
        attempted = 0
        blocked = 0
        parsed_success = 0
        selectors_hit: set[str] = set()
        for item in self._last_comment_page_items(video_data_map):
            video_url = str(item.get("url") or "").strip()
            if not video_url:
                continue
            views, comments, publish_date, title, comment_hit_selector, blocked_stub = (
                await self._extract_video_page_signals(context, video_url)
            )
            attempted += 1
            if blocked_stub:
                blocked += 1
            if comment_hit_selector:
                selectors_hit.add(comment_hit_selector)
            if comments is not None:
                parsed_success += 1
            self._merge_video_page_signals(
                item=item,
                needs_title=not item.get("title") or item.get("title") == "Unknown Title",
                needs_views=item.get("views") is None,
                needs_comment=item.get("comments") is None,
                needs_date=item.get("date") is None,
                title=title,
                views=views,
                comments=comments,
                publish_date=publish_date,
            )
        return attempted, blocked, parsed_success, selectors_hit

    def _is_generic_description(self, description: str) -> bool:
        text = (description or "").strip()
        if not text:
            return True
        return _DESCRIPTION_BOILERPLATE_RE.match(text) is not None

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
    ) -> tuple[int | None, int | None, datetime | None, str | None, str | None, bool]:
        """Open a Rumble video page and extract missing views, comments, and date."""
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
                    f"Rumble video page unresolved challenge stub: {video_url} bytes={len(html_now)}"
                )
            try:
                await human_scroll(page, direction="down", steps=2)
                await page.wait_for_selector(
                    self.VIDEO_PAGE_COMMENT_SELECTOR,
                    timeout=self.VIDEO_PAGE_COMMENT_TIMEOUT_MS,
                )
            except Exception:
                pass
            html_now = await page.content()

            soup = BeautifulSoup(html_now, "lxml")
            views = self._extract_video_page_views(soup)
            comments, comment_hit_selector = self._extract_video_page_comments(soup)
            publish_date = self._extract_video_page_upload_date(soup)
            title = self._extract_video_page_title(soup)

            return views, comments, publish_date, title, comment_hit_selector, False
        except ScraperBlockedError:
            return None, None, None, None, None, True
        except Exception as exc:
            logger.debug("Rumble: Could not extract video signals from %s: %s", video_url, exc)
            return None, None, None, None, None, False
        finally:
            await page.close()

    def _extract_video_page_views(self, soup: BeautifulSoup) -> int | None:
        node = soup.select_one(self.VIDEO_PAGE_VIEW_SELECTOR)
        if node is not None:
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed
        for fallback in RUMBLE_VIDEO["view_count"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                parsed = parse_count_text(node.get_text(" ", strip=True))
                if parsed is not None:
                    return parsed
        return None

    def _extract_video_page_comments(self, soup: BeautifulSoup) -> tuple[int | None, str | None]:
        node = soup.select_one(self.VIDEO_PAGE_COMMENT_SELECTOR)
        if node is not None:
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed, self.VIDEO_PAGE_COMMENT_SELECTOR
        return None, None

    def _extract_video_page_upload_date(self, soup: BeautifulSoup) -> datetime | None:
        node = soup.select_one(self.VIDEO_PAGE_DATE_SELECTOR)
        if node is not None:
            for candidate in [
                str(node.get("title") or ""),
                node.get_text(" ", strip=True),
            ]:
                parsed = parse_rumble_datetime(candidate)
                if parsed is not None:
                    return parsed
        for fallback in RUMBLE_VIDEO["upload_date"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                for candidate in [
                    str(node.get("datetime") or ""),
                    node.get_text(" ", strip=True),
                ]:
                    parsed = parse_rumble_datetime(candidate)
                    if parsed is not None:
                        return parsed
        return None

    def _extract_video_page_title(self, soup: BeautifulSoup) -> str:
        node = soup.select_one(self.VIDEO_PAGE_TITLE_SELECTOR)
        if node is not None:
            title = node.get_text(" ", strip=True)
            if title:
                return title
        for fallback in RUMBLE_VIDEO["title"]["fallbacks"]:
            node = soup.select_one(fallback)
            if node is not None:
                title = node.get_text(" ", strip=True)
                if title:
                    return title
        return ""

    def _extract_video_title(self, card: Tag, link: Tag) -> str:
        node = card.select_one(self.VIDEO_TITLE_SELECTOR)
        if node is not None:
            text = str(node.get("title") or node.get_text(" ", strip=True)).strip()
            if text:
                return text
        for attr in ["title", "aria-label"]:
            text = str(link.get(attr) or "").strip()
            if text:
                return text
        return link.get_text(" ", strip=True)

    def _extract_card_views(self, card: Tag) -> int | None:
        node = card.select_one(self.VIDEO_VIEWS_SELECTOR)
        if node is not None:
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed
        parent = node.parent if node is not None and isinstance(node.parent, Tag) else None
        if parent is not None:
            for candidate in [str(parent.get("data-views") or ""), str(parent.get("title") or "")]:
                parsed = parse_count_text(candidate)
                if parsed is not None:
                    return parsed
        return None

    def _extract_card_comments(self, card: Tag) -> int | None:
        # Rumble card templates are unreliable for comment counts; enforce
        # video-page extraction for comments via fallback enrichment.
        return None

    def _extract_card_date(self, card: Tag) -> datetime | None:
        for time_node in card.select(self.VIDEO_TIME_SELECTOR):
            for candidate in [
                str(time_node.get("datetime") or ""),
                str((time_node.parent.get("title") if isinstance(time_node.parent, Tag) else "") or ""),
                time_node.get_text(" ", strip=True),
            ]:
                parsed = parse_rumble_datetime(candidate)
                if parsed is not None:
                    return parsed

        text = card.get_text(" ", strip=True)
        match = re.search(
            r"(\d+\s+(?:second|minute|hour|day|week|month|year|sec|min|hr|wk|mo|yr)s?\s+ago|yesterday|just now)",
            text,
            flags=re.I,
        )
        if match:
            return parse_rumble_datetime(match.group(1))
        return None

    def _extract_description(self, soup: BeautifulSoup) -> str:
        node = soup.select_one(self.ABOUT_DESCRIPTION_SELECTOR)
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
            if "rumble.com" not in absolute:
                links.add(absolute)
        return sorted(links)

    def _extract_mailto_emails(self, soup: BeautifulSoup) -> list[str]:
        emails: list[str] = []
        for node in soup.select(RUMBLE_CHANNEL["email_addresses"]["primary"]):
            href = str(node.get("href") or "").strip()
            if href.lower().startswith("mailto:"):
                addr = href.split(":", 1)[1].split("?", 1)[0].strip().lower()
                if addr:
                    emails.append(addr)
        return sorted(set(emails))

    def _has_empty_channel_marker(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        return any(marker in lowered for marker in self._EMPTY_CHANNEL_MARKERS)
