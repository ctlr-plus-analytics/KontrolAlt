"""BitChuteScraper — full Patchright scraper for BitChute channel pages."""

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from patchright.async_api import Error as PlaywrightError

from core.browser import BrowserTelemetry, human_delay, launch_browser, wait_for_content
from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from scrapers.base import BaseScraper
from utils.contact_extractor import extract_emails, extract_urls
from utils.keyword_matcher import (
    compute_channel_demographic,
    compute_comment_tier,
)

logger = logging.getLogger(__name__)

BITCHUTE_BASE_URL = "https://www.bitchute.com"


class BitChuteScraper(BaseScraper):
    """Scraper for BitChute channels using Patchright."""

    VIDEO_COLLECTION_LIMIT = 50
    DEMOGRAPHIC_TITLE_LIMIT = 20
    VIDEO_PAGE_FALLBACK_LIMIT = 20

    async def scrape(self, channel_url: str) -> dict[str, object]:
        """Scrape a single BitChute channel.

        Extracts: channel name, subscriber count, recent videos
        (title, views, comments, date), description, external links,
        and contact emails.

        Args:
            channel_url: Full URL of the BitChute channel.

        Returns:
            Scraped channel data dict with all computed fields.
        """
        try:
            telemetry = BrowserTelemetry()
            async with launch_browser(session_key=channel_url, telemetry=telemetry) as context:
                page = await context.new_page()

                # Navigate — use domcontentloaded then actively wait for
                # Cloudflare's JS challenge to resolve.
                response = await page.goto(
                    channel_url, wait_until="domcontentloaded", timeout=90000
                )
                await human_delay(3.0, 6.0)

                # Wait up to 20 s for real content to appear
                content_ok = await wait_for_content(page, min_bytes=5000, timeout_s=20.0)
                if not content_ok:
                    logger.warning(
                        "BitChute: CF challenge not resolved after 20 s, reloading %s",
                        channel_url,
                    )
                    await page.reload(wait_until="domcontentloaded", timeout=90000)
                    await human_delay(5.0, 8.0)
                    content_ok = await wait_for_content(page, min_bytes=5000, timeout_s=20.0)

                await self.ensure_not_blocked(page, channel_url)

                if not content_ok:
                    raise ScraperBlockedError(
                        f"BitChute page still empty after reload — CF block persists: {channel_url}"
                    )

                # Wait for at least one video card to render
                try:
                    await page.wait_for_selector(".video-card-title, a[href*='/video/']", timeout=20000)
                    # Scroll deeper to trigger hydration
                    await page.mouse.wheel(0, 1500)
                    await human_delay(3.0, 5.0)
                    await page.mouse.wheel(0, -1000)
                    await human_delay(2.0, 3.0)
                except Exception:
                    logger.warning("BitChute: Video content not found on landing page for %s", channel_url)

                # Load more video cards before snapshot parsing.
                for _ in range(6):
                    await page.mouse.wheel(0, 2600)
                    await human_delay(1.5, 3.0)

                # --- Step 1: Extract videos and summary (Live Extraction) ---
                video_data_map = {}
                # Wait for at least one card to have views or title text (hydration check)
                try:
                    await page.wait_for_function(
                        "() => [...document.querySelectorAll('.video-card-title')].some(el => el.innerText.length > 5)",
                        timeout=10000
                    )
                except Exception:
                    logger.debug("BitChute: Hydration wait timed out for %s", channel_url)

                cards = await page.locator("#video-card, .q-card").all()
                
                # Fallback: If no cards found on Home tab, try Clicking "Videos" tab
                if not cards or len(cards) < 2:
                    logger.info("BitChute: No cards on Home tab, trying 'Videos' tab for %s", channel_url)
                    try:
                        videos_selectors = [
                            ".q-tab:has-text('Videos')",
                            "[role='tab']:has-text('Videos')",
                            "text='Videos'",
                        ]
                        for selector in videos_selectors:
                            videos_tab = page.locator(selector).first
                            if await videos_tab.is_visible(timeout=5000):
                                await videos_tab.click()
                                await page.wait_for_selector(".video-card-title, a[href*='/video/']", timeout=15000)
                                await page.mouse.wheel(0, 1500)
                                await human_delay(3.0, 5.0)
                                cards = await page.locator("#video-card, .q-card").all()
                                break
                    except Exception as e:
                        logger.warning("BitChute: Videos tab fallback failed for %s: %s", channel_url, e)

                logger.info("BitChute: Found %d cards live for %s", len(cards), channel_url)
                
                for i, card in enumerate(cards):
                    if i >= self.VIDEO_COLLECTION_LIMIT:
                        break
                    try:
                        # Extract Video ID from link
                        link_el = card.locator("a[href*='/video/']").first
                        href = await link_el.get_attribute("href") or ""
                        video_id = href.rstrip("/").split("/")[-1]
                        if not video_id: continue
                        video_url = self._to_absolute_url(href)
                        
                        # Extract Title
                        title = ""
                        # Try to find the first link that isn't empty
                        all_links = await card.locator("a").all()
                        for link in all_links:
                            link_text = await link.inner_text()
                            if len(link_text) > 10:
                                title = link_text.strip()
                                break
                        
                        # Fallback to specific title selectors if above failed
                        if not title:
                            title_selectors = [".video-card-title", ".q-item__label", "a.text-bold", ".text-h6"]
                            for sel in title_selectors:
                                title_el = card.locator(sel).first
                                if await title_el.count() > 0:
                                    title = await title_el.inner_text()
                                    if title: break
                        
                        # Extract Views & Date by scanning all text in the card
                        views: int | None = None
                        comments: int | None = None
                        date_val = None
                        
                        # Get all spans and labels in the card
                        info_elements = await card.locator("span, .q-item__label--caption, .video-card-info").all()
                        card_full_text = (await card.inner_text()).lower()
                        
                        # Strategy A: Regex match on full card text for "visibility\n123" or "123 views"
                        view_match = re.search(r"(?:visibility|views)\s+([\d\.,]+)\s*([km])?", card_full_text)
                        if view_match:
                            views = self._parse_bitchute_count(view_match.group(0))
                        
                        # Strategy B: Individual element scan (fallback)
                        if views is None:
                            for el in info_elements:
                                text = (await el.inner_text()).lower()
                                if "views" in text or "visibility" in text:
                                    parsed_views = self._parse_bitchute_count(text)
                                    if parsed_views is not None:
                                        views = parsed_views
                                        break
                        
                        # Strategy C: Pure numeric fallback if still 0
                        if views is None:
                            for el in info_elements:
                                text = (await el.inner_text()).lower()
                                if re.search(r"^\s*[\d\.]+[km]?\s*$", text):
                                    parsed_views = self._parse_bitchute_count(text)
                                    if parsed_views is not None:
                                        views = parsed_views
                                        break

                        # Extract comments
                        comments = await self._extract_comments_from_card(card)

                        # Extract Date
                        for el in info_elements:
                            text = (await el.inner_text()).lower()
                            if "ago" in text or "yesterday" in text or "published" in text:
                                date_val = self._parse_bitchute_date(text)
                                if date_val: break
                        
                        if video_id:
                            video_data_map[video_id] = {
                                "title": title or "Unknown Title",
                                "views": views,
                                "comments": comments,
                                "comments_source": "card" if comments is not None else None,
                                "date": date_val,
                                "url": video_url,
                            }
                    except Exception as e:
                        logger.debug("Error extracting card %d: %s", i, e)

                # Summary details (Subscribers, Name) from static soup (still fine for header)
                soup_main = BeautifulSoup(await page.content(), "html.parser")
                page_title = await page.title() or ""
                response_status = response.status if response is not None else None
                body_text = soup_main.get_text(" ", strip=True).lower()
                self.classify_terminal_page_state(
                    channel_url=channel_url,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=response_status,
                )
                subscriber_count = self._extract_subscribers(soup_main)
                name = self._extract_name(soup_main, channel_url)

                # Prefer static full-page parse for modern BitChute card markup.
                # Collect in a bounded scroll loop to reach a deeper recent-video window.
                await self._open_videos_tab_if_available(page, channel_url)
                parsed_map = await self._collect_videos_with_scroll(page)
                if parsed_map:
                    video_data_map = self._merge_video_maps(video_data_map, parsed_map)

                api_fallback = await self._fetch_api_channel_fallback(context, channel_url)
                if api_fallback:
                    api_videos = api_fallback.get("videos")
                    if isinstance(api_videos, dict):
                        video_data_map = self._merge_video_maps(video_data_map, api_videos)

                # Comments and publish dates are most reliable on video pages
                # when channel-card metadata is partial.
                fallback_items = list(video_data_map.values())[: self.VIDEO_PAGE_FALLBACK_LIMIT]
                for item in fallback_items:
                    existing_comments = item.get("comments")
                    existing_date = item.get("date")
                    needs_comment = not (
                        isinstance(existing_comments, (int, float)) and existing_comments > 0
                    )
                    needs_date = existing_date is None
                    if not needs_comment and not needs_date:
                        continue
                    video_url = str(item.get("url") or "")
                    if not video_url:
                        continue
                    comment_count, publish_date = await self._extract_video_page_signals(
                        context, video_url
                    )
                    self._merge_video_page_signals(
                        item=item,
                        needs_comment=needs_comment,
                        needs_date=needs_date,
                        comment_count=comment_count,
                        publish_date=publish_date,
                    )

                # --- Step 2: Click 'About' tab ---
                # (Keep existing About tab logic...)
                description = ""
                external_links = []
                
                try:
                    # BitChute uses Quasar tabs. Text is "About"
                    # Try several selectors for the About tab
                    about_selectors = [
                        ".q-tab:has-text('About')",
                        "text='About'",
                        ".q-tab__label:text-is('About')",
                        "[role='tab']:has-text('About')"
                    ]
                    about_clicked = False
                    for sel in about_selectors:
                        try:
                            # Use locator for better visibility check
                            about_tab = page.locator(sel).first
                            if await about_tab.is_visible(timeout=3000):
                                logger.info("BitChute: Clicking About tab for %s", channel_url)
                                await about_tab.click()
                                await human_delay(2.0, 4.0)
                                about_clicked = True
                                break
                        except Exception:
                            continue
                    
                    if about_clicked:
                        html_about = await page.content()
                        soup_about = BeautifulSoup(html_about, "html.parser")
                        description = self._extract_description(soup_about)
                        external_links = self._extract_external_links(soup_about)
                    else:
                        logger.warning("BitChute: Could not find About tab for %s, using main page fallback", channel_url)
                        description = self._extract_description(soup_main)
                        external_links = self._extract_external_links(soup_main)

                except Exception as exc:
                    logger.warning("BitChute: Error during About tab extraction for %s: %s", channel_url, exc)
                    description = self._extract_description(soup_main)
                    external_links = self._extract_external_links(soup_main)

                if api_fallback:
                    api_description = str(api_fallback.get("description") or "")
                    api_links = [
                        str(value)
                        for value in api_fallback.get("external_links", [])
                        if isinstance(value, str)
                    ]
                    if len(api_description) > len(description):
                        description = api_description
                    external_links = sorted(set(external_links + api_links))

                # --- Extract emails and URLs from description ---
                emails = extract_emails(description + " " + " ".join(external_links))
                all_urls = extract_urls(description)
                contact_info = sorted(set(emails + all_urls + external_links))

                # --- Compute derived fields ---
                video_titles = [
                    str(v["title"])
                    for v in video_data_map.values()
                    if v.get("title") and not self._is_bad_video_title(str(v["title"]))
                ][: self.VIDEO_COLLECTION_LIMIT]
                view_counts = [
                    float(v["views"])
                    for v in video_data_map.values()
                    if v.get("views") is not None
                ][: self.VIDEO_COLLECTION_LIMIT]
                comment_counts = [
                    float(v["comments"])
                    for v in video_data_map.values()
                    if v.get("comments") is not None
                ][: self.VIDEO_COLLECTION_LIMIT]
                upload_dates = [
                    v["date"]
                    for v in video_data_map.values()
                    if v["date"]
                ][: self.VIDEO_COLLECTION_LIMIT]

                avg_views = self.compute_avg(view_counts)
                avg_comments = self.compute_avg(comment_counts)
                comment_tier = compute_comment_tier(avg_comments)
                demographic = compute_channel_demographic(
                    name, description, video_titles[: self.DEMOGRAPHIC_TITLE_LIMIT]
                )
                posts_per_week = self.compute_posting_cadence(upload_dates)
                last_active = max(upload_dates) if upload_dates else None
                total_videos_considered = min(self.VIDEO_COLLECTION_LIMIT, len(video_data_map))
                comments_extracted = len(comment_counts)
                views_extracted = len(view_counts)
                dates_extracted = len(upload_dates)
                logger.info(
                    "BitChute extraction quality for %s: videos=%d views=%d comments=%d dates=%d",
                    channel_url,
                    total_videos_considered,
                    views_extracted,
                    comments_extracted,
                    dates_extracted,
                )

                # --- Build channel data ---
                missing_fields: list[str] = []
                if subscriber_count is None:
                    missing_fields.append("subscriber_count")
                if not video_titles:
                    missing_fields.append("video_titles")
                if avg_views is None:
                    missing_fields.append("avg_views")
                if avg_comments is None:
                    missing_fields.append("avg_comments")

                self.require_scrape_quality(
                    channel_url=channel_url,
                    video_titles=video_titles,
                    avg_views=avg_views,
                    page_title=page_title,
                    current_url=page.url,
                    body_text=body_text,
                    response_status=response_status,
                )

                channel_data: dict[str, object] = {
                    "platform": "bitchute",
                    "channel_url": channel_url,
                    "name": name,
                    "description": description,
                    "subscriber_count": subscriber_count,
                    "avg_views": int(avg_views) if avg_views is not None else None,
                    "avg_comments": int(avg_comments) if avg_comments is not None else None,
                    "comment_tier": comment_tier,
                    "posts_per_week": posts_per_week,
                    "last_active_date": last_active.date().isoformat() if last_active else None,
                    "contact_info": contact_info,
                    "niche_tags": demographic["niche_tags"],
                    "video_titles": video_titles,
                    "is_55_plus": demographic["is_55_plus"],
                    "secondary_urls": external_links,
                }

                # --- Persist ---
                channel_id = await self.save_to_supabase(channel_data)
                if channel_id is not None:
                    reason_prefix = (
                        "reason=empty_channel_no_videos; terminal=false; retryable=false; detail=channel exists but has no videos"
                        if not video_titles
                        else None
                    )
                    warning = (
                        f"{reason_prefix}; Missing fields: {', '.join(missing_fields)}"
                        if reason_prefix and missing_fields
                        else reason_prefix
                        if reason_prefix
                        else f"reason=parse_partial_data; terminal=false; retryable=false; detail=Missing fields: {', '.join(missing_fields)}"
                        if missing_fields
                        else None
                    )
                    await self.log_scrape_attempt(channel_id, "success", warning)

                logger.info("BitChute scrape complete for %s (%s)", name, channel_url)
                logger.info(
                    "BitChute transfer estimate for %s: responses=%d bytes_est=%d",
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
            logger.error(
                "BitChute scrape failed for %s: %s",
                channel_url, exc, exc_info=True,
            )
            raise

    def _extract_name(self, soup, channel_url: str) -> str:
        """Extract channel name from DOM or meta tags."""
        name = ""
        name_el = soup.select_one("div.text-bold.text-h4")
        if name_el:
            name = name_el.get_text(strip=True)
        
        if not name:
            og_title = soup.find("meta", property="og:title")
            if og_title:
                name = og_title.get("content", "").strip()
        
        if not name:
            name = channel_url.rstrip("/").split("/")[-1]
        return name

    def _extract_subscribers(self, soup) -> int | None:
        """Extract subscriber count from the caption text."""
        subscriber_count: int | None = None
        sub_text_el = soup.select_one(".text-caption.text-grey-8")
        if sub_text_el:
            text = sub_text_el.get_text(strip=True)
            # text like "18.3K subscribers • 7,550 videos"
            parts = re.split(r"[^a-zA-Z\d\.\,KM\s]", text)
            for part in parts:
                part = part.strip()
                if "subscriber" in part.lower():
                    subscriber_count = self._parse_bitchute_count(part)
                    break
        return subscriber_count

    def _extract_description(self, soup) -> str:
        """Extract full description from DOM or meta fallback."""
        description = ""
        desc_el = soup.select_one("div.bc-text-break")
        if desc_el:
            description = desc_el.get_text(separator="\n", strip=True)
        
        # Fallback to meta description if DOM is empty or looks like a summary
        if not description or len(description) < 50:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                meta_content = meta_desc.get("content", "").strip()
                if len(meta_content) > len(description):
                    description = meta_content
        return description

    def _extract_external_links(self, soup) -> list[str]:
        """Extract all external http(s) links that aren't bitchute.com."""
        external_links: list[str] = []
        all_links = soup.select("a[href]")
        for link in all_links:
            href = link.get("href", "")
            if href.startswith("http") and "bitchute.com" not in href:
                external_links.append(href)
        return sorted(list(set(external_links)))

    async def _extract_comments_from_card(self, card) -> int | None:
        """Extract comment count from a BitChute video card using multiple fallbacks."""
        # Selector-first strategy: common Quasar and card metadata nodes.
        selectors = [
            ".video-card-comments",
            ".q-item__label--caption",
            ".video-card-info",
            "span",
        ]
        for sel in selectors:
            try:
                nodes = await card.locator(sel).all()
            except Exception:
                nodes = []
            for node in nodes:
                try:
                    text = (await node.inner_text()).strip().lower()
                except Exception:
                    continue
                if "comment" in text:
                    parsed = self._parse_bitchute_count(text)
                    if parsed is not None:
                        return parsed

        # Full-card regex fallback for patterns like:
        # "12 comments", "comment 12", or icon-label style text near numbers.
        try:
            card_text = (await card.inner_text()).strip().lower()
        except Exception:
            return None

        patterns = [
            r"([\d\.,]+)\s*([km])?\s+comments?\b",
            r"\bcomments?\s+([\d\.,]+)\s*([km])?",
        ]
        for pattern in patterns:
            match = re.search(pattern, card_text)
            if match:
                number = match.group(1)
                suffix = match.group(2) or ""
                return self._parse_bitchute_count(f"{number}{suffix}")

        return None

    def _extract_videos(self, soup) -> dict[str, dict[str, object]]:
        """Extract recent videos from modern channel-card markup."""
        video_data_map: dict[str, dict[str, object]] = {}
        video_cards = soup.select("#video-card")
        for card in video_cards[: self.VIDEO_COLLECTION_LIMIT]:
            link_el = card.select_one("a[href*='/video/']")
            if link_el is None:
                continue
            href = str(link_el.get("href") or "").strip()
            if "/video/" not in href:
                continue
            video_id = href.rstrip("/").split("/")[-1]
            if not video_id:
                continue

            title = ""
            title_el = card.select_one(".q-item__label.bc-text-break")
            if title_el is not None:
                title = title_el.get_text(strip=True)
            if not title:
                img_el = card.select_one(".q-img[aria-label]")
                if img_el is not None:
                    title = str(img_el.get("aria-label") or "").strip()

            views: int | None = None
            date_val: datetime | None = None
            for label in card.select(".q-item__label.q-item__label--caption.text-caption"):
                text = " ".join(label.get_text(" ", strip=True).split())
                if "view" in text.lower():
                    views = self._parse_bitchute_count(text)
                    # Example: "651 Views - 6 months ago" or "651 Views – 6 months ago"
                    date_match = re.search(r"(?:-|–|â€“)\s*(.+)$", text)
                    if date_match:
                        date_val = self._parse_relative_date(date_match.group(1))
                # Some cards show date in a separate caption line.
                if date_val is None and (
                    "ago" in text.lower()
                    or "yesterday" in text.lower()
                    or "published" in text.lower()
                    or "just now" in text.lower()
                ):
                    date_val = self._parse_relative_date(text)

            # Fallback: overlay chip format with visibility icon and numeric caption.
            if views is None:
                for icon in card.select(".q-chip .q-icon"):
                    icon_text = icon.get_text(strip=True).lower()
                    if icon_text != "visibility":
                        continue
                    chip = icon.find_parent(class_="q-chip")
                    if chip is None:
                        continue
                    value_el = chip.select_one(".text-caption")
                    if value_el is None:
                        continue
                    views = self._parse_bitchute_count(value_el.get_text(" ", strip=True))
                    if views is not None:
                        break

            video_data_map[video_id] = {
                "title": title or "Unknown Title",
                "views": views,
                "comments": None,
                "comments_source": None,
                "date": date_val,
                "url": self._to_absolute_url(href),
            }
        return video_data_map

    async def _collect_videos_with_scroll(self, page) -> dict[str, dict[str, object]]:
        """Collect a deeper recent-video window by repeatedly snapshotting page HTML."""
        collected: dict[str, dict[str, object]] = {}
        stagnant_rounds = 0
        max_rounds = 16

        for _ in range(max_rounds):
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            parsed = self._extract_videos(soup)
            before = len(collected)
            for video_id, payload in parsed.items():
                if video_id not in collected:
                    collected[video_id] = payload
            after = len(collected)

            if after >= self.VIDEO_COLLECTION_LIMIT:
                break

            if after == before:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= 3:
                break

            await page.mouse.wheel(0, 3200)
            await human_delay(1.2, 2.5)

        if len(collected) > self.VIDEO_COLLECTION_LIMIT:
            trimmed: dict[str, dict[str, object]] = {}
            for idx, (video_id, payload) in enumerate(collected.items()):
                if idx >= self.VIDEO_COLLECTION_LIMIT:
                    break
                trimmed[video_id] = payload
            return trimmed
        return collected

    async def _fetch_api_channel_fallback(
        self, context, channel_url: str
    ) -> dict[str, object] | None:
        """Fetch the legacy/API BitChute channel HTML as a static fallback."""
        api_url = self._api_channel_url(channel_url)
        if api_url is None:
            return None

        page = await context.new_page()
        try:
            await page.goto(api_url, wait_until="domcontentloaded", timeout=45000)
            await human_delay(1.0, 2.0)
            if not await wait_for_content(page, min_bytes=5000, timeout_s=10.0):
                return None
            soup = BeautifulSoup(await page.content(), "html.parser")
            return {
                "videos": self._extract_api_videos(soup),
                "description": self._extract_api_description(soup),
                "external_links": self._extract_external_links(soup),
            }
        except Exception as exc:
            logger.debug("BitChute: API fallback failed for %s: %s", api_url, exc)
            return None
        finally:
            await page.close()

    def _api_channel_url(self, channel_url: str) -> str | None:
        """Build the legacy/API BitChute channel URL for a channel page."""
        parts = [part for part in urlsplit(channel_url).path.split("/") if part]
        if len(parts) < 2 or parts[0] != "channel":
            return None
        return f"https://api.bitchute.com/channel/{parts[1]}/"

    def _extract_api_description(self, soup: BeautifulSoup) -> str:
        """Extract the longest bounded text block from a legacy/API channel page."""
        candidates: list[str] = []
        for selector in ["#channel-about", ".channel-about", ".channel-description", ".description"]:
            for node in soup.select(selector):
                text = node.get_text("\n", strip=True)
                if len(text) > 80:
                    candidates.append(text)
        meta = soup.find("meta", attrs={"name": "description"})
        if isinstance(meta, Tag):
            text = str(meta.get("content") or "").strip()
            if text:
                candidates.append(text)
        if not candidates:
            return ""
        return max(candidates, key=len)

    def _extract_api_videos(self, soup: BeautifulSoup) -> dict[str, dict[str, object]]:
        """Extract video rows from the legacy/API BitChute channel surface."""
        videos: dict[str, dict[str, object]] = {}
        for link in soup.select("a[href*='/video/']"):
            href = str(link.get("href") or "").strip()
            video_id = href.rstrip("/").split("/")[-1]
            if not video_id or video_id in videos:
                continue

            title = link.get_text(" ", strip=True)
            if not title or self._is_bad_video_title(title):
                continue

            container = self._bounded_video_container(link)
            text = container.get_text(" ", strip=True) if container is not None else title
            views = self._extract_api_video_views(link, container)
            date_val = self._extract_api_video_date(text)

            videos[video_id] = {
                "title": title,
                "views": views,
                "comments": None,
                "comments_source": None,
                "date": date_val,
                "url": self._to_absolute_url(href),
            }
            if len(videos) >= self.VIDEO_COLLECTION_LIMIT:
                break
        return videos

    def _bounded_video_container(self, link: Tag) -> Tag | None:
        """Return a small parent container for legacy/API video metadata."""
        for parent in link.parents:
            if not isinstance(parent, Tag):
                continue
            if parent.name in {"article", "li", "tr"}:
                return parent
            if parent.name == "div":
                video_links = parent.select("a[href*='/video/']")
                text_len = len(parent.get_text(" ", strip=True))
                if len(video_links) <= 2 and text_len <= 3000:
                    return parent
        return None

    def _extract_api_video_views(self, link: Tag, container: Tag | None) -> int | None:
        """Extract legacy/API view counts from link-adjacent metadata."""
        candidates: list[str] = []
        if container is not None:
            for anchor in container.select("a[href*='/video/']"):
                if anchor is link:
                    continue
                text = anchor.get_text(" ", strip=True)
                if re.fullmatch(r"[\d,.\s]+(?:[kmb])?\s+\d{1,2}:\d{2}(?::\d{2})?", text, re.I):
                    candidates.append(text.split()[0])
            text = container.get_text(" ", strip=True)
            match = re.search(r"\b(\d[\d,]*(?:\.\d+)?\s*[kmb]?)\s+views?\b", text, re.I)
            if match:
                candidates.append(match.group(1))
        for candidate in candidates:
            parsed = self._parse_bitchute_count(candidate)
            if parsed is not None:
                return parsed
        return None

    def _extract_api_video_date(self, text: str) -> datetime | None:
        """Extract absolute dates from bounded legacy/API video text."""
        match = re.search(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}\b",
            text,
            flags=re.I,
        )
        if match:
            return self._parse_absolute_date(match.group(0))
        return self._parse_bitchute_date(text)

    async def _open_videos_tab_if_available(self, page, channel_url: str) -> None:
        """Switch to the Videos tab when available to avoid featured-card duplicates."""
        selectors = [
            ".q-tab:has-text('Videos')",
            "text='Videos'",
            "[role='tab']:has-text('Videos')",
        ]
        for sel in selectors:
            try:
                tab = page.locator(sel).first
                if await tab.is_visible(timeout=2500):
                    await tab.click()
                    await human_delay(1.5, 3.0)
                    await page.wait_for_selector("#video-card, a[href*='/video/']", timeout=10000)
                    return
            except Exception:
                continue
        logger.debug("BitChute: Videos tab not found for %s", channel_url)

    def _to_absolute_url(self, href: str) -> str:
        """Normalize BitChute relative/absolute URLs."""
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return f"https://www.bitchute.com{href if href.startswith('/') else '/' + href}"

    def _merge_video_page_signals(
        self,
        item: dict[str, object],
        needs_comment: bool,
        needs_date: bool,
        comment_count: int | None,
        publish_date: datetime | None,
    ) -> None:
        """Merge fallback video-page signals into a video item."""
        if needs_comment and comment_count is not None:
            item["comments"] = comment_count
            item["comments_source"] = "video_page"
        if needs_date and publish_date is not None:
            item["date"] = publish_date

    async def _extract_video_page_signals(
        self, context, video_url: str
    ) -> tuple[int | None, datetime | None]:
        """Open a video page and extract comment count + publish date."""
        page = await context.new_page()
        try:
            await human_delay(2.0, 4.0)
            await page.goto(video_url, wait_until="domcontentloaded", timeout=90000)
            await human_delay(3.0, 5.0)
            await wait_for_content(page, min_bytes=5000, timeout_s=20.0)
            await page.mouse.wheel(0, 2800)
            await human_delay(2.0, 4.0)

            comment_count: int | None = None
            count_locator = page.locator("#comments-container .navigation .count .value").first
            if await count_locator.count() > 0:
                count_text = (await count_locator.inner_text()).strip()
                parsed = self._parse_bitchute_count(count_text)
                if parsed is not None:
                    comment_count = parsed

            comments_container = page.locator("#comments-container").first
            if await comments_container.count() > 0:
                comment_text = await comments_container.inner_text()
                reply_match = re.search(r"Reply[^\d]*(\d+)", comment_text)
                if comment_count is None and reply_match:
                    try:
                        comment_count = int(reply_match.group(1))
                    except ValueError:
                        comment_count = None

            publish_date: datetime | None = None
            for sel in [".q-item__label.q-item__label--caption.text-caption", "time"]:
                nodes = await page.locator(sel).all()
                for node in nodes:
                    text = (await node.inner_text()).strip()
                    parsed_date = self._parse_bitchute_date(text)
                    if parsed_date is not None:
                        publish_date = parsed_date
                        break
                if publish_date is not None:
                    break

            if publish_date is None:
                body_text = await page.locator("body").first.inner_text()
                date_match = re.search(
                    r"(\d+\s+(?:second|minute|hour|day|week|month|year|sec|min|hr|wk|mo|yr)s?\s+ago|yesterday|just now)",
                    body_text,
                    flags=re.IGNORECASE,
                )
                if date_match:
                    publish_date = self._parse_bitchute_date(date_match.group(1))

            return comment_count, publish_date
        except Exception as exc:
            logger.debug("BitChute: Could not extract video signals from %s: %s", video_url, exc)
            return None, None
        finally:
            await page.close()

    def _parse_bitchute_count(self, text: str) -> int | None:
        """Parse counts like '18.3K', '1,445', '12.9K views' with extreme resilience."""
        if not text:
            return None
        
        # Clean text: keep only digits, dots, and k/m
        clean_text = text.lower().strip()
        
        # Extract numeric-ish part using regex that finds numbers potentially followed by K or M
        match = re.search(r"([\d\.,]+)\s*([kmb])?", clean_text)
        if not match:
            return None
        
        try:
            # Remove commas from the numeric part
            num_str = match.group(1).replace(",", "")
            suffix = match.group(2)
            
            val = float(num_str)
            if suffix == "k":
                return int(val * 1000)
            if suffix == "m":
                return int(val * 1000000)
            if suffix == "b":
                return int(val * 1000000000)
            return int(val)
        except (ValueError, TypeError):
            return None

    def _parse_relative_date(self, text: str) -> datetime | None:
        """Parse '2 hours ago', '3 days ago', etc."""
        if not text:
            return None
        
        now = datetime.now()
        # Clean up icon labels and noise
        text = text.lower().replace("event", "").replace("published", "").strip()
        
        if "yesterday" in text:
            return now - timedelta(days=1)
        if "just now" in text or "seconds ago" in text:
            return now
        if "ago" not in text:
            return None
            
        match = re.search(
            r"(\d+)\s+("
            r"second|minute|hour|day|week|month|year|"
            r"sec|min|hr|wk|mo|yr"
            r")s?",
            text,
        )
        if not match:
            return None
            
        val = int(match.group(1))
        unit = match.group(2)
        
        if unit in {"second", "sec"}:
            return now - timedelta(seconds=val)
        if unit in {"minute", "min"}:
            return now - timedelta(minutes=val)
        if unit in {"hour", "hr"}:
            return now - timedelta(hours=val)
        if "day" in unit:
            return now - timedelta(days=val)
        if unit in {"week", "wk"}:
            return now - timedelta(weeks=val)
        if unit in {"month", "mo"}:
            return now - timedelta(days=val * 30)
        if unit in {"year", "yr"}:
            return now - timedelta(days=val * 365)
        
        return None

    def _parse_absolute_date(self, text: str) -> datetime | None:
        """Parse absolute dates used by legacy BitChute pages."""
        if not text:
            return None
        normalized = " ".join(text.strip().replace(",", ", ").split())
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        return None

    def _parse_bitchute_date(self, text: str) -> datetime | None:
        """Parse either relative or absolute BitChute date text."""
        return self._parse_relative_date(text) or self._parse_absolute_date(text)

    def _extract_name(self, soup: BeautifulSoup, channel_url: str) -> str:
        """Extract channel name from visible header, metadata, or URL fallback."""
        for selector in ["div.text-bold.text-h4", "h1", "[class*='channel'] h1"]:
            node = soup.select_one(selector)
            if node is not None:
                name = node.get_text(" ", strip=True)
                if name:
                    return name

        for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
            meta = soup.find("meta", attrs=attrs)
            if isinstance(meta, Tag):
                name = str(meta.get("content") or "").strip()
                if name:
                    return re.sub(r"\s*[-|]\s*BitChute\s*$", "", name).strip()

        return channel_url.rstrip("/").split("/")[-1]

    def _extract_subscribers(self, soup: BeautifulSoup) -> int | None:
        """Extract subscriber count from header captions or full-page text."""
        for selector in [
            ".text-caption.text-grey-8",
            "[class*='subscriber']",
            "[aria-label*='subscriber']",
            "[title*='subscriber']",
        ]:
            for node in soup.select(selector):
                candidates = [
                    node.get_text(" ", strip=True),
                    str(node.get("aria-label") or ""),
                    str(node.get("title") or ""),
                ]
                for text in candidates:
                    if "subscriber" in text.lower():
                        parsed = self._parse_bitchute_count(text)
                        if parsed is not None:
                            return parsed

        return None

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract full description from about text or metadata."""
        for selector in ["div.bc-text-break", "[class*='description']", "[class*='about']"]:
            node = soup.select_one(selector)
            if node is not None:
                text = node.get_text(separator="\n", strip=True)
                if text:
                    return text

        for attrs in ({"name": "description"}, {"property": "og:description"}):
            meta = soup.find("meta", attrs=attrs)
            if isinstance(meta, Tag):
                text = str(meta.get("content") or "").strip()
                if text:
                    return text
        return ""

    def _extract_external_links(self, soup: BeautifulSoup) -> list[str]:
        """Extract absolute external links from profile/about markup."""
        external_links: set[str] = set()
        for link in soup.select("a[href]"):
            href = str(link.get("href") or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
                continue
            absolute = urljoin(BITCHUTE_BASE_URL, href)
            if absolute.startswith("http") and "bitchute.com" not in absolute:
                external_links.add(absolute)
        return sorted(external_links)

    def _extract_videos(self, soup: BeautifulSoup) -> dict[str, dict[str, object]]:
        """Extract recent videos from several BitChute card variants."""
        video_data_map: dict[str, dict[str, object]] = {}
        cards = soup.select(
            "#video-card, .video-card, .q-card:has(a[href*='/video/']), "
            "article:has(a[href*='/video/']), li:has(a[href*='/video/'])"
        )
        if not cards:
            anchors = soup.select("a[href*='/video/']")
            cards = [
                anchor.find_parent(["article", "li", "div"]) or anchor
                for anchor in anchors
            ]

        for card in cards:
            if len(video_data_map) >= self.VIDEO_COLLECTION_LIMIT or not isinstance(card, Tag):
                break
            link_el = card.select_one("a[href*='/video/']")
            if link_el is None:
                continue
            href = str(link_el.get("href") or "").strip()
            if "/video/" not in href:
                continue
            video_id = href.rstrip("/").split("/")[-1]
            if not video_id or video_id in video_data_map:
                continue

            title = self._extract_video_title(card, link_el)
            views = self._extract_card_count(
                card,
                selectors=[
                    ".q-item__label.q-item__label--caption.text-caption",
                    ".video-card-info",
                    ".q-chip",
                    "[class*='view']",
                    "[aria-label*='view']",
                    "[title*='view']",
                ],
                label_pattern=r"(\d[\d,]*(?:\.\d+)?\s*[km]?)\s+views?\b",
                icon_name="visibility",
            )
            comments = self._extract_card_count(
                card,
                selectors=[
                    ".video-card-comments",
                    ".q-item__label--caption",
                    ".video-card-info",
                    ".q-chip",
                    "[class*='comment']",
                    "[aria-label*='comment']",
                    "[title*='comment']",
                ],
                label_pattern=r"(\d[\d,]*(?:\.\d+)?\s*[km]?)\s+comments?\b",
                icon_name="comment",
            )
            date_val = self._extract_card_date(card)

            video_data_map[video_id] = {
                "title": title or "Unknown Title",
                "views": views,
                "comments": comments,
                "comments_source": "card" if comments is not None else None,
                "date": date_val,
                "url": self._to_absolute_url(href),
            }
        return video_data_map

    def _extract_video_title(self, card: Tag, link_el: Tag) -> str:
        """Extract a video title from text nodes and attributes."""
        for attr in ["title", "aria-label"]:
            text = str(link_el.get(attr) or "").strip()
            if text and not self._is_bad_video_title(text):
                return text
        for selector in [
            ".q-item__label.bc-text-break",
            ".video-card-title",
            ".q-item__label",
            "a.text-bold",
            ".text-h6",
            "h3",
            "h2",
        ]:
            node = card.select_one(selector)
            if node is not None:
                text = str(node.get("title") or node.get_text(" ", strip=True)).strip()
                if text and "/video/" not in text and not self._is_bad_video_title(text):
                    return text
        for selector in [".q-img[aria-label]", "img[alt]"]:
            node = card.select_one(selector)
            if node is not None:
                text = str(node.get("aria-label") or node.get("alt") or "").strip()
                if text:
                    return text
        return str(link_el.get("title") or link_el.get_text(" ", strip=True)).strip()

    def _is_bad_video_title(self, title: str) -> bool:
        """Return True for overlay/metadata text that is not a real video title."""
        text = " ".join(title.lower().split())
        if not text:
            return True
        if text.startswith("visibility "):
            return True
        if re.fullmatch(r"[\d,.\skm:]+", text):
            return True
        if " views " in f" {text} " and len(text) < 40:
            return True
        return False

    def _extract_card_count(
        self,
        card: Tag,
        *,
        selectors: list[str],
        label_pattern: str,
        icon_name: str,
    ) -> int | None:
        """Extract view/comment counts from selected nodes and full card text."""
        for selector in selectors:
            for node in card.select(selector):
                node_context = " ".join(
                    [
                        str(node.get("class") or ""),
                        str(node.get("aria-label") or ""),
                        str(node.get("title") or ""),
                        node.get_text(" ", strip=True),
                    ]
                ).lower()
                has_label = (
                    "view" in node_context
                    if icon_name == "visibility"
                    else "comment" in node_context
                )
                has_icon = icon_name in node_context
                if not has_label and not has_icon:
                    continue
                candidates = [
                    node.get_text(" ", strip=True),
                    str(node.get("aria-label") or ""),
                    str(node.get("title") or ""),
                    str(node.get("data-value") or ""),
                ]
                for candidate in candidates:
                    if icon_name == "visibility" and "comment" in candidate.lower():
                        continue
                    parsed = self._parse_bitchute_count(candidate)
                    if parsed is not None:
                        return parsed

        match = re.search(label_pattern, card.get_text(" ", strip=True), flags=re.IGNORECASE)
        if match:
            return self._parse_bitchute_count(match.group(1))
        return None

    def _extract_card_date(self, card: Tag) -> datetime | None:
        """Extract relative publish date from card text or time tags."""
        for time_node in card.select("time"):
            for candidate in [
                str(time_node.get("datetime") or ""),
                str(time_node.get("title") or ""),
                time_node.get_text(" ", strip=True),
            ]:
                parsed = self._parse_bitchute_date(candidate)
                if parsed is not None:
                    return parsed

        text = card.get_text(" ", strip=True)
        match = re.search(
            r"(\d+\s+(?:second|minute|hour|day|week|month|year|sec|min|hr|wk|mo|yr)s?\s+ago|yesterday|just now)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return self._parse_bitchute_date(match.group(1))
        return None

    def _merge_video_maps(
        self,
        primary: dict[str, dict[str, object]],
        fallback: dict[str, dict[str, object]],
    ) -> dict[str, dict[str, object]]:
        """Merge parser passes without losing fields extracted by either pass."""
        merged = dict(primary)
        for video_id, fallback_item in fallback.items():
            existing = merged.get(video_id)
            if existing is None:
                merged[video_id] = fallback_item
                continue
            for key, value in fallback_item.items():
                existing_value = existing.get(key)
                should_replace_bad_title = (
                    key == "title"
                    and isinstance(existing_value, str)
                    and isinstance(value, str)
                    and self._is_bad_video_title(existing_value)
                    and not self._is_bad_video_title(value)
                )
                if should_replace_bad_title or existing_value in (None, "", "Unknown Title") and value not in (
                    None,
                    "",
                    "Unknown Title",
                ):
                    existing[key] = value
        return merged
