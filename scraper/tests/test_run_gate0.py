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
    _build_search_queries,
    _extract_channel_handle,
    _iter_scan_values,
    _run_serper_search_multi,
    _scan_channel_text_for_competitors,
    _scan_serper_results,
    _should_run_gate0_check,
)
from core.runtime_settings import Gate0CompetitorSetting

_COMPETITORS = (
    Gate0CompetitorSetting("Goldco", ("goldco.com",)),
    Gate0CompetitorSetting("Noble Gold", ("noblegold.com",)),
    Gate0CompetitorSetting("Birch Gold", ("birchgold.com",)),
    Gate0CompetitorSetting("Augusta Precious Metals", ("augustapreciousmetals.com",)),
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
        },
        _COMPETITORS,
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
        ],
        _COMPETITORS,
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
        ],
        _COMPETITORS,
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
        ],
        _COMPETITORS,
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


def test_iter_scan_values_includes_video_titles_name_and_url() -> None:
    values = _iter_scan_values(
        {
            "channel_url": "https://rumble.com/c/TestChannel",
            "name": "Test Channel",
            "contact_info": [],
            "secondary_urls": [],
            "description": "",
            "video_titles": ["Gold IRA Review with Goldco", "Interview ep 42"],
        }
    )

    assert "Test Channel" in values
    assert "https://rumble.com/c/TestChannel" in values
    assert "Gold IRA Review with Goldco" in values
    assert "Interview ep 42" in values


def test_local_scan_detects_competitor_in_video_title() -> None:
    brand, source_url = _scan_channel_text_for_competitors(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": [],
            "secondary_urls": [],
            "description": "",
            "video_titles": ["Protect your retirement — sponsored by goldco.com"],
        },
        _COMPETITORS,
    )

    assert brand == "goldco.com"


def test_extract_channel_handle_rumble_c_path() -> None:
    assert _extract_channel_handle("https://rumble.com/c/DanBongino") == "DanBongino"


def test_extract_channel_handle_rumble_user_path() -> None:
    assert _extract_channel_handle("https://rumble.com/user/SomeUser") == "SomeUser"


def test_extract_channel_handle_substack_at_form() -> None:
    assert _extract_channel_handle("https://substack.com/@johndoe") == "johndoe"


def test_extract_channel_handle_substack_subdomain() -> None:
    assert _extract_channel_handle("https://johndoe.substack.com") == "johndoe"


def test_extract_channel_handle_unknown_url_returns_none() -> None:
    assert _extract_channel_handle("https://youtube.com/c/SomeChannel") is None


def test_build_search_queries_includes_broad_per_competitor_and_affiliate() -> None:
    competitors = (
        Gate0CompetitorSetting("Goldco", ("goldco.com",)),
        Gate0CompetitorSetting("Birch Gold", ("birchgold.com",)),
    )
    queries = _build_search_queries("Dan Bongino", None, competitors)

    assert '"Dan Bongino" "gold IRA"' in queries
    assert '"Dan Bongino" "Goldco"' in queries
    assert '"Dan Bongino" "Birch Gold"' in queries
    assert 'site:goldco.com "Dan Bongino"' in queries
    assert 'site:birchgold.com "Dan Bongino"' in queries


def test_build_search_queries_includes_handle_variants_when_different() -> None:
    queries = _build_search_queries(
        "Dan Bongino Show",
        "DanBongino",
        (Gate0CompetitorSetting("Goldco", ("goldco.com",)),),
    )

    assert '"DanBongino" "gold IRA"' in queries
    assert '"DanBongino" "Goldco"' in queries
    assert 'site:goldco.com "DanBongino"' in queries


def test_build_search_queries_deduplicates_when_handle_equals_name() -> None:
    queries = _build_search_queries(
        "DanBongino",
        "DanBongino",
        (Gate0CompetitorSetting("Goldco", ("goldco.com",)),),
    )

    assert queries.count('"DanBongino" "gold IRA"') == 1


def test_build_search_queries_broad_first() -> None:
    queries = _build_search_queries(
        "Test Channel",
        None,
        (Gate0CompetitorSetting("Goldco", ("goldco.com",)),),
    )

    assert queries[0] == '"Test Channel" "gold IRA"'


def test_multi_query_serper_exits_on_first_hit(monkeypatch) -> None:
    calls: list[str] = []

    def fake_serper(query: str, competitors):
        calls.append(query)
        if "Goldco" in query:
            return "Goldco", "https://goldco.com/partner"
        return None, None

    monkeypatch.setattr("tasks.run_gate0._run_serper_search", fake_serper)

    brand, url, winning_query = _run_serper_search_multi(
        ['"TestChannel" "gold IRA"', '"TestChannel" "Goldco"', '"TestChannel" "Birch Gold"'],
        _COMPETITORS,
    )

    assert brand == "Goldco"
    assert url == "https://goldco.com/partner"
    assert winning_query == '"TestChannel" "Goldco"'
    assert len(calls) == 2


def test_multi_query_serper_returns_primary_query_when_all_clean(monkeypatch) -> None:
    monkeypatch.setattr(
        "tasks.run_gate0._run_serper_search", lambda q, c: (None, None)
    )

    brand, url, winning_query = _run_serper_search_multi(
        ['"TestChannel" "gold IRA"', '"TestChannel" "Goldco"'],
        _COMPETITORS,
    )

    assert brand is None
    assert url is None
    assert winning_query == '"TestChannel" "gold IRA"'
