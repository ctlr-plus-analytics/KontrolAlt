import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

from tasks.discover_seed_expansion import (
    _canonicalize_supported_channel_url,
    _collect_candidate_urls,
)


def test_canonicalize_supported_channel_url_rumble_with_tracking_strips_noise() -> None:
    canonical, platform = _canonicalize_supported_channel_url(
        "http://www.rumble.com/c/Alpha/?utm_source=x&ref=abc"
    )
    assert canonical == "https://rumble.com/c/Alpha"
    assert platform == "rumble"


def test_canonicalize_supported_channel_url_bitchute_normalizes_host_and_slashes() -> None:
    canonical, platform = _canonicalize_supported_channel_url(
        "https://www.bitchute.com//channel/TestChan//?foo=1"
    )
    assert canonical == "https://bitchute.com/channel/TestChan"
    assert platform == "bitchute"


def test_collect_candidate_urls_extracts_supported_only() -> None:
    channel = {
        "video_titles": [
            "Guest on https://rumble.com/c/GoldTalk",
            "Ignore youtube https://youtube.com/@foo",
        ],
        "contact_info": [
            "https://www.bitchute.com/channel/SignalRoom/",
            "mailto:test@example.com",
        ],
        "description": "Also see https://rumble.com/user?channel=MacroView&utm=1",
    }

    candidates = _collect_candidate_urls(channel)

    assert ("https://rumble.com/c/GoldTalk", "rumble") in candidates
    assert ("https://rumble.com/user/GoldTalk", "rumble") in candidates
    assert ("https://bitchute.com/channel/SignalRoom", "bitchute") in candidates
    assert ("https://rumble.com/user?channel=MacroView", "rumble") in candidates
    assert len(candidates) == 4
