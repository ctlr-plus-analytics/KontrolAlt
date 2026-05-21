import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

from tasks.discover_keyword_expansion import (
    _canonicalize_channel_url,
    _query_for_keyword,
)


def test_canonicalize_channel_url_rumble_channel_path() -> None:
    canonical, platform = _canonicalize_channel_url(
        "https://www.rumble.com/c/MacroAlpha/?ref=home"
    )
    assert canonical == "https://rumble.com/c/MacroAlpha"
    assert platform == "rumble"


def test_canonicalize_channel_url_bitchute_channel_path() -> None:
    canonical, platform = _canonicalize_channel_url(
        "https://bitchute.com/channel/SignalDesk/"
    )
    assert canonical == "https://bitchute.com/channel/SignalDesk"
    assert platform == "bitchute"


def test_canonicalize_channel_url_rejects_non_channel_paths() -> None:
    canonical, platform = _canonicalize_channel_url("https://rumble.com/v6abcd-demo")
    assert canonical is None
    assert platform is None


def test_query_for_keyword_targets_platform_patterns() -> None:
    rumble_query = _query_for_keyword("gold ira", "rumble")
    bitchute_query = _query_for_keyword("gold ira", "bitchute")

    assert "site:rumble.com" in rumble_query
    assert '"/c/"' in rumble_query
    assert "site:bitchute.com" in bitchute_query
    assert '"/channel/"' in bitchute_query
