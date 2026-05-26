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
from core.runtime_settings import Gate0CompetitorSetting, _parse_gate0_competitors


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


def test_serper_scan_returns_embedded_competitor_url_not_generic_result_url() -> None:
    brand, source_url = _scan_serper_results(
        [
            {
                "title": "Creator sponsor notes",
                "snippet": "Details are at noblegold.com/creator-offer today",
                "link": "https://rumble.com/c/generic-channel",
            }
        ]
    )

    assert brand == "noblegold.com"
    assert source_url == "https://noblegold.com/creator-offer"


def test_brand_only_match_does_not_return_generic_source_url() -> None:
    brand, source_url = _scan_serper_results(
        [
            {
                "title": "Creator talks about Noble Gold",
                "snippet": "Sponsor discussion without a concrete URL",
                "link": "https://rumble.com/c/generic-channel",
            }
        ]
    )

    assert brand == "Noble Gold"
    assert source_url is None


def test_competitor_domain_scan_uses_hostname_boundaries() -> None:
    brand, source_url = _scan_serper_results(
        [
            {
                "title": "Not a competitor",
                "snippet": "This mentions notnoblegold.com only",
                "link": "https://example.com",
            }
        ],
        (Gate0CompetitorSetting("Noble Gold", ("noblegold.com",)),),
    )

    assert brand is None
    assert source_url is None


def test_gate0_competitor_parser_filters_invalid_domains_and_generic_brands() -> None:
    competitors = _parse_gate0_competitors(
        [
            {"brand": "Gold", "domains": ["gold"]},
            {"brand": "Acme Metals", "domains": ["https://partners.acme.com/path"]},
        ]
    )

    assert competitors == (
        Gate0CompetitorSetting("Acme Metals", ("partners.acme.com",)),
    )
