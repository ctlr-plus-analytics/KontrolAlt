"""Canary tests for BitChute parser stability."""

from datetime import datetime

from scrapers.bitchute import BitChuteScraper


def test_extract_videos_parses_views_and_date_from_caption_line() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    html = """
    <div id="video-card">
      <a href="/video/ABC123">
        <div class="q-item__label bc-text-break">Sample Video</div>
        <div class="q-item__label q-item__label--caption text-caption">1,234 Views - 2 months ago</div>
      </a>
    </div>
    """
    from bs4 import BeautifulSoup

    parsed = scraper._extract_videos(BeautifulSoup(html, "html.parser"))
    assert "ABC123" in parsed
    assert parsed["ABC123"]["title"] == "Sample Video"
    assert parsed["ABC123"]["views"] == 1234
    assert parsed["ABC123"]["date"] is not None


def test_extract_videos_parses_views_from_visibility_chip() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    html = """
    <div id="video-card">
      <a href="/video/XYZ789">
        <div class="q-item__label bc-text-break">Overlay Views Video</div>
      </a>
      <div class="q-chip">
        <i class="q-icon">visibility</i>
        <div class="text-caption">3,063</div>
      </div>
      <div class="q-item__label q-item__label--caption text-caption">3 weeks ago</div>
    </div>
    """
    from bs4 import BeautifulSoup

    parsed = scraper._extract_videos(BeautifulSoup(html, "html.parser"))
    assert "XYZ789" in parsed
    assert parsed["XYZ789"]["views"] == 3063
    assert parsed["XYZ789"]["date"] is not None


def test_parse_relative_date_supports_short_units() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    assert scraper._parse_relative_date("3 hr ago") is not None
    assert scraper._parse_relative_date("15 min ago") is not None
    assert scraper._parse_relative_date("2 wk ago") is not None


def test_merge_video_page_signals_fills_missing_comment_and_date() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    item: dict[str, object] = {
        "comments": None,
        "comments_source": None,
        "date": None,
    }
    publish_date = datetime(2026, 5, 1, 12, 0, 0)

    scraper._merge_video_page_signals(
        item=item,
        needs_comment=True,
        needs_date=True,
        comment_count=7,
        publish_date=publish_date,
    )

    assert item["comments"] == 7
    assert item["comments_source"] == "video_page"
    assert item["date"] == publish_date


def test_merge_video_page_signals_preserves_existing_values_when_not_needed() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    original_date = datetime(2026, 4, 1, 9, 0, 0)
    item: dict[str, object] = {
        "comments": 11,
        "comments_source": "card",
        "date": original_date,
    }

    scraper._merge_video_page_signals(
        item=item,
        needs_comment=False,
        needs_date=False,
        comment_count=3,
        publish_date=datetime(2026, 5, 1, 12, 0, 0),
    )

    assert item["comments"] == 11
    assert item["comments_source"] == "card"
    assert item["date"] == original_date
