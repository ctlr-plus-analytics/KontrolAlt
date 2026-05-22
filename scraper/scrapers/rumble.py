"""Rumble scraper with resilient channel-card extraction."""

import logging
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag
from patchright.async_api import Error as PlaywrightError

from core.browser import BrowserTelemetry, human_delay, launch_browser, wait_for_content
from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from scrapers.base import BaseScraper
from utils.contact_extractor import extract_emails, extract_urls
from utils.keyword_matcher import compute_channel_demographic, compute_comment_tier

logger = logging.getLogger(__name__)

RUMBLE_BASE_URL = "https://rumble.com"


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
    DEMOGRAPHIC_TITLE_LIMIT = 20
    VIDEO_PAGE_FALLBACK_LIMIT = 15

    async def scrape(self, channel_url: str) -> dict[str, object]:
        """Scrape a single Rumble channel."""
        try:
            telemetry = BrowserTelemetry()
            async with launch_browser(session_key=channel_url, telemetry=telemetry) as context:
                page = await context.new_page()
                response = await page.goto(
                    channel_url, wait_until="domcontentloaded", timeout=45000
                )
                await human_delay(3.0, 6.0)

                content_ok = await wait_for_content(page, min_bytes=5000, timeout_s=20.0)
                if not content_ok:
                    logger.warning("Rumble: content not ready, reloading %s", channel_url)
                    await page.reload(wait_until="domcontentloaded", timeout=45000)
                    await human_delay(5.0, 8.0)
                    content_ok = await wait_for_content(page, min_bytes=5000, timeout_s=20.0)

                await self.ensure_not_blocked(page, channel_url)
                if not content_ok:
                    raise ScraperBlockedError(f"Rumble page empty after reload: {channel_url}")

                try:
                    await page.wait_for_selector(
                        "div.videostream.thumbnail__grid--item, "
                        ".thumbnail__grid--item, article, a[href*='/v']",
                        timeout=15000,
                    )
                    await human_delay(1.0, 2.0)
                except PlaywrightError:
                    logger.warning(
                        "Rumble: video grid did not render before parsing %s",
                        channel_url,
                    )

                video_data_map = await self._collect_videos_with_scroll(page)
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                page_title = await page.title() or ""
                response_status = response.status if response is not None else None
                body_text = soup.get_text(" ", strip=True).lower()
                self.classify_terminal_page_state(
                    channel_url=channel_url,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=response_status,
                )

                name = self._extract_name(soup, channel_url, page_title)
                subscriber_count = self._extract_subscribers(soup)
                main_socials = self._extract_external_links(soup, channel_url)

                about_url = channel_url.rstrip("/") + "/about"
                description = ""
                about_socials: list[str] = []
                try:
                    about_page = await context.new_page()
                    try:
                        await about_page.goto(
                            about_url, wait_until="domcontentloaded", timeout=30000
                        )
                        await human_delay(2.0, 4.0)
                        if await wait_for_content(about_page, min_bytes=3000, timeout_s=10.0):
                            about_soup = BeautifulSoup(await about_page.content(), "html.parser")
                            description = self._extract_description(about_soup)
                            about_socials = self._extract_external_links(about_soup, about_url)
                    finally:
                        await about_page.close()
                except Exception as exc:
                    logger.warning("Rumble: Failed to fetch About page for %s: %s", channel_url, exc)

                if not description:
                    description = self._extract_description(soup)

                all_secondary = sorted(set(main_socials + about_socials))
                combined_text = f"{description}\n{soup.get_text(' ', strip=True)}"
                emails = extract_emails(combined_text)
                urls = extract_urls(combined_text)
                contact_info = sorted(set(emails + urls + all_secondary))

                fallback_items = list(video_data_map.values())[: self.VIDEO_PAGE_FALLBACK_LIMIT]
                for item in fallback_items:
                    existing_views = item.get("views")
                    existing_comments = item.get("comments")
                    existing_date = item.get("date")
                    needs_views = existing_views is None
                    needs_comment = existing_comments is None
                    needs_date = existing_date is None
                    if not needs_views and not needs_comment and not needs_date:
                        continue
                    video_url = str(item.get("url") or "")
                    if not video_url:
                        continue
                    views, comments, publish_date = await self._extract_video_page_signals(
                        context, video_url
                    )
                    self._merge_video_page_signals(
                        item=item,
                        needs_views=needs_views,
                        needs_comment=needs_comment,
                        needs_date=needs_date,
                        views=views,
                        comments=comments,
                        publish_date=publish_date,
                    )

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
                    for video in video_data_map.values()
                    if video.get("comments") is not None
                ][: self.VIDEO_COLLECTION_LIMIT]
                upload_dates = [
                    video["date"]
                    for video in video_data_map.values()
                    if isinstance(video.get("date"), datetime)
                ][: self.VIDEO_COLLECTION_LIMIT]

                avg_views = self.compute_avg(view_counts)
                avg_comments = self.compute_avg(comment_counts)
                comment_tier = compute_comment_tier(avg_comments)
                demographic = compute_channel_demographic(
                    name, description, video_titles[: self.DEMOGRAPHIC_TITLE_LIMIT]
                )
                posts_per_week = self.compute_posting_cadence(upload_dates)
                last_active_date = max(upload_dates).date() if upload_dates else None
                logger.info(
                    "Rumble extraction quality for %s: videos=%d views=%d comments=%d dates=%d",
                    channel_url,
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
                    channel_url=channel_url,
                    video_titles=video_titles,
                    avg_views=avg_views,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=response_status,
                )

                channel_data = {
                    "platform": "rumble",
                    "channel_url": channel_url,
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

                logger.info("Rumble scrape complete for %s (%s)", name, channel_url)
                logger.info(
                    "Rumble transfer estimate for %s: responses=%d bytes_est=%d",
                    channel_url,
                    telemetry.response_count,
                    telemetry.total_bytes_est,
                )
                channel_data["_scrape_metrics"] = {
                    "bytes_est": telemetry.total_bytes_est,
                    "responses": telemetry.response_count,
                }
                return channel_data

        except (PlaywrightError, ScraperBlockedError, ScraperClassifiedError) as exc:
            logger.error("Rumble scrape failed for %s: %s", channel_url, exc)
            raise

    def _extract_name(self, soup: BeautifulSoup, channel_url: str, page_title: str) -> str:
        """Extract channel name from header, metadata, or URL fallback."""
        selectors = [
            ".channel-header--title h1",
            "h1.channel-header--title",
            "h1",
            "[class*='channel'] h1",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if node is not None:
                name = node.get_text(" ", strip=True)
                name = re.sub(r"\s+\d[\d,.\s]*[kmb]?\s+followers?.*$", "", name, flags=re.I)
                if name:
                    return name

        for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
            meta = soup.find("meta", attrs=attrs)
            if isinstance(meta, Tag):
                value = str(meta.get("content") or "").strip()
                if value:
                    return re.sub(r"\s*[-|]\s*Rumble\s*$", "", value).strip()

        title = re.sub(r"\s*[-|]\s*Rumble\s*$", "", page_title).strip()
        if title:
            return title
        return channel_url.rstrip("/").split("/")[-1]

    def _extract_subscribers(self, soup: BeautifulSoup) -> int | None:
        """Extract follower count from header, text blocks, or metadata."""
        for selector in [
            ".channel-header--title span",
            "[class*='followers']",
            "[class*='follower']",
            "[aria-label*='Follower']",
            "[title*='Follower']",
        ]:
            for node in soup.select(selector):
                candidates = [
                    node.get_text(" ", strip=True),
                    str(node.get("aria-label") or ""),
                    str(node.get("title") or ""),
                ]
                for text in candidates:
                    if "follower" in text.lower():
                        parsed = parse_follower_count(text)
                        if parsed is not None:
                            return parsed

        text = soup.get_text(" ", strip=True)
        match = re.search(r"(\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+followers?\b", text, re.I)
        if match:
            return parse_follower_count(match.group(1))
        return None

    async def _collect_videos_with_scroll(self, page) -> dict[str, dict[str, object]]:
        """Collect a deeper recent-video window across scrolls and paginated pages."""
        collected: dict[str, dict[str, object]] = {}
        visited_pages: set[str] = set()
        max_pages = 5

        for _ in range(max_pages):
            current_page_url = page.url
            if current_page_url in visited_pages:
                break
            visited_pages.add(current_page_url)

            stagnant_rounds = 0
            next_page_url: str | None = None
            for _ in range(8):
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")
                parsed = self._extract_videos(soup)
                before = len(collected)
                for video_id, payload in parsed.items():
                    if video_id not in collected:
                        collected[video_id] = payload

                if len(collected) >= self.VIDEO_COLLECTION_LIMIT:
                    break

                next_page_url = self._extract_next_page_url(soup, page.url)
                stagnant_rounds = stagnant_rounds + 1 if len(collected) == before else 0
                if stagnant_rounds >= 2 and next_page_url:
                    break
                if stagnant_rounds >= 3:
                    break

                await page.mouse.wheel(0, 3200)
                await human_delay(1.2, 2.5)

            if len(collected) >= self.VIDEO_COLLECTION_LIMIT:
                break
            if not next_page_url or next_page_url in visited_pages:
                break
            try:
                await page.goto(next_page_url, wait_until="domcontentloaded", timeout=45000)
                await human_delay(1.5, 3.0)
            except PlaywrightError as exc:
                logger.debug("Rumble: Could not follow next page %s: %s", next_page_url, exc)
                break

        return self._trim_video_map(collected)

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
        """Extract recent video cards with multi-selector fallbacks."""
        video_map: dict[str, dict[str, object]] = {}
        cards = soup.select(
            "div.videostream.thumbnail__grid--item, "
            ".thumbnail__grid--item, "
            "article:has(a[href*='/v']), "
            "li:has(a[href*='/v'])"
        )
        if not cards:
            anchors = soup.select("a[href*='/v']")
            cards = [
                anchor.find_parent(["article", "li", "div"]) or anchor
                for anchor in anchors
            ]

        for card in cards:
            if len(video_map) >= self.VIDEO_COLLECTION_LIMIT or not isinstance(card, Tag):
                break
            link = card.select_one("a[href*='/v']") or card.find("a", href=True)
            if not isinstance(link, Tag):
                continue
            href = str(link.get("href") or "")
            if not self._is_video_href(href):
                continue
            video_url = urljoin(RUMBLE_BASE_URL, href)
            video_id = video_url.rstrip("/").split("/")[-1]
            if not video_id or video_id in video_map:
                continue

            title = self._extract_video_title(card, link)
            views = self._extract_card_count(
                card,
                selectors=[
                    "span.videostream__views[data-views]",
                    "span.videostream__views",
                    "[class*='views']",
                    "[aria-label*='view']",
                    "[title*='view']",
                ],
                data_keys=["data-views", "data-value", "title", "aria-label"],
                label_pattern=r"(\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+views?\b",
            )
            comments = self._extract_card_count(
                card,
                selectors=[
                    "span.videostream__comments[title]",
                    "span.videostream__comments",
                    "[class*='comments']",
                    "[aria-label*='comment']",
                    "[title*='comment']",
                ],
                data_keys=["data-comments", "data-value", "title", "aria-label"],
                label_pattern=r"(\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+comments?\b",
            )
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
        needs_views: bool,
        needs_comment: bool,
        needs_date: bool,
        views: int | None,
        comments: int | None,
        publish_date: datetime | None,
    ) -> None:
        """Merge deeper video-page metadata without overwriting card data."""
        if needs_views and views is not None:
            item["views"] = views
        if needs_comment and comments is not None:
            item["comments"] = comments
        if needs_date and publish_date is not None:
            item["date"] = publish_date

    async def _extract_video_page_signals(
        self, context, video_url: str
    ) -> tuple[int | None, int | None, datetime | None]:
        """Open a Rumble video page and extract missing views, comments, and date."""
        page = await context.new_page()
        try:
            await human_delay(1.5, 3.0)
            await page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
            await human_delay(2.0, 4.0)
            await wait_for_content(page, min_bytes=5000, timeout_s=15.0)
            soup = BeautifulSoup(await page.content(), "html.parser")
            body_text = soup.get_text(" ", strip=True)

            views = self._extract_page_count(
                soup=soup,
                selectors=[
                    "[class*='views']",
                    "[aria-label*='view']",
                    "[title*='view']",
                    "meta[itemprop='interactionCount']",
                ],
                metric_label="view",
                label_pattern=r"(\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+views?\b",
            )
            comments = self._extract_page_count(
                soup=soup,
                selectors=[
                    "[class*='comments']",
                    "[aria-label*='comment']",
                    "[title*='comment']",
                ],
                metric_label="comment",
                label_pattern=r"(\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+comments?\b",
            )
            publish_date = self._extract_card_date(soup)
            if publish_date is None:
                match = re.search(
                    r"(\d+\s+(?:second|minute|hour|day|week|month|year|sec|min|hr|wk|mo|yr)s?\s+ago|yesterday|just now)",
                    body_text,
                    flags=re.I,
                )
                if match:
                    publish_date = parse_rumble_datetime(match.group(1))

            return views, comments, publish_date
        except Exception as exc:
            logger.debug("Rumble: Could not extract video signals from %s: %s", video_url, exc)
            return None, None, None
        finally:
            await page.close()

    def _extract_page_count(
        self,
        *,
        soup: BeautifulSoup,
        selectors: list[str],
        metric_label: str,
        label_pattern: str,
    ) -> int | None:
        """Extract a count from video-page metadata, attributes, or body text."""
        for selector in selectors:
            for node in soup.select(selector):
                node_context = " ".join(
                    [
                        str(node.get("class") or ""),
                        str(node.get("aria-label") or ""),
                        str(node.get("title") or ""),
                        str(node.get("itemprop") or ""),
                        node.get_text(" ", strip=True),
                    ]
                ).lower()
                if metric_label not in node_context and "interactioncount" not in node_context:
                    continue
                candidates = [
                    node.get_text(" ", strip=True),
                    str(node.get("content") or ""),
                    str(node.get("aria-label") or ""),
                    str(node.get("title") or ""),
                    str(node.get("data-value") or ""),
                ]
                for candidate in candidates:
                    parsed = parse_count_text(candidate)
                    if parsed is not None:
                        return parsed
        match = re.search(label_pattern, soup.get_text(" ", strip=True), re.I)
        if match:
            return parse_count_text(match.group(1))
        return None

    def _extract_video_title(self, card: Tag, link: Tag) -> str:
        for selector in ["h3.thumbnail__title", "[class*='title']", "h3", "h2"]:
            node = card.select_one(selector)
            if node is not None:
                text = str(node.get("title") or node.get_text(" ", strip=True)).strip()
                if text:
                    return text
        for attr in ["title", "aria-label"]:
            text = str(link.get(attr) or "").strip()
            if text:
                return text
        img = card.select_one("img[alt]")
        if img is not None:
            return str(img.get("alt") or "").strip()
        return link.get_text(" ", strip=True)

    def _extract_card_count(
        self,
        card: Tag,
        *,
        selectors: list[str],
        data_keys: list[str],
        label_pattern: str,
    ) -> int | None:
        for selector in selectors:
            for node in card.select(selector):
                candidates = [str(node.get(key) or "") for key in data_keys]
                candidates.append(node.get_text(" ", strip=True))
                for candidate in candidates:
                    parsed = parse_count_text(candidate)
                    if parsed is not None:
                        return parsed
        match = re.search(label_pattern, card.get_text(" ", strip=True), re.I)
        if match:
            return parse_count_text(match.group(1))
        return None

    def _extract_card_date(self, card: Tag) -> datetime | None:
        for time_node in card.select("time"):
            for candidate in [
                str(time_node.get("datetime") or ""),
                str(time_node.get("title") or ""),
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
        selectors = [
            ".channel-about--description",
            "[class*='about'] [class*='description']",
            "[class*='description']",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if node is not None:
                text = node.get_text("\n", strip=True)
                if text:
                    return text
        for attrs in ({"property": "og:description"}, {"name": "description"}):
            meta = soup.find("meta", attrs=attrs)
            if isinstance(meta, Tag):
                text = str(meta.get("content") or "").strip()
                if text:
                    return text
        return ""

    def _extract_external_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        links: set[str] = set()
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            absolute = urljoin(base_url, href)
            if "rumble.com" not in absolute:
                links.add(absolute)
        return sorted(links)
