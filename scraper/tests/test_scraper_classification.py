import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.exceptions import ScraperClassifiedError
from scrapers.base import BaseScraper


class _DummyScraper(BaseScraper):
    async def scrape(self, channel_url: str) -> dict[str, object]:
        return {"channel_url": channel_url}


def test_classify_terminal_page_state_404() -> None:
    scraper = _DummyScraper.__new__(_DummyScraper)
    with pytest.raises(ScraperClassifiedError) as exc_info:
        scraper.classify_terminal_page_state(
            channel_url="https://rumble.com/c/example",
            page_title="Not Found",
            current_url="https://rumble.com/c/example",
            body_text="",
            response_status=404,
        )
    assert exc_info.value.reason_code == "not_found_404"
    assert exc_info.value.terminal is True
    assert exc_info.value.retryable is False


def test_classify_terminal_page_state_banned_marker() -> None:
    scraper = _DummyScraper.__new__(_DummyScraper)
    with pytest.raises(ScraperClassifiedError) as exc_info:
        scraper.classify_terminal_page_state(
            channel_url="https://www.bitchute.com/channel/test",
            page_title="Channel Suspended",
            current_url="https://www.bitchute.com/channel/test",
            body_text="This account suspended for policy violations",
            response_status=200,
        )
    assert exc_info.value.reason_code == "channel_banned_or_suspended"


def test_classify_terminal_page_state_no_match() -> None:
    scraper = _DummyScraper.__new__(_DummyScraper)
    scraper.classify_terminal_page_state(
        channel_url="https://rumble.com/c/example",
        page_title="Example Channel",
        current_url="https://rumble.com/c/example",
        body_text="recent uploads and followers",
        response_status=200,
    )


def test_require_scrape_quality_rejects_empty_video_parse() -> None:
    scraper = _DummyScraper.__new__(_DummyScraper)
    with pytest.raises(ScraperClassifiedError) as exc_info:
        scraper.require_scrape_quality(
            channel_url="https://rumble.com/c/example",
            video_titles=[],
            subscriber_count=0,
            avg_views=None,
            avg_comments=0,
            posts_per_week=0.0,
            last_active_date=None,
            contact_info=["https://example.com"],
            secondary_urls=["https://example.com"],
            page_title="Example Channel",
            current_url="https://rumble.com/c/example",
            body_text="recent uploads and followers",
            response_status=200,
        )

    assert exc_info.value.reason_code == "parse_no_videos"
    assert exc_info.value.terminal is False
    assert exc_info.value.retryable is True


def test_require_scrape_quality_rejects_missing_views() -> None:
    scraper = _DummyScraper.__new__(_DummyScraper)
    with pytest.raises(ScraperClassifiedError) as exc_info:
        scraper.require_scrape_quality(
            channel_url="https://www.bitchute.com/channel/example",
            video_titles=["Example Video"],
            subscriber_count=0,
            avg_views=None,
            avg_comments=0,
            posts_per_week=0.0,
            last_active_date=None,
            contact_info=["https://example.com"],
            secondary_urls=["https://example.com"],
            page_title="Example Channel",
            current_url="https://www.bitchute.com/channel/example",
            body_text="example video 2 days ago",
            response_status=200,
        )

    assert exc_info.value.reason_code == "parse_missing_avg_views"


def test_require_scrape_quality_allows_explicit_empty_channel_with_zero_metrics() -> None:
    scraper = _DummyScraper.__new__(_DummyScraper)
    scraper.require_scrape_quality(
        channel_url="https://www.bitchute.com/channel/empty-example",
        video_titles=[],
        subscriber_count=0,
        avg_views=0,
        avg_comments=0,
        posts_per_week=0.0,
        last_active_date=None,
        contact_info=["https://example.com"],
        secondary_urls=["https://example.com"],
        page_title="Empty Channel",
        current_url="https://www.bitchute.com/channel/empty-example",
        body_text="0 videos no videos yet",
        response_status=200,
        allow_empty_channel=True,
    )


def test_require_scrape_quality_allows_empty_contact_info_and_secondary_urls() -> None:
    """Channels with no external links, emails, or social profiles should
    pass the quality gate — many legitimate channels have no outbound links."""
    scraper = _DummyScraper.__new__(_DummyScraper)
    scraper.require_scrape_quality(
        channel_url="https://www.bitchute.com/channel/example",
        video_titles=["Example Video"],
        subscriber_count=100,
        avg_views=500,
        avg_comments=10,
        posts_per_week=1.0,
        last_active_date="2026-05-01",
        contact_info=[],
        secondary_urls=[],
        page_title="Example Channel",
        current_url="https://www.bitchute.com/channel/example",
        body_text="example video 2 days ago",
        response_status=200,
    )
