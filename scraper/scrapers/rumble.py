"""RumbleScraper — full Patchright scraper for Rumble channel pages."""

import logging
import re
import asyncio
from datetime import datetime
from bs4 import BeautifulSoup

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


def parse_follower_count(text: str) -> int | None:
    """Parse '2.18M Followers' -> 2180000."""
    if not text:
        return None
    text = text.lower().replace("followers", "").replace(",", "").strip()
    try:
        if "k" in text:
            return int(float(text.replace("k", "")) * 1_000)
        elif "m" in text:
            return int(float(text.replace("m", "")) * 1_000_000)
        elif "b" in text:
            return int(float(text.replace("b", "")) * 1_000_000_000)
        return int(float(text))
    except (ValueError, TypeError):
        return None


def parse_count_text(text: str) -> int | None:
    """Parse generic count strings like '1,234', '12.5K', '3M comments'."""
    if not text:
        return None
    cleaned = text.lower().replace(",", "").strip()
    match = re.search(r"([\d\.]+)\s*([kmb])?", cleaned)
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


def parse_rumble_datetime(dt_str: str) -> datetime | None:
    """Parse Rumble datetime strings into naive datetime."""
    if not dt_str:
        return None
    try:
        dt_clean = re.sub(r"[+-]\d{2}:\d{2}$", "", dt_str)
        return datetime.fromisoformat(dt_clean)
    except (ValueError, TypeError):
        return None


class RumbleScraper(BaseScraper):
    """Scraper for Rumble channels using Patchright and BeautifulSoup.
    
    This scraper uses confirmed selectors from Rumble HTML dumps to accurately
    extract channel and video data.
    """

    async def scrape(self, channel_url: str) -> dict[str, object]:
        """Scrape a single Rumble channel.

        Extracts: channel name, subscriber count, last 20 videos
        (title, views, comments, date), social links, and contact info.

        Args:
            channel_url: Full URL of the Rumble channel.

        Returns:
            Scraped channel data dict with all computed fields.
        """
        try:
            telemetry = BrowserTelemetry()
            async with launch_browser(session_key=channel_url, telemetry=telemetry) as context:
                page = await context.new_page()

                # Navigate — use domcontentloaded then wait for real content
                response = await page.goto(
                    channel_url, wait_until="domcontentloaded", timeout=45000
                )
                await human_delay(3.0, 6.0)

                # Wait up to 20s for real content to appear (Cloudflare bypass check)
                content_ok = await wait_for_content(page, min_bytes=5000, timeout_s=20.0)
                if not content_ok:
                    logger.warning("Rumble: CF challenge not resolved, reloading %s", channel_url)
                    await page.reload(wait_until="domcontentloaded", timeout=45000)
                    await human_delay(5.0, 8.0)
                    content_ok = await wait_for_content(page, min_bytes=5000, timeout_s=20.0)

                await self.ensure_not_blocked(page, channel_url)

                if not content_ok:
                    raise ScraperBlockedError(f"Rumble page empty after reload: {channel_url}")

                # Use BeautifulSoup for faster and more reliable parsing of confirmed selectors
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

                # --- Extract channel name ---
                # Selector: .channel-header--title h1
                name = ""
                name_el = soup.select_one(".channel-header--title h1")
                if name_el:
                    name = name_el.get_text(strip=True)
                else:
                    # Fallback to page title
                    title = page_title
                    name = re.sub(r"\s*[-–]\s*Rumble\s*$", "", title).strip()

                if not name:
                    name = channel_url.rstrip("/").split("/")[-1]

                # --- Extract subscriber count ---
                # Selector: span inside .channel-header--title containing "Followers"
                subscriber_count: int | None = None
                title_div = soup.select_one(".channel-header--title")
                if title_div:
                    for span in title_div.find_all("span"):
                        text = span.get_text(strip=True)
                        if "Followers" in text or "followers" in text:
                            parsed_followers = parse_follower_count(text)
                            if parsed_followers is not None:
                                subscriber_count = parsed_followers
                                break

                # --- Extract video data (last 20) ---
                video_titles: list[str] = []
                view_counts: list[float] = []
                comment_counts: list[float] = []
                upload_dates: list[datetime] = []

                # Selector: div.videostream.thumbnail__grid--item
                video_cards = soup.select("div.videostream.thumbnail__grid--item")
                for card in video_cards[:20]:
                    # Title: h3.thumbnail__title[title]
                    title_el = card.select_one("h3.thumbnail__title")
                    title = ""
                    if title_el:
                        title = title_el.get("title") or title_el.get_text(strip=True)
                        if title:
                            video_titles.append(title)

                    # View count: span.videostream__views[data-views]
                    views_el = card.select_one("span.videostream__views[data-views]")
                    if views_el:
                        try:
                            view_counts.append(float(views_el["data-views"]))
                        except (ValueError, KeyError):
                            pass
                    else:
                        views_text_el = card.select_one("span.videostream__views")
                        if views_text_el:
                            parsed_views = parse_count_text(
                                views_text_el.get_text(strip=True)
                            )
                            if parsed_views is not None:
                                view_counts.append(float(parsed_views))

                    # Comment count: span.videostream__comments[title]
                    comments_el = card.select_one("span.videostream__comments[title]")
                    if comments_el:
                        try:
                            comment_counts.append(float(comments_el["title"].replace(",", "")))
                        except (ValueError, KeyError):
                            pass
                    else:
                        comments_text_el = card.select_one("span.videostream__comments")
                        if comments_text_el:
                            parsed_comments = parse_count_text(
                                comments_text_el.get_text(strip=True)
                            )
                            if parsed_comments is not None:
                                comment_counts.append(float(parsed_comments))

                    # Upload date: time.videostream__time[datetime]
                    time_el = card.select_one("time.videostream__time[datetime]")
                    if time_el:
                        dt_str = time_el.get("datetime", "")
                        parsed_dt = parse_rumble_datetime(dt_str)
                        if parsed_dt is not None:
                            upload_dates.append(parsed_dt)

                # --- Extract social links from main page ---
                # Selector: a.channel-subheader--socials-item[href]
                main_socials = []
                for a in soup.select("a.channel-subheader--socials-item[href]"):
                    href = a.get("href", "")
                    if href and href.startswith("http"):
                        main_socials.append(href)

                # --- Fetch About Page (for description and more socials) ---
                about_url = channel_url.rstrip("/") + "/about"
                description = ""
                about_socials = []

                try:
                    # We use a separate context for the about page
                    async with launch_browser(
                        session_key=channel_url,
                        telemetry=telemetry,
                    ) as about_context:
                        about_page = await about_context.new_page()
                        await about_page.goto(about_url, wait_until="domcontentloaded", timeout=30000)
                        await human_delay(2.0, 4.0)

                        # Check for content
                        about_content_ok = await wait_for_content(about_page, min_bytes=3000, timeout_s=10.0)
                        if about_content_ok:
                            about_html = await about_page.content()
                            about_soup = BeautifulSoup(about_html, "html.parser")

                            desc_el = about_soup.select_one(".channel-about--description")
                            if desc_el:
                                description = desc_el.get_text(separator="\n", strip=True)

                            for a in about_soup.select("a.channel-about--socials-item[href]"):
                                href = a.get("href", "")
                                if href and href.startswith("http"):
                                    about_socials.append(href)
                except Exception as e:
                    logger.warning("Rumble: Failed to fetch About page for %s: %s", channel_url, e)

                # Merge socials and extract contact info from all text
                all_secondary = sorted(set(main_socials + about_socials))
                page_text = soup.get_text()
                combined_text = description + "\n" + page_text
                emails = extract_emails(combined_text)
                urls = extract_urls(combined_text)
                contact_info = sorted(set(emails + urls + all_secondary))

                # --- Compute derived metrics ---
                avg_views = self.compute_avg(view_counts)
                avg_comments = self.compute_avg(comment_counts)
                comment_tier = compute_comment_tier(avg_comments)
                demographic = compute_channel_demographic(name, description, video_titles)
                posts_per_week = self.compute_posting_cadence(upload_dates)
                last_active_date = (
                    max(upload_dates).date() if upload_dates else None
                )
                logger.info(
                    "Rumble extraction quality for %s: cards=%d views=%d comments=%d dates=%d",
                    channel_url,
                    min(20, len(video_cards)),
                    len(view_counts),
                    len(comment_counts),
                    len(upload_dates),
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
                if posts_per_week is None:
                    missing_fields.append("posts_per_week")
                if last_active_date is None:
                    missing_fields.append("last_active_date")

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
                    "last_active_date": last_active_date.isoformat() if last_active_date else None,
                    "contact_info": contact_info,
                    "niche_tags": demographic["niche_tags"],
                    "video_titles": video_titles,
                    "is_55_plus": demographic["is_55_plus"],
                    "secondary_urls": all_secondary,
                }

                # --- Persist ---
                channel_id = await self.save_to_supabase(channel_data)
                if channel_id:
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
