import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

from tasks.run_gate0 import (
    _scan_channel_text_for_competitors,
    _scan_serper_results,
    _should_run_gate0_check,
)


def test_gate0_skips_recent_clean_channels() -> None:
    channel = {
        "gate0_status": "clean",
        "gate0_checked_at": (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).isoformat(),
    }

    should_run, reason = _should_run_gate0_check(channel)

    assert should_run is False
    assert reason == "clean channel checked within the last 7 days"


def test_gate0_manual_override_runs_dirty_channel() -> None:
    should_run, reason = _should_run_gate0_check(
        {"gate0_status": "dirty"},
        manual=True,
    )

    assert should_run is True
    assert reason is None


def test_local_scan_detects_competitor_before_serper() -> None:
    brand, source_url = _scan_channel_text_for_competitors(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": ["https://noblegold.com/partner"],
            "secondary_urls": [],
            "description": "",
        }
    )

    assert brand == "noblegold.com"
    assert source_url == "https://noblegold.com/partner"


def test_serper_scan_checks_top_result_links_and_text() -> None:
    brand, source_url = _scan_serper_results(
        [
            {
                "title": "Interview",
                "snippet": "Sponsor details",
                "link": "https://birchgold.com/show",
            }
        ]
    )

    assert brand == "birchgold.com"
    assert source_url == "https://birchgold.com/show"
