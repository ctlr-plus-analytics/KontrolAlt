import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("SERP_API_KEY", "serper-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")

from models.channel import Platform
from services.channel_intake_service import (
    _canonicalize_supported_url,
    _name_score,
    _parse_bulk_urls,
)


def test_canonicalize_supported_url_rumble() -> None:
    url, platform, error = _canonicalize_supported_url(
        "http://www.rumble.com/c/TestChan/?utm=abc"
    )

    assert error is None
    assert url == "https://rumble.com/c/TestChan"
    assert platform == Platform.rumble


def test_canonicalize_supported_url_rejects_mismatched_platform() -> None:
    url, platform, error = _canonicalize_supported_url(
        "https://bitchute.com/channel/demo",
        expected_platform=Platform.rumble,
    )

    assert url is None
    assert platform is None
    assert error is not None


def test_parse_bulk_urls_supports_newline_and_commas() -> None:
    parsed = _parse_bulk_urls(
        "https://rumble.com/c/one,\nhttps://bitchute.com/channel/two\nhttps://rumble.com/c/three"
    )

    assert parsed == [
        "https://rumble.com/c/one",
        "https://bitchute.com/channel/two",
        "https://rumble.com/c/three",
    ]


def test_name_score_prefers_exact_match() -> None:
    exact = _name_score("Glenn Beck", "Glenn Beck")
    partial = _name_score("Glenn Beck", "Glenn Beck Interviews")

    assert exact == 1.0
    assert partial < exact
