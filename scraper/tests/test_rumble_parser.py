"""Canary tests for Rumble parser helpers."""

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.rumble import (
    RumbleScraper,
    parse_count_text,
    parse_follower_count,
    parse_rumble_datetime,
)


def test_rumble_scrape_does_not_hardcode_low_content_threshold() -> None:
    source = inspect.getsource(RumbleScraper.scrape)
    assert "min_bytes=5000" not in source


def test_parse_follower_count_m_suffix() -> None:
    assert parse_follower_count("3.64M Followers") == 3_640_000


def test_parse_follower_count_k_suffix() -> None:
    assert parse_follower_count("18.3K followers") == 18_300


def test_parse_follower_count_invalid_returns_none() -> None:
    assert parse_follower_count("unknown") is None


def test_parse_count_text_variants() -> None:
    assert parse_count_text("1,234") == 1234
    assert parse_count_text("12.5K comments") == 12500
    assert parse_count_text("3M") == 3000000
    assert parse_count_text("2.18M Followers") == 2180000
    assert parse_count_text("") is None


def test_parse_rumble_datetime() -> None:
    assert parse_rumble_datetime("2026-05-06T12:34:56-04:00") is not None
    assert parse_rumble_datetime("2026-05-06T12:34:56Z") is not None
    assert parse_rumble_datetime("2 days ago") is not None
    assert parse_rumble_datetime("May 18, 2026") is not None
    assert parse_rumble_datetime("2026-05-06T12:34:56") is not None
    assert parse_rumble_datetime("invalid-date") is None


def test_extract_home_header_name_and_followers_from_manual_selectors() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    html = """
    <div class="flex items-center justify-center md:justify-start mb-1">
      <h1>Graham Allen</h1><svg><title>Verified</title></svg>
    </div>
    <span class="text-fjord dark:text-cloud text-[12px] font-semibold flex items-center justify-center md:justify-start">
      <span>226K Followers</span>
    </span>
    """
    soup = BeautifulSoup(html, "html.parser")

    assert scraper._extract_name(soup, "https://rumble.com/c/grahamallen", "") == "Graham Allen"
    assert scraper._extract_subscribers(soup) == 226_000


def test_extract_videos_parses_modern_rumble_card() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    html = """
    <div class="videostream thumbnail__grid--item">
      <a class="title__link link" href="/v7a12nw-interview-with-true-gold-republic.html?e9s=src_v1_cbl">
        <h3 class="thumbnail__title line-clamp-2" title="Interview With True Gold Republic">Ignored</h3>
      </a>
      <span class="videostream__data--subitem videostream__views--count">&nbsp;30.3K&nbsp;</span>
      <time class="videostream__data--subitem videostream__time" datetime="2026-05-18T11:41:23-04:00">6 days ago</time>
    </div>
    """

    parsed = scraper._extract_videos(BeautifulSoup(html, "html.parser"))
    assert "v7a12nw-interview-with-true-gold-republic.html" in parsed
    item = parsed["v7a12nw-interview-with-true-gold-republic.html"]
    assert item["title"] == "Interview With True Gold Republic"
    assert item["views"] == 30300
    assert item["comments"] is None
    assert item["date"] is not None


def test_extract_videos_ignores_non_videos_tab_fallback_shapes() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    html = """
    <article>
      <a href="/v6xyz-fallback.html" title="Fallback Video"></a>
      <div>12.5K views</div>
      <div>7 comments</div>
      <div>3 days ago</div>
    </article>
    """

    parsed = scraper._extract_videos(BeautifulSoup(html, "html.parser"))
    assert parsed == {}


def test_extract_about_description_and_social_links_from_about_tab_only() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    html = """
    <div class="channel-about--description">
      <p>The OFFICIAL account for Graham Allen and home of The Graham Allen Show!</p>
    </div>
    <div class="channel-about--socials">
      <a class="channel-about--socials-item" href="https://twitter.com/grahamallen">
        <svg></svg>Twitter
      </a>
    </div>
    <a href="https://rumble.com/internal">Internal</a>
    """
    soup = BeautifulSoup(html, "html.parser")

    assert (
        scraper._extract_description(soup)
        == "The OFFICIAL account for Graham Allen and home of The Graham Allen Show!"
    )
    assert scraper._extract_external_links(soup, "https://rumble.com/c/grahamallen/about") == [
        "https://twitter.com/grahamallen"
    ]


def test_extract_next_page_url_normalizes_rumble_pagination() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    html = '<a href="?page=2" rel="next">Next</a>'

    assert (
        scraper._extract_next_page_url(
            BeautifulSoup(html, "html.parser"),
            "https://rumble.com/c/example",
        )
        == "https://rumble.com/c/example?page=2"
    )


def test_extract_video_page_metrics_from_manual_selectors() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    html = """
    <div class="video-header-container__title"><h1 class="h1">Interview With True Gold Republic</h1></div>
    <div class="media-description-info-stream-time"><div title="May 18, 2026">6 days ago</div></div>
    <div class="media-description-info-views">30.2K</div>
    <div class="comments-header"><h3 class="comment-count">18 Comments</h3></div>
    """
    soup = BeautifulSoup(html, "html.parser")

    assert scraper._extract_video_page_title(soup) == "Interview With True Gold Republic"
    assert scraper._extract_video_page_views(soup) == 30200
    assert scraper._extract_video_page_upload_date(soup) is not None
    count, source = scraper._extract_video_page_comments(soup)
    assert count == 18
    assert source == "div.comments-header > h3.comment-count"


def test_video_page_comments_do_not_use_body_text_fallback() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    soup = BeautifulSoup(
        '<section id="video-comments"><div>There are 42 comments on this post</div></section>',
        "html.parser",
    )
    count, source = scraper._extract_video_page_comments(soup)
    assert count is None
    assert source is None


def test_channel_tab_url_normalizes_input_tabs() -> None:
    scraper = RumbleScraper.__new__(RumbleScraper)
    base = scraper._channel_base_url("https://rumble.com/c/GrahamAllen/videos?x=1")
    assert base == "https://rumble.com/c/GrahamAllen"
    assert scraper._channel_tab_url(base, "about") == "https://rumble.com/c/GrahamAllen/about"


def test_last_comment_page_items_is_strictly_three_latest() -> None:
    scraper = RumbleScraper.__new__(RumbleScraper)
    scraper.VIDEO_COLLECTION_LIMIT = 50
    scraper.COMMENT_VIDEO_PAGE_SAMPLE_LIMIT = 3
    video_map = {str(i): {"url": f"https://rumble.com/v{i}.html"} for i in range(1, 7)}
    items = scraper._last_comment_page_items(video_map)
    assert len(items) == 3
    assert items[0]["url"].endswith("v1.html")
    assert items[2]["url"].endswith("v3.html")
