"""Canary tests for BitChute parser stability."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
from datetime import datetime, timedelta
import pytest
from bs4 import BeautifulSoup

from scrapers.bitchute import (
    BitChuteScraper,
    parse_count_text,
    parse_bitchute_views,
    parse_bitchute_datetime,
)


def test_parse_count_text() -> None:
    assert parse_count_text("18") == 18
    assert parse_count_text("102.8K subscribers") == 102800
    assert parse_count_text("3M comments") == 3000000
    assert parse_count_text("34.3K") == 34300
    assert parse_count_text("102,886") == 102886
    assert parse_count_text("(356)") == 356
    assert parse_count_text("Be the first to comment") is None


def test_parse_bitchute_views() -> None:
    assert parse_bitchute_views("34338 Views") == 34338
    assert parse_bitchute_views("34338 Views - 2 weeks ago") == 34338
    assert parse_bitchute_views("1.2K views") == 1200
    assert parse_bitchute_views("34.3K") == 34300


def test_parse_bitchute_datetime() -> None:
    assert parse_bitchute_datetime("yesterday") is not None
    assert parse_bitchute_datetime("just now") is not None
    assert parse_bitchute_datetime("2 weeks ago") is not None
    assert parse_bitchute_datetime("1 day ago") is not None
    assert parse_bitchute_datetime("May 25, 2026") == datetime(2026, 5, 25)


def test_extract_name() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    scraper.CHANNEL_NAME_SELECTOR = "span.q-btn__content span.block"
    
    html = """
    <span class="q-btn__content">
        <span class="block">TheCrowhouse</span>
    </span>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert scraper._extract_name(soup, "https://www.bitchute.com/channel/thecrowhouse", "Title") == "TheCrowhouse"


def test_extract_subscribers() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    scraper.CHANNEL_FOLLOWERS_SELECTOR = "div.text-caption.text-grey-8 span[style*=\"cursor: pointer\"]"
    
    html = """
    <div class="text-caption text-grey-8">
        <span style="cursor: pointer">102.8K subscribers</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert scraper._extract_subscribers(soup) == 102800


def test_extract_videos() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    scraper.VIDEO_CARD_SELECTOR = "a[href^=\"/video/\"]"
    scraper.VIDEO_LINK_SELECTOR = "a[href^=\"/video/\"]"
    scraper.VIDEO_TITLE_SELECTOR = "div.q-item__label.bc-text-break.ellipsis-2-lines.bc-responsive-font"
    scraper.VIDEO_VIEWS_SELECTOR = "div.q-chip__content div.text-caption"
    scraper.VIDEO_TIME_SELECTOR = "div.q-item__label.q-item__label--caption.text-caption"
    scraper.VIDEO_COLLECTION_LIMIT = 50
    
    html = """
    <div>
      <a href="/video/ABC123">
        <div class="q-item__label bc-text-break ellipsis-2-lines bc-responsive-font">Max Igan - Fair Food Forager</div>
        <div class="q-chip__content">
            <div class="text-caption">34.3K</div>
        </div>
        <div class="q-item__label q-item__label--caption text-caption">2 weeks ago</div>
      </a>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    parsed = scraper._extract_videos(soup)
    assert "ABC123" in parsed
    assert parsed["ABC123"]["title"] == "Max Igan - Fair Food Forager"
    assert parsed["ABC123"]["views"] == 34300
    assert parsed["ABC123"]["date"] is not None
    assert parsed["ABC123"]["url"] == "https://www.bitchute.com/video/ABC123"


def test_extract_videos_from_rendered_card_container() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    scraper.VIDEO_CARD_SELECTOR = "#video-card"
    scraper.VIDEO_LINK_SELECTOR = "#video-card a[href^=\"/video/\"]"
    scraper.VIDEO_TITLE_SELECTOR = "div.q-item__label.bc-text-break.ellipsis-2-lines.bc-responsive-font"
    scraper.VIDEO_VIEWS_SELECTOR = "div.q-chip__content div.text-caption"
    scraper.VIDEO_TIME_SELECTOR = "div.q-item__label.q-item__label--caption.text-caption"
    scraper.VIDEO_COLLECTION_LIMIT = 50

    html = """
    <div id="video-card">
      <a class="q-item" href="/video/kO4CknSw3I8Z">
        <div class="q-chip__content"><div class="text-caption">91</div></div>
        <div class="q-chip__content"><div class="text-caption">1:15:57</div></div>
      </a>
      <div class="q-card__section">
        <a href="/video/kO4CknSw3I8Z">
          <div class="q-item__label bc-text-break ellipsis-2-lines bc-responsive-font">
            Blackpilled - Jew behind the mask
          </div>
        </a>
        <div class="q-item__label q-item__label--caption text-caption">19 hours ago</div>
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    parsed = scraper._extract_videos(soup)
    assert parsed["kO4CknSw3I8Z"]["title"] == "Blackpilled - Jew behind the mask"
    assert parsed["kO4CknSw3I8Z"]["views"] == 91
    assert parsed["kO4CknSw3I8Z"]["date"] is not None


def test_merge_video_page_signals() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    item = {
        "title": "Test Title",
        "views": None,
        "comments": None,
        "date": None,
        "url": "https://www.bitchute.com/video/ABC123",
    }
    publish_date = datetime(2026, 5, 1, 12, 0, 0)
    scraper._merge_video_page_signals(
        item=item,
        needs_title=False,
        needs_views=True,
        needs_comment=True,
        needs_date=True,
        title=None,
        views=5000,
        comments=42,
        publish_date=publish_date,
    )
    assert item["views"] == 5000
    assert item["comments"] == 42
    assert item["date"] == publish_date


def test_merge_video_page_signals_replaces_overlay_title() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    item = {
        "title": "visibility 91 1:15:57",
        "views": 91,
        "comments": None,
        "date": None,
        "url": "https://www.bitchute.com/video/kO4CknSw3I8Z",
    }
    scraper._merge_video_page_signals(
        item=item,
        needs_title=False,
        needs_views=False,
        needs_comment=False,
        needs_date=False,
        title="Blackpilled - Jew behind the mask",
        views=None,
        comments=None,
        publish_date=None,
    )
    assert item["title"] == "Blackpilled - Jew behind the mask"



def test_last_comment_page_items() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    scraper.VIDEO_COLLECTION_LIMIT = 50
    scraper.COMMENT_VIDEO_PAGE_SAMPLE_LIMIT = 3
    video_map = {
        f"V{i}": {"url": f"https://www.bitchute.com/video/V{i}/"}
        for i in range(1, 8)
    }
    items = scraper._last_comment_page_items(video_map)
    assert len(items) == 3
    assert items[0]["url"].endswith("/V1/")
    assert items[2]["url"].endswith("/V3/")


def test_extract_video_page_comments_container_fallback() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    scraper.VIDEO_PAGE_COMMENT_SELECTOR = "#comments-container span.item.count span.value"
    html = """
    <div id="comments-container">
      <div>Send Refresh DYNAMIC ( 19 ) Newest Oldest Popular</div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    count, hit = scraper._extract_video_page_comments(soup)
    assert count == 19
    assert hit == "#comments-container text-count"


def test_extract_video_page_comments_no_comments_marker() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    scraper.VIDEO_PAGE_COMMENT_SELECTOR = "#comments-container span.item.count span.value"
    html = """
    <div id="comments-container">
      <div class="no-comments no-data">No comments</div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    count, hit = scraper._extract_video_page_comments(soup)
    assert count == 0
    assert hit in {"#comments-container", "div.no-comments.no-data"}


def test_extract_video_page_comments_navigation_beats_no_comments_marker() -> None:
    scraper = BitChuteScraper.__new__(BitChuteScraper)
    scraper.VIDEO_PAGE_COMMENT_SELECTOR = "#comments-container span.item.count span.value"
    html = """
    <div id="comments-container" class="jquery-comments">
      <div class="navigation">
        <span class="item count">(<span class="value">4</span><span class="caret"></span>)</span>
        <span class="item active">Newest</span>
      </div>
      <div id="comment-list" class="main">
        <div class="comment">First</div>
        <div class="comment">Second</div>
      </div>
      <div class="no-comments no-data">No comments</div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    count, hit = scraper._extract_video_page_comments(soup)
    assert count == 4
    assert hit == "#comments-container span.item.count span.value"
