import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.channel_urls import canonicalize_channel_url, extract_supported_channel_urls


def test_canonicalize_rumble_user_channel_path() -> None:
    candidate = canonicalize_channel_url("https://www.rumble.com/user/MacroAlpha/?ref=home")

    assert candidate is not None
    assert candidate.channel_url == "https://rumble.com/user/MacroAlpha"
    assert candidate.platform == "rumble"


def test_canonicalize_bitchute_channel_path() -> None:
    candidate = canonicalize_channel_url("https://bitchute.com/channel/SignalDesk/")

    assert candidate is not None
    assert candidate.channel_url == "https://bitchute.com/channel/SignalDesk"
    assert candidate.platform == "bitchute"


def test_canonicalize_rejects_bitchute_video_path() -> None:
    candidate = canonicalize_channel_url("https://bitchute.com/video/abcd/")

    assert candidate is None


def test_extract_bare_supported_urls_from_serp_text() -> None:
    candidates = extract_supported_channel_urls(
        "Results mention rumble.com/LibertyDesk, old.bitchute.com/channel/SignalDesk, and theconsciouslee.substack.com."
    )

    urls = {candidate.channel_url for candidate in candidates}
    assert "https://rumble.com/LibertyDesk" in urls
    assert "https://bitchute.com/channel/SignalDesk" in urls
    assert "https://substack.com/@theconsciouslee" in urls


def test_canonicalize_substack_handle_url() -> None:
    candidate = canonicalize_channel_url("https://substack.com/@theconsciouslee/?utm_source=feed")

    assert candidate is not None
    assert candidate.channel_url == "https://substack.com/@theconsciouslee"
    assert candidate.platform == "substack"
