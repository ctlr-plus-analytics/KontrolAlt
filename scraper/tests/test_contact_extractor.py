import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.contact_extractor import extract_emails, extract_urls, is_competitor_url


def test_extract_urls_includes_bare_outbound_and_link_in_bio_domains() -> None:
    text = "Email me at a@example.com or visit linktr.ee/creator and beacons.ai/team."

    assert extract_emails(text) == ["a@example.com"]
    assert extract_urls(text) == [
        "https://beacons.ai/team",
        "https://linktr.ee/creator",
    ]


def test_extract_urls_filters_internal_platform_links() -> None:
    text = "https://rumble.com/c/test https://bitchute.com/channel/x example.com"

    assert extract_urls(text) == ["https://example.com"]


def test_competitor_url_detection() -> None:
    assert is_competitor_url("https://noblegold.com/promo")
    assert not is_competitor_url("https://example.com")
