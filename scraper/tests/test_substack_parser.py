"""Tests for the browser+API Substack scraper."""

import inspect
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.substack import SubstackScraper, parse_count_text, parse_substack_datetime
from core.exceptions import ScraperClassifiedError


# ── parse_count_text ─────────────────────────────────────────────────────────

def test_parse_count_text_variants() -> None:
    assert parse_count_text("1,234") == 1234
    assert parse_count_text("12.5K subscribers") == 12500
    assert parse_count_text("4.1K+") == 4100
    assert parse_count_text("3M comments") == 3000000
    assert parse_count_text("402 views") == 402
    assert parse_count_text("unknown") is None
    assert parse_count_text("") is None


# ── parse_substack_datetime ──────────────────────────────────────────────────

def test_parse_substack_datetime_variants() -> None:
    assert parse_substack_datetime("2026-05-28T06:25:15.617Z") is not None
    assert parse_substack_datetime("2026-05-06T12:34:56Z") is not None
    assert parse_substack_datetime("May 18, 2026") == datetime(2026, 5, 18)
    assert parse_substack_datetime("2 days ago") is not None
    assert parse_substack_datetime("invalid-date") is None
    assert parse_substack_datetime("") is None


# ── URL helpers ──────────────────────────────────────────────────────────────

def test_channel_base_url_normalizes_handle_and_query() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    base = scraper._channel_base_url(
        "https://www.substack.com/@theconsciouslee/?utm_source=x"
    )
    assert base == "https://substack.com/@theconsciouslee"


def test_channel_base_url_returns_canonical_handle_url() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    assert (
        scraper._channel_base_url("https://substack.com/@havivgur")
        == "https://substack.com/@havivgur"
    )


def test_channel_base_url_rejects_invalid_shapes() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    with pytest.raises(ScraperClassifiedError):
        scraper._channel_base_url("https://substack.com/no-at-sign")


def test_extract_handle_strips_at_sign() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    assert scraper._extract_handle("https://substack.com/@havivgur/posts") == "havivgur"
    assert scraper._extract_handle("https://substack.com/@theconsciouslee/posts") == "theconsciouslee"


def test_handle_from_current_url_detects_redirect() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    # JS redirect fired — different handle in URL
    assert scraper._handle_from_current_url(
        "https://substack.com/@andysfight", "andyparker"
    ) == "andysfight"
    # No redirect — same handle
    assert scraper._handle_from_current_url(
        "https://substack.com/@andyparker", "andyparker"
    ) is None
    # Search page redirect — not a valid @-handle URL
    assert scraper._handle_from_current_url(
        "https://substack.com/search?query=andyparker", "andyparker"
    ) is None


# ── _filter_contact_info ─────────────────────────────────────────────────────

def test_filter_contact_info_removes_substack_domains() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    result = scraper._filter_contact_info([
        "https://twitter.com/havivgur",
        "https://substack.com/@havivgur",
        "https://www.substack.com/inbox",
    ])
    assert result == ["https://twitter.com/havivgur"]


def test_filter_contact_info_deduplicates_trailing_slash() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    result = scraper._filter_contact_info([
        "https://twitter.com/havivgur/",
        "https://twitter.com/havivgur",
        "https://TWITTER.com/havivgur",
    ])
    assert len(result) == 1


# ── _fetch_public_profile — page.evaluate() mocks ───────────────────────────

def _make_page_mock(evaluate_return_value):
    """Return a mock Playwright Page whose evaluate() returns the given value."""
    page = MagicMock()
    page.evaluate = AsyncMock(return_value=evaluate_return_value)
    return page


@pytest.mark.asyncio
async def test_fetch_public_profile_returns_parsed_dict() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    body = json.dumps({
        "id": 25948955,
        "name": "Haviv Rettig Gur",
        "bio": "Analyses of Israel and the Middle East.",
        "subscriberCount": "4.1K+",
        "userLinks": [
            {"url": "https://twitter.com/havivrettiggur", "type": "twitter"},
            {"url": "https://www.youtube.com/@AskHavivAnything", "type": "youtube"},
        ],
    })
    page = _make_page_mock({"status": 200, "body": body})

    result, bytes_read = await scraper._fetch_public_profile(page, "havivgur")
    assert result["id"] == 25948955
    assert result["name"] == "Haviv Rettig Gur"
    assert parse_count_text(result["subscriberCount"]) == 4100
    assert len(result["userLinks"]) == 2
    assert bytes_read > 0


@pytest.mark.asyncio
async def test_fetch_public_profile_raises_on_404() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    page = _make_page_mock({"status": 404, "body": '{"error":"not found"}'})

    with pytest.raises(ScraperClassifiedError) as exc_info:
        await scraper._fetch_public_profile(page, "nonexistent")
    assert exc_info.value.reason_code == "substack_profile_not_found"


@pytest.mark.asyncio
async def test_fetch_profile_posts_parses_metrics() -> None:
    scraper = SubstackScraper.__new__(SubstackScraper)
    scraper.API_POST_LIMIT = 3
    body = json.dumps({
        "posts": [
            {
                "canonical_url": "https://havivgur.substack.com/p/post-one",
                "title": "Post One",
                "reaction_count": 48,
                "comment_count": 2,
                "post_date": "2026-05-28T06:25:15.617Z",
                "type": "newsletter",
            },
            {
                "canonical_url": "https://havivgur.substack.com/p/post-two",
                "title": "Post Two",
                "reaction_count": 120,
                "comment_count": 15,
                "post_date": "2026-05-21T10:00:00.000Z",
                "type": "newsletter",
            },
            {
                "canonical_url": "https://havivgur.substack.com/p/post-three",
                "title": "Post Three",
                "reaction_count": 75,
                "comment_count": 8,
                "post_date": "2026-05-14T08:00:00.000Z",
                "type": "podcast",
            },
        ],
        "nextCursor": "abc",
    })
    page = _make_page_mock({"status": 200, "body": body})

    post_map, bytes_read = await scraper._fetch_profile_posts(page, 25948955, "havivgur")
    assert len(post_map) == 3

    first = post_map["/p/post-one"]
    assert first["title"] == "Post One"
    assert first["views"] == 48
    assert first["comments"] == 2
    assert isinstance(first["date"], datetime)
    assert bytes_read > 0


# ── scrape() source sanity ────────────────────────────────────────────────────

def test_scrape_does_not_open_post_enrichment_pages() -> None:
    """Verify scrape() never opens separate post-enrichment tabs."""
    source = inspect.getsource(SubstackScraper.scrape)
    # Exactly 1 guarded_goto: navigate to bare /@handle, which triggers JS redirect
    # and establishes CF clearance in a single navigation. No /posts nav needed.
    assert source.count("guarded_goto") == 1
    assert "new_page" in source       # one page is opened for CF clearance
    assert "post_enrichment" not in source


def test_scrape_uses_camoufox_browser() -> None:
    """Substack uses launch_browser (Camoufox) for CF clearance, not raw httpx."""
    source = inspect.getsource(SubstackScraper.scrape)
    assert "launch_browser" in source
    assert "httpx" not in source


def test_scrape_calls_apis_via_page_evaluate() -> None:
    """Profile and posts data are fetched via in-browser page.evaluate(), not DOM."""
    for method in (SubstackScraper._fetch_public_profile, SubstackScraper._fetch_profile_posts):
        source = inspect.getsource(method)
        assert "page.evaluate" in source
        assert "BeautifulSoup" not in source
        assert "select_one" not in source
