"""Canary tests for Rumble parser helpers."""

from scrapers.rumble import (
    RumbleScraper,
    parse_count_text,
    parse_follower_count,
    parse_rumble_datetime,
)


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
    assert parse_rumble_datetime("2026-05-06T12:34:56") is not None
    assert parse_rumble_datetime("invalid-date") is None


def test_extract_videos_parses_modern_rumble_card() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    html = """
    <div class="videostream thumbnail__grid--item">
      <a href="/v6abc-example-video.html">
        <h3 class="thumbnail__title" title="Example Video">Ignored</h3>
      </a>
      <span class="videostream__views" data-views="1234">1.2K views</span>
      <span class="videostream__comments" title="56">56 comments</span>
      <time class="videostream__time" datetime="2026-05-06T12:34:56-04:00"></time>
    </div>
    """

    parsed = scraper._extract_videos(BeautifulSoup(html, "html.parser"))
    assert "v6abc-example-video.html" in parsed
    assert parsed["v6abc-example-video.html"]["title"] == "Example Video"
    assert parsed["v6abc-example-video.html"]["views"] == 1234
    assert parsed["v6abc-example-video.html"]["comments"] == 56
    assert parsed["v6abc-example-video.html"]["date"] is not None


def test_extract_videos_falls_back_to_text_labels() -> None:
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
    assert parsed["v6xyz-fallback.html"]["views"] == 12500
    assert parsed["v6xyz-fallback.html"]["comments"] == 7
    assert parsed["v6xyz-fallback.html"]["date"] is not None


def test_extract_videos_ignores_non_video_nav_links() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    html = """
    <nav>
      <a href="/videos">Videos</a>
      <a href="/viewer-license">License</a>
    </nav>
    <article>
      <a href="/v6xyz-real-video.html" title="Real Video"></a>
      <div>1,000 views</div>
    </article>
    """

    parsed = scraper._extract_videos(BeautifulSoup(html, "html.parser"))
    assert list(parsed) == ["v6xyz-real-video.html"]


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


def test_extract_page_count_ignores_unlabeled_numeric_nodes() -> None:
    from bs4 import BeautifulSoup

    scraper = RumbleScraper.__new__(RumbleScraper)
    soup = BeautifulSoup('<span class="duration">12:45</span>', "html.parser")

    assert (
        scraper._extract_page_count(
            soup=soup,
            selectors=["span"],
            metric_label="view",
            label_pattern=r"(\d[\d,]*)\s+views?\b",
        )
        is None
    )
