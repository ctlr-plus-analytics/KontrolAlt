"""Substack scraper with resilient publication and post extraction."""

import logging
import json
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from time import perf_counter
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from bs4.element import Tag
from playwright.async_api import Error as PlaywrightError

from core.browser import BrowserTelemetry, guarded_goto, human_delay, launch_browser, wait_for_content
from core.cf_bypass import human_scroll, inter_request_jitter
from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from core.runtime_settings import get_runtime_settings
from scrapers.base import BaseScraper
from utils.contact_extractor import extract_emails, extract_urls
from utils.keyword_matcher import compute_channel_demographic, compute_comment_tier

logger = logging.getLogger(__name__)

SUBSTACK_BASE_URL = "https://substack.com"
_SUBSTACK_HANDLE_PATH_RE = re.compile(r"^/@[a-zA-Z0-9._-]+$")
_EXCLUDED_CONTACT_DOMAINS = {
    "substack.com",
    "www.substack.com",
    "enable-javascript.com",
    "www.enable-javascript.com",
}

# Selector constants — verified against live HTML dumps
SEL_POST_CARD = "div[role='article'][aria-label*='Post preview']"
SEL_POST_TITLE = "a[data-testid='post-preview-title']"
SEL_POST_DATE = "time[datetime]"
SEL_POST_LIKES = ".like-button-container .label"
SEL_POST_COMMENTS = ".post-ufi-comment-button .label"
SEL_CHANNEL_NAME = "h1.publication-name"
SEL_CHANNEL_BIO = "meta[name='description']"
SEL_SUBSCRIBER_COUNT = "a[href$='/subscribers']"

SUBSTACK_CHANNEL = {
    "channel_name": {
        "primary": "h1.publication-name, h1[data-testid='publication-name']",
        "fallbacks": [
            "span.line-height-24-jnGwiv.font-themed-headings-BmE7Hr.size-20-P_cSRT.weight-bold-DmI9lw",
            "h1.publication-name",
            "h1[data-testid='publication-name']",
            "meta[property='og:site_name']",
            "meta[property='og:title']",
        ],
    },
    "channel_description": {
        "primary": "meta[name='description']",
        "fallbacks": [
            "div.line-height-20-t4M0El.font-themed-body-bDmALd.size-15-Psle70.weight-regular-mUq6Gb span",
            "meta[name='description']",
            "meta[property='og:description']",
            "div[data-testid='publication-description']",
        ],
    },
    "subscriber_count": {
        "primary": "a[href$='/subscribers']",
        "fallbacks": [
            "[data-testid='subscriber-count']",
            "[class*='subscriber']",
            "script[type='application/ld+json']",
            "script#__NEXT_DATA__",
        ],
    },
    "post_card": {
        "primary": (
            "div.reader2-post-container, "
            "a.reader2-inbox-post, "
            "div[role='article'][aria-label*='Post preview'], "
            "article, "
            "[data-testid='post-preview']"
        ),
        "fallbacks": [],
    },
    "post_link": {
        "primary": (
            "a.reader2-inbox-post[href*='/p/'], "
            "a[data-testid='post-preview-title'][href*='/p/'], "
            "a[href*='/p/']"
        ),
        "fallbacks": [],
    },
    "post_title": {
        "primary": "a[data-testid='post-preview-title']",
        "fallbacks": [],
    },
    "post_views": {
        "primary": "div.line-height-20-t4M0El.font-text-qe4AeH.size-13-hZTUKr.weight-regular-mUq6Gb",
        "fallbacks": [],
    },
    "post_comments": {
        "primary": "div.line-height-20-t4M0El.font-text-qe4AeH.size-13-hZTUKr.weight-regular-mUq6Gb",
        "fallbacks": [],
    },
    "post_date": {
        "primary": "div.meta-EgzBVA.inbox-item-timestamp, time[datetime], time.date-rtYe1v",
        "fallbacks": [],
    },
    "external_links": {
        "primary": "button[data-href]",
        "fallbacks": [],
    },
    "email_addresses": {
        "primary": "a[href^='mailto:']",
        "fallbacks": [],
    },
}

SUBSTACK_POST = {
    "title": {
        "primary": "h1",
        "fallbacks": ["meta[property='og:title']"],
    },
    "views": {
        "primary": "[data-testid='view-count'], [class*='view']",
        "fallbacks": ["script[type='application/ld+json']"],
    },
    "comments": {
        "primary": "button[aria-label='Comment'], [data-testid='comment-count'], [class*='comment']",
        "fallbacks": ["script[type='application/ld+json']"],
    },
    "date": {
        "primary": "time[datetime], meta[property='article:published_time']",
        "fallbacks": ["script[type='application/ld+json']"],
    },
}


def parse_count_text(text: str) -> int | None:
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


def parse_substack_datetime(text: str) -> datetime | None:
    if not text:
        return None
    value = text.strip()
    now = datetime.now()
    try:
        parsed = datetime.fromisoformat(re.sub(r"Z$", "+00:00", value))
        return parsed.replace(tzinfo=None)
    except (ValueError, TypeError):
        pass
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError):
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    for fmt in ("%B %d", "%b %d"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(year=now.year)
        except ValueError:
            continue
    lowered = value.lower()
    if "yesterday" in lowered:
        return now - timedelta(days=1)
    if "just now" in lowered:
        return now
    match = re.search(
        r"(\d+)\s+(second|minute|hour|day|week|month|year|sec|min|hr|wk|mo|yr)s?\s+ago",
        lowered,
    )
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit in {"second", "sec"}:
        return now - timedelta(seconds=amount)
    if unit in {"minute", "min"}:
        return now - timedelta(minutes=amount)
    if unit in {"hour", "hr"}:
        return now - timedelta(hours=amount)
    if unit == "day":
        return now - timedelta(days=amount)
    if unit in {"week", "wk"}:
        return now - timedelta(weeks=amount)
    if unit in {"month", "mo"}:
        return now - timedelta(days=amount * 30)
    if unit in {"year", "yr"}:
        return now - timedelta(days=amount * 365)
    return None


class SubstackScraper(BaseScraper):
    """Scraper for Substack publications."""

    POST_COLLECTION_LIMIT = 50
    COMMENT_POST_PAGE_SAMPLE_LIMIT = 3
    DEMOGRAPHIC_TITLE_LIMIT = 20
    CHANNEL_NAV_TIMEOUT_MS = 45000
    PRIMARY_CONTENT_TIMEOUT_S = 14.0
    RELOAD_CONTENT_TIMEOUT_S = 12.0
    SECOND_CYCLE_CONTENT_TIMEOUT_S = 16.0
    CARD_SELECTOR_TIMEOUT_MS = 9000
    POST_PAGE_TIMEOUT_MS = 30000
    POST_PAGE_CONTENT_TIMEOUT_S = 10.0
    POST_PAGE_COMMENT_TIMEOUT_MS = 8000

    POST_CARD_SELECTOR = SEL_POST_CARD
    POST_LINK_SELECTOR = SEL_POST_TITLE
    POST_TITLE_SELECTOR = SEL_POST_TITLE
    POST_DATE_SELECTOR = SEL_POST_DATE
    POST_VIEWS_SELECTOR = SUBSTACK_CHANNEL["post_views"]["primary"]
    POST_COMMENTS_SELECTOR = SUBSTACK_CHANNEL["post_comments"]["primary"]

    async def scrape(self, channel_url: str) -> dict[str, object]:
        try:
            stage_t0 = perf_counter()
            telemetry = BrowserTelemetry()
            stage_marks: list[tuple[str, float]] = []
            channel_base_url = self._channel_base_url(channel_url)
            publication_url = self._publication_url(channel_base_url)
            profile_url = self._profile_url(channel_base_url)
            session_key = self._session_key or channel_base_url

            async with launch_browser(session_key=session_key, telemetry=telemetry) as context:
                page = await context.new_page()
                # FIX A: Navigate to the publication subdomain page (posts render here)
                response = await guarded_goto(
                    page,
                    publication_url,
                    session_key=session_key,
                    wait_until="domcontentloaded",
                    timeout=self.CHANNEL_NAV_TIMEOUT_MS,
                )
                stage_marks.append(("goto_domcontentloaded", perf_counter() - stage_t0))

                content_ok = await wait_for_content(page, timeout_s=self.PRIMARY_CONTENT_TIMEOUT_S)
                if not content_ok:
                    await page.reload(wait_until="domcontentloaded", timeout=self.CHANNEL_NAV_TIMEOUT_MS)
                    await human_delay(0.15, 0.35)
                    content_ok = await wait_for_content(page, timeout_s=self.RELOAD_CONTENT_TIMEOUT_S)

                runtime = get_runtime_settings()
                if not content_ok and runtime.scraper_challenge_second_cycle_enabled:
                    await human_delay(
                        runtime.scraper_challenge_second_cycle_pre_reload_delay_seconds * 0.75,
                        runtime.scraper_challenge_second_cycle_pre_reload_delay_seconds * 1.35,
                    )
                    await page.reload(wait_until="domcontentloaded", timeout=self.CHANNEL_NAV_TIMEOUT_MS)
                    await human_delay(
                        runtime.scraper_challenge_second_cycle_post_reload_delay_seconds * 0.75,
                        runtime.scraper_challenge_second_cycle_post_reload_delay_seconds * 1.35,
                    )
                    content_ok = await wait_for_content(
                        page,
                        timeout_s=max(
                            0.1,
                            min(
                                runtime.scraper_challenge_second_cycle_wait_timeout_seconds,
                                self.SECOND_CYCLE_CONTENT_TIMEOUT_S,
                            ),
                        ),
                    )
                stage_marks.append(("challenge_resolution", perf_counter() - stage_t0))

                await self.ensure_not_blocked(page, channel_base_url)
                if not content_ok:
                    raise ScraperBlockedError(f"Substack page empty after reload: {channel_base_url}")

                html = await page.content()
                if len(html) < 1000:
                    raise ScraperBlockedError(
                        f"Substack page appears unresolved challenge stub: {channel_base_url} bytes={len(html)}"
                    )
                soup = BeautifulSoup(html, "lxml")
                page_title = await page.title() or ""
                body_text = soup.get_text(" ", strip=True).lower()
                response_status = response.status if response is not None else None
                self.classify_terminal_page_state(
                    channel_url=channel_base_url,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=response_status,
                )

                name = self._extract_name(soup, channel_base_url, page_title)
                description = self._extract_description(soup)

                # FIX A: Wait for post cards using the single confirmed selector
                try:
                    await page.wait_for_selector(SEL_POST_CARD, timeout=self.CARD_SELECTOR_TIMEOUT_MS)
                except PlaywrightError:
                    logger.warning("Substack: post card selector not found for %s", publication_url)

                # FIX B: Parse exactly 3 cards from the rendered page (no scroll loop)
                html = await page.content()
                soup = BeautifulSoup(html, "lxml")
                post_data_map = self._extract_posts(soup, page.url)
                if not post_data_map:
                    logger.info("Substack: post cards empty, waiting for JS render %s", publication_url)
                    await human_delay(1.2, 2.2)
                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")
                    post_data_map = self._extract_posts(soup, page.url)
                stage_marks.append(("fast_path_card_parse", perf_counter() - stage_t0))

                comment_attempted, comment_blocked, comment_success = await self._enrich_latest_post_page_metrics(
                    context, post_data_map
                )
                stage_marks.append(("post_page_enrichment", perf_counter() - stage_t0))

                # FIX D: Subscriber count is only present on the profile page, not the publication page
                subscriber_count = await self._fetch_subscriber_count(context, profile_url, session_key)
                stage_marks.append(("profile_page_subscriber", perf_counter() - stage_t0))

                secondary_urls = self._extract_external_links(soup, channel_base_url)
                combined_text = f"{description}\n{soup.get_text(' ', strip=True)}"
                emails = self._extract_mailto_emails(soup)
                emails.extend(extract_emails(combined_text))
                urls = extract_urls(combined_text)
                contact_info = self._filter_contact_info(sorted(set(emails + urls + secondary_urls)))

                post_titles = [
                    str(item["title"]) for item in post_data_map.values() if item.get("title")
                ][: self.POST_COLLECTION_LIMIT]
                view_counts = [
                    float(item["views"]) for item in post_data_map.values() if item.get("views") is not None
                ][: self.POST_COLLECTION_LIMIT]
                comment_counts = [
                    float(item["comments"]) for item in post_data_map.values() if item.get("comments") is not None
                ][: self.POST_COLLECTION_LIMIT]
                upload_dates = [
                    item["date"] for item in post_data_map.values() if isinstance(item.get("date"), datetime)
                ][: self.POST_COLLECTION_LIMIT]

                avg_views = self.compute_avg(view_counts)
                avg_comments = self.compute_avg(comment_counts)
                posts_per_week = self.compute_posting_cadence(upload_dates)
                last_active_date = max(upload_dates) if upload_dates else None
                comment_tier = compute_comment_tier(avg_comments)
                demographic = compute_channel_demographic(name, description, post_titles[: self.DEMOGRAPHIC_TITLE_LIMIT])

                self.require_scrape_quality(
                    channel_url=channel_base_url,
                    video_titles=post_titles,
                    subscriber_count=subscriber_count,
                    avg_views=avg_views,
                    avg_comments=avg_comments,
                    posts_per_week=posts_per_week,
                    last_active_date=last_active_date,
                    contact_info=contact_info,
                    secondary_urls=secondary_urls,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=response_status,
                    allow_empty_channel=False,
                )

                channel_data = {
                    "platform": "substack",
                    "channel_url": channel_base_url,
                    "name": name,
                    "description": description,
                    "subscriber_count": subscriber_count,
                    "avg_views": avg_views,
                    "avg_comments": avg_comments,
                    "comment_tier": comment_tier,
                    "posts_per_week": posts_per_week,
                    "last_active_date": last_active_date.isoformat() if last_active_date else None,
                    "contact_info": contact_info,
                    "niche_tags": demographic["niche_tags"],
                    "video_titles": post_titles,
                    "secondary_urls": secondary_urls,
                }

                channel_id = await self.save_to_supabase(channel_data)
                if channel_id:
                    await self.log_scrape_attempt(channel_id, "success")

                stage_marks.append(("persist", perf_counter() - stage_t0))
                logger.info("Substack stage timings for %s: %s", channel_base_url, ", ".join(
                    f"{stage}={elapsed:.2f}s" for stage, elapsed in stage_marks
                ))
                channel_data["_scrape_metrics"] = {
                    "bytes_est": telemetry.total_bytes_est,
                    "responses": telemetry.response_count,
                    "geoip_enabled": telemetry.geoip_enabled,
                    "comment_pages_attempted": comment_attempted,
                    "comment_pages_blocked": comment_blocked,
                    "comment_pages_parsed_success": comment_success,
                }
                return channel_data

        except (PlaywrightError, ScraperBlockedError, ScraperClassifiedError) as exc:
            logger.error("Substack scrape failed for %s: %s", channel_url, exc)
            raise

    def _channel_base_url(self, channel_url: str) -> str:
        parsed = urlsplit(channel_url.strip())
        scheme = parsed.scheme or "https"
        host = parsed.netloc or "substack.com"
        if host.lower() in {"www.substack.com", "substack.com"}:
            host = "substack.com"
        parts = [p for p in parsed.path.split("/") if p]
        if not parts or not parts[0].startswith("@"):
            raise ScraperClassifiedError(
                "unsupported_substack_url_shape",
                f"Unsupported Substack URL shape: {channel_url}",
                terminal=True,
                retryable=False,
            )
        handle = parts[0]
        path = f"/{handle}/posts"
        canonical = urlunsplit((scheme, host, path, "", ""))
        if not _SUBSTACK_HANDLE_PATH_RE.match(f"/{handle}"):
            raise ScraperClassifiedError(
                "unsupported_substack_url_shape",
                f"Unsupported Substack URL shape: {channel_url}",
                terminal=True,
                retryable=False,
            )
        return canonical.rstrip("/")

    def _publication_url(self, channel_base_url: str) -> str:
        """Build the publication subdomain URL where post cards render."""
        # channel_base_url = "https://substack.com/@handle/posts"
        handle = urlsplit(channel_base_url).path.strip("/").split("/")[0].lstrip("@")
        return f"https://{handle}.substack.com/"

    def _profile_url(self, channel_base_url: str) -> str:
        """Build the profile page URL where subscriber count is present."""
        # channel_base_url = "https://substack.com/@handle/posts"
        handle_part = urlsplit(channel_base_url).path.strip("/").split("/")[0]  # "@handle"
        return f"https://substack.com/{handle_part}"

    async def _fetch_subscriber_count(self, context, profile_url: str, session_key: str) -> int | None:
        """Navigate to the profile page and extract subscriber count."""
        page = await context.new_page()
        try:
            await inter_request_jitter()
            await guarded_goto(
                page,
                profile_url,
                session_key=session_key,
                wait_until="domcontentloaded",
                timeout=self.CHANNEL_NAV_TIMEOUT_MS,
            )
            await wait_for_content(page, timeout_s=8.0)
            html = await page.content()
            profile_soup = BeautifulSoup(html, "lxml")
            return self._extract_subscribers(profile_soup)
        except Exception as exc:
            logger.warning(
                "Substack: profile page fetch failed, subscriber_count will be None for %s: %s",
                profile_url,
                exc,
            )
            return None
        finally:
            await page.close()

    async def _collect_posts(self, page) -> tuple[dict[str, dict[str, object]], BeautifulSoup]:
        collected: dict[str, dict[str, object]] = {}
        last_soup = BeautifulSoup(await page.content(), "lxml")

        for _ in range(7):
            html = await page.content()
            soup = BeautifulSoup(html, "lxml")
            last_soup = soup
            parsed = self._extract_posts(soup, page.url)
            for post_id, payload in parsed.items():
                if post_id not in collected:
                    collected[post_id] = payload
            if len(collected) >= self.POST_COLLECTION_LIMIT:
                break
            prev_count = len(collected)
            await human_scroll(page, direction="down", steps=4)
            try:
                await page.wait_for_function(
                    "(selector, prev) => document.querySelectorAll(selector).length > prev",
                    self.POST_CARD_SELECTOR,
                    prev_count,
                    timeout=2500,
                )
            except Exception:
                await human_delay(0.05, 0.2)

        return self._trim_post_map(collected), last_soup

    def _extract_posts(self, soup: BeautifulSoup, base_url: str) -> dict[str, dict[str, object]]:
        post_map: dict[str, dict[str, object]] = {}
        for card in soup.select(SEL_POST_CARD):
            if len(post_map) >= 3 or not isinstance(card, Tag):  # FIX B: exactly 3 cards
                break
            # FIX B: title link is the confirmed source for both href and title text
            link = card.select_one(SEL_POST_TITLE)
            if not isinstance(link, Tag):
                continue
            href = str(link.get("href") or "").strip()
            if "/p/" not in href:
                continue
            post_url = urljoin(base_url, href)
            post_id = urlsplit(post_url).path.rstrip("/")
            if not post_id or post_id in post_map:
                continue
            title = self._extract_post_title(card, link)
            views = self._extract_post_card_views(card)
            comments = self._extract_post_card_comments(card)
            publish_date = self._extract_post_card_date(card)
            post_map[post_id] = {
                "title": title or "Unknown Title",
                "views": views,
                "comments": comments,
                "date": publish_date,
                "url": post_url,
            }
        return post_map

    def _trim_post_map(self, post_map: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
        if len(post_map) <= self.POST_COLLECTION_LIMIT:
            return post_map
        trimmed: dict[str, dict[str, object]] = {}
        for idx, (post_id, payload) in enumerate(post_map.items()):
            if idx >= self.POST_COLLECTION_LIMIT:
                break
            trimmed[post_id] = payload
        return trimmed

    async def _enrich_latest_post_page_metrics(
        self, context, post_data_map: dict[str, dict[str, object]]
    ) -> tuple[int, int, int]:
        attempted = 0
        blocked = 0
        parsed_success = 0
        for item in list(post_data_map.values())[: self.COMMENT_POST_PAGE_SAMPLE_LIMIT]:
            post_url = str(item.get("url") or "").strip()
            if not post_url:
                continue
            attempted += 1
            views, comments, publish_date, title, blocked_stub = await self._extract_post_page_signals(context, post_url)
            if blocked_stub:
                blocked += 1
            if comments is not None:
                parsed_success += 1
            if (not item.get("title") or item.get("title") == "Unknown Title") and title:
                item["title"] = title
            if item.get("views") is None and views is not None:
                item["views"] = views
            if item.get("comments") is None and comments is not None:
                item["comments"] = comments
            if item.get("date") is None and publish_date is not None:
                item["date"] = publish_date
        return attempted, blocked, parsed_success

    async def _extract_post_page_signals(
        self, context, post_url: str
    ) -> tuple[int | None, int | None, datetime | None, str | None, bool]:
        page = await context.new_page()
        try:
            await inter_request_jitter()
            await guarded_goto(
                page,
                post_url,
                session_key=self._session_key or post_url,
                wait_until="domcontentloaded",
                timeout=self.POST_PAGE_TIMEOUT_MS,
            )
            content_ok = await wait_for_content(page, timeout_s=self.POST_PAGE_CONTENT_TIMEOUT_S)
            html = await page.content()
            if not content_ok or len(html) < 1000:
                raise ScraperBlockedError(
                    f"Substack post page unresolved challenge stub: {post_url} bytes={len(html)}"
                )
            try:
                await human_scroll(page, direction="down", steps=2)
                await page.wait_for_selector(SUBSTACK_POST["comments"]["primary"], timeout=self.POST_PAGE_COMMENT_TIMEOUT_MS)
            except Exception:
                pass
            soup = BeautifulSoup(await page.content(), "lxml")
            views = self._extract_post_page_views(soup)
            comments = self._extract_post_page_comments(soup)
            publish_date = self._extract_post_page_date(soup)
            title = self._extract_post_page_title(soup)
            return views, comments, publish_date, title, False
        except ScraperBlockedError:
            return None, None, None, None, True
        except Exception:
            return None, None, None, None, False
        finally:
            await page.close()

    def _extract_name(self, soup: BeautifulSoup, channel_url: str, page_title: str) -> str:
        node = soup.select_one(SUBSTACK_CHANNEL["channel_name"]["primary"])
        if node is not None:
            text = " ".join(node.stripped_strings)
            if text:
                return text
        for fallback in SUBSTACK_CHANNEL["channel_name"]["fallbacks"]:
            node = soup.select_one(fallback)
            if not isinstance(node, Tag):
                continue
            if node.name == "meta":
                content = str(node.get("content") or "").strip()
                if content:
                    return content
            else:
                text = node.get_text(" ", strip=True)
                if text:
                    return text
        meta = soup.select_one("meta[property='og:site_name']")
        if isinstance(meta, Tag):
            content = str(meta.get("content") or "").strip()
            if content:
                return content
        title = re.sub(r"\s*[-|]\s*Substack\s*$", "", page_title).strip()
        if title:
            return title
        return channel_url.rstrip("/").split("/")[-1]

    def _extract_description(self, soup: BeautifulSoup) -> str:
        # FIX C: meta[name="description"] requires .get("content"), not .get_text()
        primary = soup.select_one(SEL_CHANNEL_BIO)
        if isinstance(primary, Tag):
            content = str(primary.get("content") or "").strip()
            if content:
                return content
        for fallback in SUBSTACK_CHANNEL["channel_description"]["fallbacks"]:
            node = soup.select_one(fallback)
            if not isinstance(node, Tag):
                continue
            if node.name == "meta":
                content = str(node.get("content") or "").strip()
                if content:
                    return content
            else:
                text = node.get_text("\n", strip=True)
                if text:
                    return text
        return ""

    def _extract_subscribers(self, soup: BeautifulSoup) -> int | None:
        node = soup.select_one(SUBSTACK_CHANNEL["subscriber_count"]["primary"])
        if node is not None:
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed
        for fallback in SUBSTACK_CHANNEL["subscriber_count"]["fallbacks"]:
            if fallback == "script[type='application/ld+json']":
                continue
            node = soup.select_one(fallback)
            if node is not None:
                parsed = parse_count_text(node.get_text(" ", strip=True))
                if parsed is not None:
                    return parsed
        for script in soup.select("script[type='application/ld+json']"):
            text = script.get_text(" ", strip=True)
            parsed = parse_count_text(text)
            if parsed is not None and "subscriber" in text.lower():
                return parsed
        preloads_payload = self._extract_preloads_payload(soup)
        if preloads_payload is not None:
            parsed = self._extract_subscribers_from_json(preloads_payload)
            if parsed is not None:
                return parsed
        for script in soup.select("script"):
            text = script.get_text(" ", strip=True)
            if not text:
                continue
            normalized = text.replace('\\"', '"')
            for pattern in (
                r'"subscriberCountNumber"\s*:\s*(\d+)',
                r'"subscriberCountString"\s*:\s*"([^"]+)"',
                r'"subscriberCount"\s*:\s*"([^"]+)"',
                r'"freeSubscriberCountOrderOfMagnitude"\s*:\s*"([^"]+)"',
                r'"freeSubscriberCount"\s*:\s*"([^"]+)"',
                r'"rankingDetailFreeSubscriberCount"\s*:\s*"([^"]+)"',
            ):
                match = re.search(pattern, normalized)
                if not match:
                    continue
                value = match.group(1)
                if value.isdigit():
                    return int(value)
                parsed = parse_count_text(value)
                if parsed is not None:
                    return parsed
        next_data = soup.select_one("script#__NEXT_DATA__")
        if isinstance(next_data, Tag):
            try:
                payload = json.loads(next_data.get_text(" ", strip=True))
                parsed = self._extract_subscribers_from_json(payload)
                if parsed is not None:
                    return parsed
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return None

    def _extract_preloads_payload(self, soup: BeautifulSoup) -> object | None:
        for script in soup.select("script"):
            text = script.get_text(" ", strip=True)
            if "window._preloads" not in text or "JSON.parse(" not in text:
                continue
            match = re.search(r'window\._preloads\s*=\s*JSON\.parse\("(.+?)"\)', text)
            if not match:
                continue
            try:
                # Decode escaped JSON string passed into JSON.parse("...")
                encoded = f'"{match.group(1)}"'
                decoded = json.loads(encoded)
                return json.loads(decoded)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return None

    def _extract_post_title(self, card: Tag, link: Tag) -> str:
        node = card.select_one(self.POST_TITLE_SELECTOR)
        if node is not None:
            text = node.get_text(" ", strip=True)
            if text:
                return text
        for attr in ("title", "aria-label"):
            text = str(link.get(attr) or "").strip()
            if text:
                return text
        return link.get_text(" ", strip=True)

    def _extract_post_card_views(self, card: Tag) -> int | None:
        # FIX B primary: confirmed selector from live DOM dump
        like_label = card.select_one(SEL_POST_LIKES)
        if isinstance(like_label, Tag):
            parsed = parse_count_text(like_label.get_text(" ", strip=True))
            if parsed is not None:
                return parsed
        # Fallback: aria-label on like button
        like_button = card.select_one("button[aria-label*='Like']")
        if isinstance(like_button, Tag):
            parsed = self._extract_metric_from_button(like_button)
            if parsed is not None:
                return parsed
            return 0
        return None

    def _extract_post_card_comments(self, card: Tag) -> int | None:
        # FIX B primary: confirmed selector from live DOM dump
        comment_label = card.select_one(SEL_POST_COMMENTS)
        if isinstance(comment_label, Tag):
            parsed = parse_count_text(comment_label.get_text(" ", strip=True))
            if parsed is not None:
                return parsed
        # Fallback: aria-label on comment button
        comment_button = card.select_one("button[aria-label*='comment']")
        if isinstance(comment_button, Tag):
            parsed = self._extract_metric_from_button(comment_button)
            if parsed is not None:
                return parsed
            return 0
        return None

    def _extract_post_card_metric_values(self, card: Tag) -> list[int]:
        values: list[int] = []
        for node in card.select(self.POST_VIEWS_SELECTOR):
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                values.append(parsed)
        return values

    def _extract_post_card_date(self, card: Tag) -> datetime | None:
        node = card.select_one(self.POST_DATE_SELECTOR)
        if node is None:
            return None
        if node.name == "time":
            parsed = parse_substack_datetime(str(node.get("datetime") or ""))
            if parsed is not None:
                return parsed
        return parse_substack_datetime(node.get_text(" ", strip=True))

    def _extract_subscribers_from_json(self, payload: object) -> int | None:
        if isinstance(payload, dict):
            for key in ("subscriberCountString", "subscriberCount", "subscriberCountNumber"):
                if key in payload:
                    value = payload.get(key)
                    if isinstance(value, (int, float)):
                        return int(value)
                    if isinstance(value, str):
                        parsed = parse_count_text(value)
                        if parsed is not None:
                            return parsed
            for value in payload.values():
                parsed = self._extract_subscribers_from_json(value)
                if parsed is not None:
                    return parsed
        elif isinstance(payload, list):
            for item in payload:
                parsed = self._extract_subscribers_from_json(item)
                if parsed is not None:
                    return parsed
        return None

    def _extract_post_page_views(self, soup: BeautifulSoup) -> int | None:
        like_button = soup.select_one("button[aria-label='Like']")
        if isinstance(like_button, Tag):
            parsed = self._extract_metric_from_button(like_button)
            if parsed is not None:
                return parsed
            return 0
        node = soup.select_one(SUBSTACK_POST["views"]["primary"])
        if node is not None:
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed
        return None

    def _extract_post_page_comments(self, soup: BeautifulSoup) -> int | None:
        comment_button = soup.select_one("button[aria-label='Comment']")
        if isinstance(comment_button, Tag):
            parsed = self._extract_metric_from_button(comment_button)
            if parsed is not None:
                return parsed
            return 0
        node = soup.select_one(SUBSTACK_POST["comments"]["primary"])
        if node is not None:
            parsed = parse_count_text(node.get_text(" ", strip=True))
            if parsed is not None:
                return parsed
        return None

    def _extract_post_page_date(self, soup: BeautifulSoup) -> datetime | None:
        node = soup.select_one("time[datetime]")
        if node is not None:
            parsed = parse_substack_datetime(str(node.get("datetime") or ""))
            if parsed is not None:
                return parsed
        meta = soup.select_one("meta[property='article:published_time']")
        if isinstance(meta, Tag):
            return parse_substack_datetime(str(meta.get("content") or ""))
        return None

    def _extract_post_page_title(self, soup: BeautifulSoup) -> str:
        node = soup.select_one(SUBSTACK_POST["title"]["primary"])
        if node is not None:
            text = node.get_text(" ", strip=True)
            if text:
                return text
        meta = soup.select_one("meta[property='og:title']")
        if isinstance(meta, Tag):
            return str(meta.get("content") or "").strip()
        return ""

    def _extract_metric_from_button(self, button: Tag) -> int | None:
        for node in button.select("div, span"):
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            parsed = parse_count_text(text)
            if parsed is not None:
                return parsed
        return parse_count_text(button.get_text(" ", strip=True))

    def _extract_external_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        links: set[str] = set()
        for anchor in soup.select(SUBSTACK_CHANNEL["external_links"]["primary"]):
            href = str(anchor.get("data-href") or anchor.get("href") or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            absolute = urljoin(base_url, href)
            host = (urlsplit(absolute).hostname or "").lower()
            if host.endswith("substack.com"):
                continue
            if not absolute.lower().startswith(("http://", "https://")):
                continue
            links.add(absolute)
        if not links:
            for anchor in soup.select("a[href]"):
                href = str(anchor.get("href") or "").strip()
                if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                    continue
                absolute = urljoin(base_url, href)
                host = (urlsplit(absolute).hostname or "").lower()
                if host.endswith("substack.com"):
                    continue
                if not absolute.lower().startswith(("http://", "https://")):
                    continue
                links.add(absolute)
        return self._filter_contact_info(sorted(links))

    def _extract_mailto_emails(self, soup: BeautifulSoup) -> list[str]:
        emails: list[str] = []
        for node in soup.select(SUBSTACK_CHANNEL["email_addresses"]["primary"]):
            href = str(node.get("href") or "").strip()
            if href.lower().startswith("mailto:"):
                addr = href.split(":", 1)[1].split("?", 1)[0].strip().lower()
                if addr:
                    emails.append(addr)
        return sorted(set(emails))

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
