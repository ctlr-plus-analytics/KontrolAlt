import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.channel_urls import canonicalize_channel_url, extract_supported_channel_urls


def test_canonicalize_rumble_channel_path_strips_tracking() -> None:
    candidate = canonicalize_channel_url("http://www.rumble.com/c/Alpha/?utm_source=x")

    assert candidate is not None
    assert candidate.channel_url == "https://rumble.com/c/Alpha"
    assert candidate.platform == "rumble"


def test_canonicalize_rumble_custom_channel_url() -> None:
    candidate = canonicalize_channel_url("https://rumble.com/MacroAlpha")

    assert candidate is not None
    assert candidate.channel_url == "https://rumble.com/MacroAlpha"
    assert candidate.platform == "rumble"


def test_canonicalize_rejects_rumble_video_url() -> None:
    candidate = canonicalize_channel_url("https://rumble.com/v6abcd-demo")

    assert candidate is None


def test_canonicalize_bitchute_channel_normalizes_subdomain() -> None:
    candidate = canonicalize_channel_url("https://old.bitchute.com//channel/TestChan//?foo=1")

    assert candidate is not None
    assert candidate.channel_url == "https://bitchute.com/channel/TestChan"
    assert candidate.platform == "bitchute"


def test_extract_supported_channel_urls_does_not_invent_aliases() -> None:
    candidates = extract_supported_channel_urls(
        "Guest on https://rumble.com/c/GoldTalk and https://www.bitchute.com/channel/SignalRoom/"
    )

    urls = {candidate.channel_url for candidate in candidates}
    assert "https://rumble.com/c/GoldTalk" in urls
    assert "https://rumble.com/user/GoldTalk" not in urls
    assert "https://bitchute.com/channel/SignalRoom" in urls


def test_extract_supported_channel_urls_reads_contextual_platform_mentions() -> None:
    candidates = extract_supported_channel_urls(
        "Find us on Rumble channel LibertyDesk, BitChute profile SignalRoom, and Substack @theconsciouslee."
    )

    urls = {candidate.channel_url for candidate in candidates}
    assert "https://rumble.com/LibertyDesk" in urls
    assert "https://bitchute.com/channel/SignalRoom" in urls
    assert "https://substack.com/@theconsciouslee" in urls


def test_extract_supported_channel_urls_does_not_parse_rumble_channel_as_path() -> None:
    candidates = extract_supported_channel_urls(
        "Find us on Rumble channel LibertyDesk for new videos."
    )

    urls = {candidate.channel_url for candidate in candidates}
    assert "https://rumble.com/LibertyDesk" in urls
    assert "https://rumble.com/c/hannel" not in urls


def test_canonicalize_rejects_common_rumble_root_noise() -> None:
    urls = [
        "https://rumble.com/that",
        "https://rumble.com/for",
        "https://rumble.com/to",
        "https://rumble.com/Of",
        "https://rumble.com/DOWNLOAD",
    ]

    assert [canonicalize_channel_url(url) for url in urls] == [None] * len(urls)


def test_canonicalize_substack_subdomain_url() -> None:
    candidate = canonicalize_channel_url("https://theconsciouslee.substack.com/?utm_source=home")

    assert candidate is not None
    assert candidate.channel_url == "https://substack.com/@theconsciouslee"
    assert candidate.platform == "substack"
