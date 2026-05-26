"""Canary tests for Substack parser stability."""

import inspect
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.substack import SubstackScraper, parse_count_text, parse_substack_datetime


_REAL_PUBLICATION_DUMP = (
    Path(__file__).resolve().parents[1]
    / "scratch"
    / "substack_theconsciouslee_publication_dump.html"
)
_REAL_HOME_DUMP = (
    Path(__file__).resolve().parents[1]
    / "scratch"
    / "substack_theconsciouslee_home_dump.html"
)


def test_substack_scrape_does_not_hardcode_low_content_threshold() -> None:
    source = inspect.getsource(SubstackScraper.scrape)
    assert "min_bytes=5000" not in source


def test_parse_count_text_variants() -> None:
    assert parse_count_text("1,234") == 1234
    assert parse_count_text("12.5K subscribers") == 12500
    assert parse_count_text("3M comments") == 3000000
    assert parse_count_text("402 views") == 402
    assert parse_count_text("unknown") is None


def test_parse_substack_datetime_variants() -> None:
    assert parse_substack_datetime("2026-05-06T12:34:56Z") is not None
    assert parse_substack_datetime("May 18, 2026") == datetime(2026, 5, 18)
    assert parse_substack_datetime("2 days ago") is not None
    assert parse_substack_datetime("invalid-date") is None


def test_channel_base_url_normalizes_handle_and_query() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    base = scraper._channel_base_url("https://www.substack.com/@theconsciouslee/?utm_source=x")
    assert base == "https://substack.com/@theconsciouslee/posts"


def test_extract_name_description_and_subscribers() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    html = """
    <html><head>
      <meta property="og:site_name" content="The Consciouslee" />
      <meta name="description" content="Critical culture and media analysis." />
    </head>
    <body>
      <h1 data-testid="publication-name">The Consciouslee</h1>
      <div data-testid="subscriber-count">18.4K subscribers</div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert (
        scraper._extract_name(soup, "https://substack.com/@theconsciouslee", "")
        == "The Consciouslee"
    )
    assert scraper._extract_description(soup) == "Critical culture and media analysis."
    assert scraper._extract_subscribers(soup) == 18400


def test_extract_posts_from_card_selectors() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    scraper.POST_COLLECTION_LIMIT = 50
    scraper.POST_CARD_SELECTOR = "article"
    scraper.POST_LINK_SELECTOR = "a[href*='/p/']"
    scraper.POST_TITLE_SELECTOR = "h3"
    scraper.POST_DATE_SELECTOR = "time[datetime], time"

    html = """
    <article>
      <a href="/p/first-post"><h3>First Post</h3></a>
      <div data-testid="view-count">3.2K views</div>
      <div data-testid="comment-count">42 comments</div>
      <time datetime="2026-05-18T11:41:23Z">May 18, 2026</time>
    </article>
    """
    parsed = scraper._extract_posts(BeautifulSoup(html, "html.parser"), "https://substack.com/@theconsciouslee")
    assert "/p/first-post" in parsed
    item = parsed["/p/first-post"]
    assert item["title"] == "First Post"
    assert item["views"] == 3200
    assert item["comments"] == 42
    assert item["date"] is not None


def test_extract_post_metrics_from_like_and_comment_buttons() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    html = """
    <div class="reader2-post-container">
      <a class="reader2-inbox-post" href="https://example.substack.com/p/post-slug">
        <div class="meta-EgzBVA inbox-item-timestamp">May 18</div>
        <div class="reader2-post-title">A Post</div>
        <div class="rowUfi-owxpPL">
          <button aria-label="Like"><div>32</div></button>
          <button aria-label="Comment"><div>6</div></button>
        </div>
      </a>
    </div>
    """
    parsed = scraper._extract_posts(
        BeautifulSoup(html, "html.parser"),
        "https://substack.com/@theconsciouslee/posts",
    )
    assert "/p/post-slug" in parsed
    item = parsed["/p/post-slug"]
    assert item["views"] == 32
    assert item["comments"] == 6
    assert item["date"] is not None


def test_extract_post_metrics_do_not_confuse_restack_with_comments() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    scraper.POST_COLLECTION_LIMIT = 50
    scraper.POST_CARD_SELECTOR = "div.reader2-post-container"
    scraper.POST_LINK_SELECTOR = "a[href*='/p/']"
    scraper.POST_TITLE_SELECTOR = "div.reader2-post-title"
    scraper.POST_DATE_SELECTOR = "div.meta-EgzBVA.inbox-item-timestamp, time[datetime], time"

    html = """
    <div class="reader2-post-container">
      <a class="reader2-inbox-post" href="https://example.substack.com/p/post-slug">
        <div class="meta-EgzBVA inbox-item-timestamp">May 18</div>
        <div class="reader2-post-title">A Post</div>
        <div class="rowUfi-owxpPL">
          <button aria-label="Like"><div>32</div></button>
          <button aria-label="Comment"></button>
          <button aria-label="Restack"><div>6</div></button>
        </div>
      </a>
    </div>
    """
    parsed = scraper._extract_posts(
        BeautifulSoup(html, "html.parser"),
        "https://substack.com/@theconsciouslee/posts",
    )
    item = parsed["/p/post-slug"]
    assert item["views"] == 32
    assert item["comments"] == 0


def test_extract_post_page_signals_selectors_only() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    html = """
    <h1>First Post</h1>
    <div data-testid="view-count">1,234 views</div>
    <div data-testid="comment-count">18 comments</div>
    <time datetime="2026-05-18T11:41:23Z">May 18, 2026</time>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert scraper._extract_post_page_title(soup) == "First Post"
    assert scraper._extract_post_page_views(soup) == 1234
    assert scraper._extract_post_page_comments(soup) == 18
    assert scraper._extract_post_page_date(soup) is not None


def test_comment_count_does_not_use_body_text_fallback() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    soup = BeautifulSoup(
        '<section><div>There are 42 comments on this post</div></section>',
        "html.parser",
    )
    assert scraper._extract_post_page_comments(soup) is None


def test_extract_external_links_filters_substack_domains() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    html = """
    <a href="https://twitter.com/theconsciouslee">Twitter</a>
    <a href="https://substack.com/@theconsciouslee">Home</a>
    """
    links = scraper._extract_external_links(
        BeautifulSoup(html, "html.parser"),
        "https://substack.com/@theconsciouslee",
    )
    assert links == ["https://twitter.com/theconsciouslee"]


def test_real_publication_dump_extracts_core_metrics() -> None:
    if not _REAL_PUBLICATION_DUMP.exists():
        return

    scraper = SubstackScraper.__new__(SubstackScraper)
    soup = BeautifulSoup(_REAL_PUBLICATION_DUMP.read_text(encoding="utf-8"), "lxml")

    name = scraper._extract_name(soup, "https://substack.com/@theconsciouslee", "")
    description = scraper._extract_description(soup)
    subscribers = scraper._extract_subscribers(soup)
    posts = scraper._extract_posts(soup, "https://theconsciouslee.substack.com")

    assert name == "Education Is Elevation"
    assert len(description) > 40
    assert subscribers is not None and subscribers >= 1000
    assert len(posts) >= 5

    first = next(iter(posts.values()))
    assert first["title"] and first["title"] != "Unknown Title"
    assert first["views"] is not None
    assert first["comments"] is not None
    assert first["date"] is not None


def test_real_home_dump_extracts_profile_metrics() -> None:
    if not _REAL_HOME_DUMP.exists():
        return

    scraper = SubstackScraper.__new__(SubstackScraper)
    soup = BeautifulSoup(_REAL_HOME_DUMP.read_text(encoding="utf-8"), "lxml")

    name = scraper._extract_name(soup, "https://substack.com/@theconsciouslee", "")
    description = scraper._extract_description(soup)
    subscribers = scraper._extract_subscribers(soup)
    links = scraper._extract_external_links(soup, "https://substack.com/@theconsciouslee")

    assert name in {"The Conscious Lee", "Education Is Elevation"}
    assert len(description) > 40
    assert subscribers is not None and subscribers >= 1000
    assert all("substack.com" not in link for link in links)
