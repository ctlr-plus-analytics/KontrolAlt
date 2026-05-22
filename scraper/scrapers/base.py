"""Abstract base class for all scrapers."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import UUID

from patchright.async_api import Error as PlaywrightError, Page

from core.exceptions import ScraperBlockedError, ScraperClassifiedError
from core.supabase import get_supabase_client
from models import ChannelSnapshotData

logger = logging.getLogger(__name__)

_BLOCKED_MARKERS = (
    "checking your browser",
    "cloudflare",
    "cf-browser-verification",
    "challenge-platform",
    "attention required",
    "access denied",
    "captcha",
    "verify you are human",
    "just a moment",
)

_TERMINAL_MARKERS = {
    "not_found_404": (
        "404",
        "page not found",
        "this page is unavailable",
        "does not exist",
    ),
    "channel_deleted": (
        "channel has been deleted",
        "account deleted",
        "this channel is deleted",
        "deleted by user",
    ),
    "channel_banned_or_suspended": (
        "account suspended",
        "channel suspended",
        "account banned",
        "channel banned",
        "violates our community guidelines",
    ),
    "channel_unavailable": (
        "temporarily unavailable",
        "unavailable in your region",
        "this channel is unavailable",
    ),
}


class BaseScraper(ABC):
    """Base scraper defining the interface and shared methods.

    All platform-specific scrapers must inherit from this class and
    implement the ``scrape`` method.
    """

    def __init__(self) -> None:
        self.supabase = get_supabase_client()

    @abstractmethod
    async def scrape(self, channel_url: str) -> dict[str, object]:
        """Scrape a single channel and return structured data.

        Args:
            channel_url: Full URL of the channel to scrape.

        Returns:
            A dict containing scraped channel data.
        """
        ...

    async def save_to_supabase(self, data: dict[str, object]) -> UUID | None:
        """Upsert channel data and insert its daily snapshot.

        Args:
            data: Channel data dict. Must include ``channel_url``.

        Returns:
            The saved channel ID, or None if Supabase returned no row.
        """
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        data["has_been_scraped"] = True
        data["discovery_status"] = "scraped"
        result = (
            self.supabase.table("channels")
            .upsert(data, on_conflict="channel_url")
            .execute()
        )
        if not result.data:
            return None

        channel_id = UUID(str(result.data[0]["id"]))
        await self._save_snapshot(channel_id, data)
        return channel_id

    async def _save_snapshot(
        self, channel_id: UUID, data: dict[str, object]
    ) -> None:
        """Insert a channel snapshot into the channel_snapshots table.

        Args:
            channel_id: UUID of the channel.
            data: Dict with subscriber_count, avg_views, avg_comments.
        """
        snapshot = ChannelSnapshotData(
            channel_id=str(channel_id),
            scraped_at=datetime.now(timezone.utc).isoformat(),
            subscriber_count=data.get("subscriber_count"),
            avg_views=data.get("avg_views"),
            avg_comments=data.get("avg_comments"),
        )
        self.supabase.table("channel_snapshots").insert(
            snapshot.model_dump(mode="json")
        ).execute()
        logger.info("Snapshot saved for channel %s", channel_id)

    async def log_scrape_attempt(
        self,
        channel_id: UUID,
        status: str,
        error: str | None = None,
    ) -> None:
        """Log a scrape attempt to the scrape_logs table.

        Args:
            channel_id: UUID of the channel being scraped.
            status: Outcome status (success, blocked, retry, failed).
            error: Optional error message if the scrape failed.
        """
        log = {
            "channel_id": str(channel_id),
            "attempted_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "error_message": error,
        }
        self.supabase.table("scrape_logs").insert(log).execute()

    async def get_channel_id(self, channel_url: str) -> UUID | None:
        """Return the channel ID for an existing channel URL."""
        result = (
            self.supabase.table("channels")
            .select("id")
            .eq("channel_url", channel_url)
            .maybe_single()
            .execute()
        )
        if result.data is None:
            return None
        return UUID(str(result.data["id"]))

    async def ensure_not_blocked(self, page: Page, channel_url: str) -> None:
        """Raise when the current page appears to be an anti-bot challenge."""
        title = (await page.title() or "").lower()
        current_url = page.url.lower()
        body_text = ""

        try:
            html_content = await page.content()
            html_len = len(html_content)
            body = await page.query_selector("body")
            if body is not None:
                body_text = ((await body.text_content()) or "").lower()
        except PlaywrightError as exc:
            logger.debug("Could not inspect page body for %s: %s", channel_url, exc)
            html_len = 0

        combined = f"{title} {current_url} {body_text}"
        
        # If we successfully loaded a large DOM, the CF elements might be hidden but present.
        # Only check for blocking markers if the page content is suspiciously small.
        if html_len < 30000:
            for marker in _BLOCKED_MARKERS:
                if marker in combined:
                    raise ScraperBlockedError(
                        f"Blocked while scraping {channel_url}: marker={marker}"
                    )

    def classify_terminal_page_state(
        self,
        *,
        channel_url: str,
        page_title: str,
        current_url: str,
        body_text: str,
        response_status: int | None,
    ) -> None:
        """Raise classified terminal error when page signals non-recoverable state."""
        combined = f"{page_title} {current_url} {body_text}".lower()

        if response_status == 404:
            raise ScraperClassifiedError(
                "not_found_404",
                f"HTTP 404 for {channel_url}",
                terminal=True,
                retryable=False,
            )

        for reason_code, markers in _TERMINAL_MARKERS.items():
            for marker in markers:
                if marker in combined:
                    raise ScraperClassifiedError(
                        reason_code,
                        f"Matched marker '{marker}' for {channel_url}",
                        terminal=True,
                        retryable=False,
                    )

    def require_non_empty_videos(
        self,
        *,
        channel_url: str,
        video_titles: list[str],
        page_title: str,
        current_url: str,
        body_text: str,
        response_status: int | None,
    ) -> None:
        """Raise when no videos likely indicates page failure rather than empty channel."""
        if video_titles:
            return
        self.classify_terminal_page_state(
            channel_url=channel_url,
            page_title=page_title,
            current_url=current_url,
            body_text=body_text,
            response_status=response_status,
        )
        raise ScraperClassifiedError(
            "parse_no_videos",
            f"No videos extracted for {channel_url}",
            terminal=False,
            retryable=True,
        )

    def require_scrape_quality(
        self,
        *,
        channel_url: str,
        video_titles: list[str],
        avg_views: int | None,
        page_title: str,
        current_url: str,
        body_text: str,
        response_status: int | None,
    ) -> None:
        """Raise when parsed data is too incomplete to safely persist."""
        self.require_non_empty_videos(
            channel_url=channel_url,
            video_titles=video_titles,
            page_title=page_title,
            current_url=current_url,
            body_text=body_text,
            response_status=response_status,
        )
        if avg_views is None:
            raise ScraperClassifiedError(
                "parse_missing_avg_views",
                f"No view counts extracted for {channel_url}",
                terminal=False,
                retryable=True,
            )

    def compute_avg(self, values: list[float]) -> int | None:
        """Compute the median of a list of values and return as integer.

        Uses median instead of mean for robustness against outliers.

        Args:
            values: List of numeric values.

        Returns:
            The median value rounded to the nearest int, or None if the list is empty.
        """
        if not values:
            return None
        sorted_vals = sorted(values)
        mid = len(sorted_vals) // 2
        if len(sorted_vals) % 2 == 0:
            return int(round((sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0))
        return int(round(sorted_vals[mid]))

    def compute_posting_cadence(
        self, upload_dates: list[datetime]
    ) -> float | None:
        """Compute posts per week from a list of upload dates.

        Args:
            upload_dates: List of upload datetimes.

        Returns:
            Average posts per week, rounded to 2 decimal places, or None.
        """
        if len(upload_dates) < 2:
            return None
        sorted_dates = sorted(upload_dates)
        total_days = (sorted_dates[-1] - sorted_dates[0]).days
        if total_days == 0:
            return None
        return round(len(upload_dates) / (total_days / 7), 2)

