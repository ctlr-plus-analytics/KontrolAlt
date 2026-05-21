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
