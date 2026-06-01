"""Substack scraper — Playwright Chromium for CF clearance, then two in-browser
API calls via page.evaluate() fetch.

Flow per channel:
  1. launch_browser() (Playwright Chromium) → navigate to /@handle/posts
       Establishes cf_clearance and session cookies.  Storage-state is
       persisted to disk so repeat scrapes of the same channel skip the
       Cloudflare challenge entirely.
  2. page.evaluate() → GET /api/v1/user/{handle}/public_profile
       Returns name, bio, subscriber count, userLinks (external social URLs).
  3. page.evaluate() → GET /api/v1/profile/posts?profile_user_id={id}&limit=3
       Returns latest posts with reaction_count, comment_count, post_date.

Why page.evaluate() instead of httpx:
  Raw httpx / context.request.get() both get CF 403 — Substack sits behind
  Cloudflare bot-management and requires a cf_clearance cookie that only a
  real browser can obtain by solving the JS challenge.  Fetch calls executed
  inside the browser page share its cookie jar and its proxy connection, so
  both CF auth and proxy routing work transparently.

Net cost vs. old DOM approach: 1 nav + 2 JSON fetches (was 5+ navs + DOM).
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError

from core.browser import (
    BrowserTelemetry,
    guarded_goto,
    launch_browser,
    wait_for_content,
)
from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from scrapers.base import BaseScraper
from utils.contact_extractor import extract_emails, extract_urls
from utils.keyword_matcher import compute_channel_demographic, compute_comment_tier

logger = logging.getLogger(__name__)

_SUBSTACK_BASE_URL = "https://substack.com"
_SUBSTACK_HANDLE_PATH_RE = re.compile(r"^/@[a-zA-Z0-9._-]+$")
_EXCLUDED_CONTACT_DOMAINS = {
    "substack.com",
    "www.substack.com",
    "enable-javascript.com",
    "www.enable-javascript.com",
}

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
    if "@" in stripped and not stripped.startswith("http"):
        return True
    hostname = (urlsplit(stripped).hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname in _SOCIAL_DOMAINS or any(
        hostname.endswith("." + d) for d in _SOCIAL_DOMAINS
    )

# Timeout for the initial page navigation.
_NAV_TIMEOUT_MS = 25_000
# Timeout waiting for the page body to grow past the CF challenge stub.
_CONTENT_WAIT_TIMEOUT_S = 15.0


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
            # Provide a year to avoid ambiguous-leap-day deprecation in Python 3.15+
            parsed = datetime.strptime(f"{value} {now.year}", f"{fmt} %Y")
            return parsed
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
    """Scraper for Substack publications.

    Uses a single Playwright Chromium navigation to establish Cloudflare
    clearance, then calls Substack's public JSON APIs via in-page fetch()
    to retrieve profile metadata and post metrics.
    """

    API_POST_LIMIT = 3
    POST_COLLECTION_LIMIT = 50
    DEMOGRAPHIC_TITLE_LIMIT = 20

    async def scrape(self, channel_url: str) -> dict[str, object]:
        try:
            stage_t0 = perf_counter()
            stage_marks: list[tuple[str, float]] = []

            channel_base_url = self._channel_base_url(channel_url)
            handle = self._extract_handle(channel_base_url)
            session_key = getattr(self, "_session_key", None) or channel_base_url

            telemetry = BrowserTelemetry()
            async with launch_browser(
                session_key=session_key, telemetry=telemetry
            ) as context:
                page = await context.new_page()

                # ── Step 1: navigate to /@handle ─────────────────────────────
                # The bare /@handle URL triggers Substack's client-side JS redirect,
                # resolving any username→@handle mismatches in one shot.
                # CF clearance is established here; /posts is not needed.
                await guarded_goto(
                    page,
                    f"{_SUBSTACK_BASE_URL}/@{handle}",
                    session_key=session_key,
                    wait_until="commit",
                    timeout=_NAV_TIMEOUT_MS,
                )
                content_ok = await wait_for_content(
                    page, timeout_s=_CONTENT_WAIT_TIMEOUT_S
                )
                if not content_ok:
                    raise ScraperClassifiedError(
                        "substack_cf_challenge",
                        f"Substack page never grew past CF stub for: @{handle}",
                        terminal=False,
                        retryable=True,
                    )

                # Wait for JS redirect to resolve; exit early once URL stabilises.
                # Substack's React app may redirect /@handle to /@canonical-handle.
                # Using wait_for_url avoids the full 2 s sleep when no redirect fires.
                _pre_redirect_url = page.url
                try:
                    await page.wait_for_url(
                        lambda url: url.rstrip("/") != _pre_redirect_url.rstrip("/"),
                        timeout=1500,
                    )
                except Exception:
                    pass  # URL already stable — no client-side redirect occurred
                current_url = page.url

                if "/search" in urlsplit(current_url).path:
                    raise ScraperClassifiedError(
                        "substack_handle_redirected_to_search",
                        f"Substack redirected @{handle} to search — handle does not exist",
                        terminal=True,
                        retryable=False,
                    )

                redirected_handle = self._handle_from_current_url(current_url, handle)
                if redirected_handle:
                    logger.info(
                        "Substack handle resolved via page redirect: @%s → @%s",
                        handle, redirected_handle,
                    )
                    handle = redirected_handle

                stage_marks.append(("nav", perf_counter() - stage_t0))

                # ── Step 2: public profile API ────────────────────────────────
                profile, profile_bytes = await self._fetch_public_profile(page, handle)
                stage_marks.append(("fetch_profile", perf_counter() - stage_t0))

                user_id: int | None = profile.get("id")
                if not user_id:
                    raise ScraperClassifiedError(
                        "substack_profile_not_found",
                        f"Substack public profile missing user ID for handle: {handle}",
                        terminal=True,
                        retryable=False,
                    )

                name = str(profile.get("name") or "").strip() or handle
                bio = str(profile.get("bio") or "").strip()

                _raw_sub_count = profile.get("subscriberCount")
                if _raw_sub_count is None:
                    raise ScraperClassifiedError(
                        "substack_see_subscribers_stub",
                        f"Substack profile has hidden subscriber count for: {channel_base_url}",
                        terminal=True,
                        retryable=False,
                    )
                subscriber_count = parse_count_text(str(_raw_sub_count))

                # ── Step 3: latest posts API ──────────────────────────────────
                post_data_map, posts_bytes = await self._fetch_profile_posts(
                    page, user_id, handle
                )
                stage_marks.append(("fetch_posts", perf_counter() - stage_t0))

            # ── Outside browser context ───────────────────────────────────────

            # Contact info from userLinks + bio text, split by type
            user_links: list[dict] = profile.get("userLinks") or []
            link_urls = [
                str(link.get("url") or "").strip()
                for link in user_links
                if link.get("url")
            ]
            all_links = self._filter_contact_info(
                sorted(set(link_urls + extract_emails(bio) + extract_urls(bio)))
            )
            contact_info = [v for v in all_links if _is_social_or_email(v)]
            secondary_urls = [v for v in all_links if not _is_social_or_email(v)]

            # Aggregate metrics
            post_titles = [
                str(item["title"])
                for item in post_data_map.values()
                if item.get("title")
            ][: self.POST_COLLECTION_LIMIT]
            view_counts = [
                float(item["views"])
                for item in post_data_map.values()
                if item.get("views") is not None
            ][: self.POST_COLLECTION_LIMIT]
            comment_counts = [
                float(item["comments"])
                for item in post_data_map.values()
                if item.get("comments") is not None
            ][: self.POST_COLLECTION_LIMIT]
            upload_dates = [
                item["date"]
                for item in post_data_map.values()
                if isinstance(item.get("date"), datetime)
            ][: self.POST_COLLECTION_LIMIT]

            avg_views = self.compute_avg(view_counts)
            avg_comments = self.compute_avg(comment_counts)
            posts_per_week = self.compute_posting_cadence(upload_dates) or 0.0
            last_active_date = max(upload_dates) if upload_dates else None
            comment_tier = compute_comment_tier(avg_comments)
            demographic = compute_channel_demographic(
                name, bio, post_titles[: self.DEMOGRAPHIC_TITLE_LIMIT]
            )

            resolved_channel_url = channel_base_url

            self.require_scrape_quality(
                channel_url=resolved_channel_url,
                video_titles=post_titles,
                subscriber_count=subscriber_count,
                avg_views=avg_views,
                avg_comments=avg_comments,
                posts_per_week=posts_per_week,
                last_active_date=last_active_date,
                contact_info=contact_info,
                secondary_urls=secondary_urls,
                page_title=name,
                current_url=resolved_channel_url,
                body_text=bio,
                response_status=200,
                allow_empty_channel=False,
            )

            channel_data: dict[str, object] = {
                "platform": "substack",
                "channel_url": resolved_channel_url,
                "name": name,
                "description": bio,
                "subscriber_count": subscriber_count,
                "avg_views": avg_views,
                "avg_comments": avg_comments,
                "comment_tier": comment_tier,
                "posts_per_week": posts_per_week,
                "last_active_date": (
                    last_active_date.date().isoformat() if last_active_date else None
                ),
                "contact_info": contact_info,
                "niche_tags": demographic["niche_tags"],
                "video_titles": post_titles,
                "recent_videos": [
                    {
                        "title": str(item.get("title") or "Unknown Title"),
                        "views": item.get("views"),
                        "comments": item.get("comments"),
                        "published_at": (
                            item["date"].isoformat()
                            if isinstance(item.get("date"), datetime)
                            else None
                        ),
                        "url": item.get("url"),
                    }
                    for item in post_data_map.values()
                ],
                "secondary_urls": secondary_urls,
            }

            channel_id = await self.save_to_supabase(channel_data)
            if channel_id:
                await self.log_scrape_attempt(channel_id, "success")

            stage_marks.append(("persist", perf_counter() - stage_t0))
            logger.info(
                "Substack scrape complete for %s: %s",
                resolved_channel_url,
                ", ".join(f"{s}={e:.2f}s" for s, e in stage_marks),
            )

            bytes_est = telemetry.total_bytes_est + profile_bytes + posts_bytes
            channel_data["_scrape_metrics"] = {
                "bytes_est": bytes_est,
                "responses": telemetry.response_count + 2,
                "geoip_enabled": telemetry.geoip_enabled,
                "comment_pages_attempted": 0,
                "comment_pages_blocked": 0,
                "comment_pages_parsed_success": 0,
            }
            return channel_data

        except (ScraperBlockedError, ScraperClassifiedError, PlaywrightError) as exc:
            logger.error("Substack scrape failed for %s: %s", channel_url, exc)
            raise

    # ── URL helpers ──────────────────────────────────────────────────────────

    def _channel_base_url(self, channel_url: str) -> str:
        parsed = urlsplit(channel_url.strip())
        scheme = parsed.scheme or "https"
        host = (parsed.netloc or "substack.com").lower()
        if host in {"www.substack.com", "substack.com"}:
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
        if not _SUBSTACK_HANDLE_PATH_RE.match(f"/{handle}"):
            raise ScraperClassifiedError(
                "unsupported_substack_url_shape",
                f"Unsupported Substack URL shape: {channel_url}",
                terminal=True,
                retryable=False,
            )
        return urlunsplit((scheme, host, f"/{handle}", "", ""))

    def _extract_handle(self, channel_base_url: str) -> str:
        """Return the bare handle slug (no leading @).

        e.g. ``https://substack.com/@havivgur/posts`` → ``"havivgur"``
        """
        for part in urlsplit(channel_base_url).path.split("/"):
            if part.startswith("@"):
                return part[1:]
        return ""

    # ── In-browser API fetchers ──────────────────────────────────────────────

    async def _fetch_public_profile(
        self, page, handle: str
    ) -> tuple[dict[str, object], int]:
        """Fetch /api/v1/user/{handle}/public_profile via in-page fetch().

        Runs inside the browser so CF cookies and proxy routing apply
        automatically.  Returns (profile_dict, bytes_estimated).
        """
        js = f"""
        async () => {{
            try {{
                const r = await fetch(
                    'https://substack.com/api/v1/user/{handle}/public_profile',
                    {{ headers: {{ 'Accept': 'application/json' }} }}
                );
                const body = await r.text();
                return {{ status: r.status, body: body }};
            }} catch (e) {{
                return {{ status: 0, body: '', error: String(e) }};
            }}
        }}
        """
        result: dict = await page.evaluate(js)
        status = result.get("status", 0)
        body = result.get("body", "")
        bytes_read = len(body.encode("utf-8"))

        if status == 0:
            raise ScraperBlockedError(
                f"Substack public profile fetch() threw a network error "
                f"for handle={handle}: {result.get('error', '')}"
            )
        if status == 404:
            raise ScraperClassifiedError(
                "substack_profile_not_found",
                f"Substack profile not found for handle: {handle}",
                terminal=True,
                retryable=False,
            )
        if status in {429, 503}:
            raise ScraperBlockedError(
                f"Substack public profile API rate-limited: handle={handle} "
                f"status={status}"
            )
        if status != 200:
            raise ScraperClassifiedError(
                "substack_api_error",
                f"Substack public profile API returned HTTP {status} for handle={handle}",
                terminal=False,
                retryable=True,
            )
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ScraperClassifiedError(
                "substack_api_error",
                f"Substack public profile API returned non-JSON for handle={handle}: {exc}",
                terminal=False,
                retryable=True,
            ) from exc

        return (data if isinstance(data, dict) else {}), bytes_read

    async def _fetch_profile_posts(
        self, page, user_id: int, handle: str
    ) -> tuple[dict[str, dict[str, object]], int]:
        """Fetch /api/v1/profile/posts via in-page fetch().

        Returns (post_map, bytes_estimated).  post_map is keyed by post path
        (e.g. "/p/post-slug").
        """
        url = (
            f"https://substack.com/api/v1/profile/posts"
            f"?profile_user_id={user_id}&limit={self.API_POST_LIMIT}"
        )
        js = f"""
        async () => {{
            try {{
                const r = await fetch(
                    '{url}',
                    {{ headers: {{ 'Accept': 'application/json' }} }}
                );
                const body = await r.text();
                return {{ status: r.status, body: body }};
            }} catch (e) {{
                return {{ status: 0, body: '', error: String(e) }};
            }}
        }}
        """
        result: dict = await page.evaluate(js)
        status = result.get("status", 0)
        body = result.get("body", "")
        bytes_read = len(body.encode("utf-8"))

        if status == 0:
            raise ScraperBlockedError(
                f"Substack profile posts fetch() threw a network error "
                f"for user_id={user_id}: {result.get('error', '')}"
            )
        if status in {429, 503}:
            raise ScraperBlockedError(
                f"Substack profile posts API rate-limited: user_id={user_id} status={status}"
            )
        if status != 200:
            raise ScraperClassifiedError(
                "substack_api_error",
                f"Substack profile posts API returned HTTP {status} for user_id={user_id}",
                terminal=False,
                retryable=True,
            )
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ScraperClassifiedError(
                "substack_api_error",
                f"Substack profile posts API returned non-JSON for user_id={user_id}: {exc}",
                terminal=False,
                retryable=True,
            ) from exc

        posts = data.get("posts") if isinstance(data, dict) else None
        if not isinstance(posts, list):
            logger.warning(
                "Substack profile posts API unexpected shape for user_id=%s: %r",
                user_id,
                type(data),
            )
            return {}, bytes_read

        post_map: dict[str, dict[str, object]] = {}
        for item in posts:
            if not isinstance(item, dict):
                continue
            post_url = str(item.get("canonical_url") or "").strip()
            if not post_url:
                continue
            post_id = urlsplit(post_url).path.rstrip("/")
            if not post_id or post_id in post_map:
                continue
            title = str(item.get("title") or "").strip() or "Unknown Title"
            reaction_count = item.get("reaction_count")
            views: int | None = (
                int(reaction_count)
                if isinstance(reaction_count, (int, float))
                else None
            )
            comment_count = item.get("comment_count")
            comments: int | None = (
                int(comment_count)
                if isinstance(comment_count, (int, float))
                else None
            )
            post_date = parse_substack_datetime(str(item.get("post_date") or ""))
            post_map[post_id] = {
                "title": title,
                "views": views,
                "comments": comments,
                "date": post_date,
                "url": post_url,
            }

        return post_map, bytes_read

    # ── Handle recovery ───────────────────────────────────────────────────────

    def _handle_from_current_url(self, current_url: str, original_handle: str) -> str | None:
        """Extract a different @-handle from the browser's current URL.

        Returns the new bare handle if page.url shows a redirect to a different
        handle, otherwise None (meaning no redirect happened yet).
        """
        try:
            new_handle = self._extract_handle(self._channel_base_url(current_url))
        except ScraperClassifiedError:
            return None
        return new_handle if new_handle and new_handle != original_handle else None

    # ── Contact deduplication ─────────────────────────────────────────────────

    def _filter_contact_info(self, values: list[str]) -> list[str]:
        filtered: list[str] = []
        seen_normalized: set[str] = set()
        for value in values:
            stripped = (value or "").strip()
            if not stripped:
                continue
            host = (urlsplit(stripped).hostname or "").lower()
            if host in _EXCLUDED_CONTACT_DOMAINS:
                continue
            normalized = stripped.lower().rstrip("/")
            if normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            filtered.append(stripped)
        return sorted(filtered)
