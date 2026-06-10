"""Rumble scraper with resilient channel-card extraction."""

import asyncio
import json
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
from core.cf_bypass import check_for_cf_challenge, human_scroll, wait_for_cf_resolution
from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from core.runtime_settings import get_runtime_settings
from scrapers.base import BaseScraper
from utils.contact_extractor import extract_emails, extract_urls
from utils.keyword_matcher import compute_channel_demographic, compute_comment_tier

logger = logging.getLogger(__name__)

RUMBLE_BASE_URL = "https://rumble.com"

# Domains treated as social-media / direct-contact links.
# URLs on these domains go to contact_info; everything else goes to secondary_urls.
_SOCIAL_DOMAINS = frozenset({
    "twitter.com", "x.com",
    "instagram.com",
    "facebook.com", "fb.com", "m.facebook.com",
    "youtube.com", "youtu.be",
    "tiktok.com",
    "t.me", "telegram.me", "telegram.org",
    "linkedin.com",
    "odysee.com",
    "gab.com", "gab.ai",
    "gettr.com",
    "truthsocial.com",
    "parler.com",
    "reddit.com",
    "discord.gg", "discord.com",
    "twitch.tv",
    "pinterest.com",
    "snapchat.com",
    "rumble.com",
    "locals.com",
    "minds.com",
    "mewe.com",
    "clouthub.com",
})


def _is_social_or_email(value: str) -> bool:
    """Return True for email addresses and social-media profile URLs."""
    stripped = (value or "").strip()
    if not stripped:
        return False
    # Plain email address (no scheme)
    if "@" in stripped and not stripped.startswith("http"):
        return True
    hostname = (urlsplit(stripped).hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname in _SOCIAL_DOMAINS or any(
        hostname.endswith("." + d) for d in _SOCIAL_DOMAINS
    )


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
            "div.media-description-info-stream-time time[datetime]"
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
    "description": {
        # Rumble splits long descriptions into p.media-description--first (always
        # visible) and one or more p.media-description--more (hidden until "Show
        # more" is clicked).  All paragraphs are present in the static HTML, so
        # BeautifulSoup sees the full content without any Playwright interaction.
        # data-js attr is Rumble's own JS hook — more stable than cosmetic CSS class.
        "primary": "[data-js='media_long_description_container']",
        "fallbacks": ["div.media-description"],
        "extract": "children(p.media-description)+a[href]",
        "normalize": "text()+hrefs",
        "js_required": False,
    },
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
        "fallbacks": [
            # Confirmed working 2026-05. #comments, button[data-js], a[href*='#comments']
            # variants were removed — they never match current Rumble DOM.
            "#video-comments h3.comment-count",
        ],
        "extract": "text()",
        "normalize": "parse_count_text()",
        "js_required": False,
    },
    "upload_date": {
        # Rumble removed <time datetime="..."> from video pages (confirmed 2026-05).
        # Date is now rendered as <div title="May 26, 2026">1 day ago</div>.
        # Extraction reads node.get("title") which parse_rumble_datetime handles via %B %d, %Y.
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

    VIDEO_COLLECTION_LIMIT = 3
    COMMENT_VIDEO_PAGE_SAMPLE_LIMIT = 3
    DEMOGRAPHIC_TITLE_LIMIT = 20
    PRIMARY_CONTENT_TIMEOUT_S = 7.0
    RELOAD_CONTENT_TIMEOUT_S = 8.0
    SECOND_CYCLE_CONTENT_TIMEOUT_S = 10.0
    CARD_SELECTOR_TIMEOUT_MS = 500
    ABOUT_NAV_TIMEOUT_MS = 10000
    ABOUT_CONTENT_TIMEOUT_S = 5.0
    ABOUT_FETCH_ATTEMPTS = 2
    VIDEO_PAGE_TIMEOUT_MS = 15000
    VIDEO_PAGE_CONTENT_TIMEOUT_S = 4.0
    VIDEO_PAGE_COMMENT_TIMEOUT_MS = 2000
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
    VIDEO_PAGE_DESC_SELECTOR = RUMBLE_VIDEO["description"]["primary"]
    VIDEO_PAGE_DESC_FALLBACKS = RUMBLE_VIDEO["description"]["fallbacks"]

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
            async with launch_browser(session_key=session_key, telemetry=telemetry, platform="rumble") as context:
                self._proxy_key = telemetry.selected_proxy
                page = await context.new_page()
                if await is_cold_session(context):
                    await pre_warm_homepage(
                        page, RUMBLE_BASE_URL + "/", session_key=session_key, proxy_key=self._proxy_key
                    )
                response = await guarded_goto(
                    page,
                    videos_url,
                    session_key=session_key,
                    proxy_key=self._proxy_key,
                    wait_until="domcontentloaded",
                    timeout=get_runtime_settings().scraper_rumble_nav_timeout_ms,
                )
                stage_marks.append(("goto_domcontentloaded", perf_counter() - stage_t0))
                # With domcontentloaded the full HTML is already parsed, so
                # wait_for_content is effectively instant for real pages.
                # It still catches CF challenge stubs (< 5 KB) that domcontentloaded
                # fires on before any JS challenge resolution runs.
                content_ok = await wait_for_content(
                    page, timeout_s=self.PRIMARY_CONTENT_TIMEOUT_S
                )
                # CF managed challenge pages are > 5 KB (passing the byte check) but
                # block real content behind a JS fingerprint verification that auto-
                # resolves in 2–3 s for browsers that pass. Poll with behavioral
                # signals until the challenge clears or the timeout expires.
                if content_ok and await check_for_cf_challenge(page):
                    logger.info(
                        "Rumble: CF managed challenge on %s — waiting for auto-resolution",
                        channel_url,
                    )
                    content_ok = await wait_for_cf_resolution(page)
                if not content_ok:
                    logger.warning("Rumble: content not ready, reloading %s", channel_url)
                    await page.reload(
                        wait_until="domcontentloaded", timeout=get_runtime_settings().scraper_rumble_nav_timeout_ms
                    )
                    await human_delay(0.15, 0.35)
                    content_ok = await wait_for_content(
                        page, timeout_s=self.RELOAD_CONTENT_TIMEOUT_S
                    )
                    # Re-run the challenge check after reload — a CF managed challenge
                    # page is large enough to pass the byte heuristic, so without this
                    # check the reload path skips the 15 s resolution wait entirely and
                    # fails immediately at ensure_not_blocked.
                    if content_ok and await check_for_cf_challenge(page):
                        logger.info(
                            "Rumble: CF managed challenge after reload on %s — waiting for auto-resolution",
                            channel_url,
                        )
                        content_ok = await wait_for_cf_resolution(page)
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
                        wait_until="domcontentloaded", timeout=get_runtime_settings().scraper_rumble_nav_timeout_ms
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
                response_status = response.status if response is not None else None

                # Start about page fetch in parallel while we wait for video cards.
                about_task = asyncio.create_task(self._fetch_about_with_retry(context, about_url))

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

                html = await page.content()
                soup = BeautifulSoup(html, "lxml")
                page_title = await page.title() or ""
                body_text = soup.get_text(" ", strip=True).lower()
                self.classify_terminal_page_state(
                    channel_url=channel_base_url,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=response_status,
                )
                name = self._extract_name(soup, channel_base_url, page_title)
                subscriber_count = self._extract_subscribers(soup)
                video_data_map = self._extract_videos(soup)
                if not video_data_map:
                    logger.warning(
                        "Rumble: no videos parsed from videos-tab selectors for %s",
                        videos_url,
                    )
                stage_marks.append(("fast_path_card_parse", perf_counter() - stage_t0))

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
                    video_desc_social,
                    video_desc_secondary,
                ) = await self._enrich_latest_video_page_comments(context, video_data_map)
                # Social media URLs and emails → contact_info
                if video_desc_social:
                    new_social = set(video_desc_social) - set(contact_info)
                    contact_info = self._filter_contact_info(
                        sorted(set(contact_info) | set(video_desc_social))
                    )
                    logger.info(
                        "Rumble video desc social contacts for %s: %d new (total contact_info=%d)",
                        channel_base_url, len(new_social), len(contact_info),
                    )
                # Affiliate/general URLs → secondary_urls
                if video_desc_secondary:
                    new_secondary = set(video_desc_secondary) - set(all_secondary)
                    all_secondary = sorted(set(all_secondary) | set(video_desc_secondary))
                    logger.info(
                        "Rumble video desc secondary links for %s: %d new (total secondary_urls=%d)",
                        channel_base_url, len(new_secondary), len(all_secondary),
                    )
                stage_marks.append(("video_page_comments", perf_counter() - stage_t0))

                video_titles = [
                    str(video["title"])
                    for video in video_data_map.values()
                    if video.get("title")
                ]
                view_counts = [
                    float(video["views"])
                    for video in video_data_map.values()
                    if video.get("views") is not None
                ]
                comment_counts = [
                    float(video["comments"])
                    for video in video_data_map.values()
                    if video.get("comments") is not None
                ]
                upload_dates = [
                    video["date"]
                    for video in video_data_map.values()
                    if isinstance(video.get("date"), datetime)
                ]

                # Mean of up to 3 card view samples, rounded to nearest integer.
                avg_views = round(sum(view_counts) / len(view_counts)) if view_counts else None
                # Mean of up to 3 video-page comment samples; 0s included, Nones excluded.
                avg_comments = round(sum(comment_counts) / len(comment_counts)) if comment_counts else None
                if avg_comments is None:
                    if comment_pages_attempted > 0 and comment_pages_attempted == comment_pages_blocked:
                        raise ScraperClassifiedError(
                            "parse_missing_avg_comments_cf_blocked",
                            f"No comment counts extracted from latest video pages for {channel_base_url}",
                            terminal=False,
                            retryable=True,
                        )
                    # Selector/layout miss: treat as zero-comments signal instead of
                    # retrying indefinitely when pages load but expose no parseable counts.
                    avg_comments = 0
                    logger.warning(
                        "Rumble comments unavailable from video pages for %s; defaulting avg_comments=0 "
                        "(attempted=%d blocked=%d parsed_success=%d selectors=%s)",
                        channel_base_url,
                        comment_pages_attempted,
                        comment_pages_blocked,
                        comment_pages_parsed_success,
                        sorted(comment_selectors_hit),
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
                    allow_empty_channel=False,
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
                    "recent_videos": [
                        {
                            "title": str(video.get("title") or "Unknown Title"),
                            "views": video.get("views"),
                            "comments": video.get("comments"),
                            "published_at": (
                                video["date"].isoformat()
                                if isinstance(video.get("date"), datetime)
                                else None
                            ),
                            "url": video.get("url"),
                        }
                        for video in video_data_map.values()
                    ],
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
            try:
                about_page = await context.new_page()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_reasons.append(f"attempt={attempt}:new_page:{type(exc).__name__}")
                break
            try:
                response = await guarded_goto(
                    about_page,
                    about_url,
                    session_key=self._session_key or about_url,
                    proxy_key=self._proxy_key,
                    wait_until="commit",
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
                if description:
                    break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_reasons.append(f"attempt={attempt}:exception:{type(exc).__name__}")
            finally:
                try:
                    await about_page.close()
                except Exception:
                    pass
        return description, socials, about_soup, error_reasons

    def _extract_name(self, soup: BeautifulSoup, channel_url: str, page_title: str) -> str:
        """Extract channel name — JSON by.name first, DOM fallback, then page title."""
        _, _, channel_name = self._parse_video_json_items(soup)
        if channel_name:
            return channel_name
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
        """Extract follower count — JSON by.followers first, DOM fallback."""
        _, followers, _ = self._parse_video_json_items(soup)
        if followers is not None:
            return followers
        node = soup.select_one(self.CHANNEL_FOLLOWERS_SELECTOR)
        if node is not None:
            return parse_follower_count(node.get_text(" ", strip=True))
        return None

    def _parse_video_json_items(
        self, soup: BeautifulSoup
    ) -> tuple[list[dict], int | None, str | None]:
        """Parse Rumble's inline JSON script tag (current page format).

        Returns (video_items, channel_followers, channel_name).
        video_items contains only items where object_type == "video".
        channel_followers and channel_name are taken from the first video's
        by field and may be None if the JSON is absent or malformed.
        """
        for script in soup.find_all("script"):
            text = script.string or ""
            if '"object_type"' not in text:
                continue
            try:
                data = json.loads(text)
            except (ValueError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            items = data.get("items")
            if not isinstance(items, list):
                continue
            followers: int | None = None
            channel_name: str | None = None
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("by"), dict):
                    by = item["by"]
                    raw = by.get("followers")
                    if isinstance(raw, (int, float)):
                        followers = int(raw)
                    name = str(by.get("name") or "").strip()
                    if name:
                        channel_name = name
                    break
            video_items = [
                item for item in items
                if isinstance(item, dict) and item.get("object_type") == "video"
            ]
            return video_items, followers, channel_name
        return [], None, None

    def _extract_videos(self, soup: BeautifulSoup) -> dict[str, dict[str, object]]:
        """Extract recent videos — JSON script tag first, legacy DOM selectors as fallback."""
        video_map: dict[str, dict[str, object]] = {}

        # Current Rumble format: video grid data is embedded as inline JSON.
        json_items, _, _ = self._parse_video_json_items(soup)
        for item in json_items:
            if len(video_map) >= self.VIDEO_COLLECTION_LIMIT:
                break
            video_url = str(item.get("url") or "").strip()
            if not video_url or not self._is_video_href(video_url):
                continue
            video_id = urlsplit(video_url).path.rstrip("/").split("/")[-1]
            if not video_id or video_id in video_map:
                continue
            title = str(item.get("title") or "").strip() or "Unknown Title"
            views_raw = item.get("views")
            views = int(views_raw) if isinstance(views_raw, (int, float)) else None
            comments_data = item.get("comments")
            comments_raw = comments_data.get("count") if isinstance(comments_data, dict) else None
            comments = int(comments_raw) if isinstance(comments_raw, (int, float)) else None
            upload_date_str = str(item.get("upload_date") or "").strip()
            date_val = parse_rumble_datetime(upload_date_str) if upload_date_str else None
            video_map[video_id] = {
                "title": title,
                "views": views,
                "comments": comments,
                "date": date_val,
                "url": video_url,
            }
        if video_map:
            return video_map

        # Legacy DOM fallback for older Rumble page layouts.
        cards = soup.select(self.VIDEO_CARD_SELECTOR)
        for card in cards:
            if len(video_map) >= self.VIDEO_COLLECTION_LIMIT or not isinstance(card, Tag):
                break
            if "videostream--featured" in (card.get("class") or []):
                continue
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

    async def _enrich_latest_video_page_comments(
        self,
        context,
        video_data_map: dict[str, dict[str, object]],
    ) -> tuple[int, int, int, set[str], list[str]]:
        """Fetch video-page signals for all collected videos in parallel.

        Tasks are staggered so they don't all navigate simultaneously —
        simultaneous requests from the same proxy IP to multiple video pages
        are a primary Cloudflare bot-detection trigger.  Each subsequent task
        waits 5–12 s before opening its tab, keeping the overlap benefit while
        spreading the CF-visible request pattern.

        Returns:
            (attempted, blocked, parsed_success, selectors_hit, video_desc_contacts)
            video_desc_contacts is the deduplicated union of all contact URLs and
            email addresses found across all visited video page descriptions.
        """
        work = [
            (item, str(item.get("url") or "").strip())
            for item in video_data_map.values()
        ]
        work = [(item, url) for item, url in work if url]
        if not work:
            return 0, 0, 0, set(), [], []

        results = await asyncio.gather(
            *[
                self._extract_video_page_signals(
                    context, url, stagger_s=i * 0.1
                )
                for i, (_, url) in enumerate(work)
            ],
            return_exceptions=True,
        )

        attempted = len(work)
        blocked = 0
        parsed_success = 0
        selectors_hit: set[str] = set()
        all_desc_social: set[str] = set()
        all_desc_secondary: set[str] = set()
        for (item, _), result in zip(work, results):
            if isinstance(result, Exception):
                continue
            views, comments, publish_date, title, comment_hit_selector, desc_social, desc_secondary, blocked_stub = result
            if blocked_stub:
                blocked += 1
            if comment_hit_selector:
                selectors_hit.add(comment_hit_selector)
            if comments is not None:
                parsed_success += 1
            all_desc_social.update(desc_social)
            all_desc_secondary.update(desc_secondary)
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
        return attempted, blocked, parsed_success, selectors_hit, sorted(all_desc_social), sorted(all_desc_secondary)

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
        self, context, video_url: str, *, stagger_s: float = 0.0
    ) -> tuple[int | None, int | None, datetime | None, str | None, str | None, list[str], list[str], bool]:
        """Open a Rumble video page and extract views, comments, date, title, and description links.

        Returns:
            (views, comments, publish_date, title, comment_hit_selector,
             desc_social, desc_secondary, blocked_stub)
            desc_social   — emails and social-media URLs from description (→ contact_info)
            desc_secondary — affiliate and general website URLs (→ secondary_urls)
        """
        if stagger_s > 0:
            await asyncio.sleep(stagger_s)
        page = await context.new_page()
        try:
            await guarded_goto(
                page,
                video_url,
                session_key=self._session_key or video_url,
                proxy_key=self._proxy_key,
                wait_until="commit",
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
            _, desc_social, desc_secondary = self._extract_video_page_description(soup)

            return views, comments, publish_date, title, comment_hit_selector, desc_social, desc_secondary, False
        except ScraperBlockedError:
            return None, None, None, None, None, [], [], True
        except Exception as exc:
            logger.debug("Rumble: Could not extract video signals from %s: %s", video_url, exc)
            return None, None, None, None, None, [], [], False
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
        # Primary: server-rendered comment count heading — present even for 0-comment videos.
        # Text is "0 Comments" / "42 Comments" etc.; parse_count_text strips the word.
        node = soup.select_one(self.VIDEO_PAGE_COMMENT_SELECTOR)
        if node is not None:
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed, self.VIDEO_PAGE_COMMENT_SELECTOR
        for selector in RUMBLE_VIDEO["comment_count"]["fallbacks"]:
            node = soup.select_one(selector)
            if node is None:
                continue
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed, selector
        # Body-text fallbacks: Rumble shows these phrases when the comments section
        # is empty and the h3.comment-count element failed to render or was missed.
        lowered = soup.get_text(" ", strip=True).lower()
        if (
            "be the first to comment" in lowered
            or "no comments yet" in lowered
            or "0 comments" in lowered
        ):
            return 0, "comments-empty-marker"
        return None, None

    def _extract_video_page_upload_date(self, soup: BeautifulSoup) -> datetime | None:
        node = soup.select_one(self.VIDEO_PAGE_DATE_SELECTOR)
        if node is not None:
            for candidate in [
                str(node.get("datetime") or ""),
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

    def _extract_video_page_description(
        self, soup: BeautifulSoup
    ) -> tuple[str, list[str], list[str]]:
        """Extract video page description text and split links by type.

        Rumble splits long descriptions into a visible first paragraph
        (``p.media-description--first``) and hidden paragraphs
        (``p.media-description--more``) toggled by a "Show more" button.
        All paragraphs are present in the static HTML.

        Returns:
            (description_text, social_contacts, secondary_links)
            social_contacts — emails and social-media profile URLs (→ contact_info)
            secondary_links — affiliate links and general website URLs (→ secondary_urls)
        """
        container = soup.select_one(self.VIDEO_PAGE_DESC_SELECTOR)
        if container is None:
            for fallback in self.VIDEO_PAGE_DESC_FALLBACKS:
                container = soup.select_one(fallback)
                if container is not None:
                    break
        if container is None:
            return "", [], []

        paragraphs = container.select("p.media-description")
        text = (
            " ".join(p.get_text(" ", strip=True) for p in paragraphs)
            if paragraphs
            else container.get_text(" ", strip=True)
        )
        if not text:
            return "", [], []

        raw: set[str] = set()

        # 1. Direct <a href> — catches shortened/affiliate URLs whose link text
        #    differs from the href (e.g. "Click here" → bit.ly/xyz).
        for anchor in container.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            if not href:
                continue
            if href.lower().startswith("mailto:"):
                addr = href.split(":", 1)[1].split("?", 1)[0].strip().lower()
                if addr:
                    raw.add(addr)
                continue
            if href.startswith(("#", "javascript:", "tel:")):
                continue
            host = (urlsplit(href).hostname or "").lower()
            if host == "rumble.com" or host.endswith(".rumble.com"):
                continue
            raw.add(href)

        # 2. Regex over plain text — catches bare domains and emails not in <a>.
        raw.update(extract_emails(text))
        raw.update(extract_urls(text))

        filtered = self._filter_contact_info(sorted(raw))
        social: list[str] = []
        secondary: list[str] = []
        for item in filtered:
            if _is_social_or_email(item):
                social.append(item)
            else:
                secondary.append(item)
        return text, social, secondary

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
        if node is None:
            return None
        # Prefer the exact integer on the parent container over parsing the
        # abbreviated display text (e.g. data-views="11700" vs span text "11.7K").
        parent = node.parent if isinstance(node.parent, Tag) else None
        if parent is not None:
            for candidate in [str(parent.get("data-views") or ""), str(parent.get("title") or "")]:
                parsed = parse_count_text(candidate)
                if parsed is not None:
                    return parsed
        # Fall back to parsing the visible span text ("11.7K", "1.2M", etc.)
        return parse_count_text(node.get_text(" ", strip=True))

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
