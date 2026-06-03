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
    _W_DOMAIN_IN_CONTACT,
    _W_DOMAIN_IN_DESCRIPTION,
    _W_ONE_TITLE_NEUTRAL,
    _W_ONE_TITLE_PROMO,
    _W_SERPER_SINGLE,
    _W_SERPER_DOMAIN_LINK,
    _W_SERPER_DOMAIN_TEXT,
    _W_SERPER_BRAND_PROMO,
    _THRESHOLD_DIRTY,
    _THRESHOLD_REVIEW,
    ScanResult,
    _build_search_queries,
    _classify_confidence,
    _compound_confidence,
    _extract_channel_handle,
    _has_negative_context,
    _has_promo_context,
    _run_serper_search_multi,
    _scan_channel_local,
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


# ---------------------------------------------------------------------------
# _should_run_gate0_check
# ---------------------------------------------------------------------------

def test_gate0_skips_recent_clean_channels() -> None:
    channel = {
        "gate0_status": "clean",
        "gate0_checked_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
    }
    should_run, reason = _should_run_gate0_check(channel)
    assert should_run is False
    assert reason == "clean channel checked within the last 7 days"


def test_gate0_skips_needs_review_channels_automatically() -> None:
    should_run, reason = _should_run_gate0_check({"gate0_status": "needs_review"})
    assert should_run is False
    assert "needs_review" in reason


def test_gate0_skips_dirty_channels_automatically() -> None:
    should_run, reason = _should_run_gate0_check({"gate0_status": "dirty"})
    assert should_run is False
    assert "dirty" in reason


def test_gate0_manual_override_runs_needs_review_channel() -> None:
    should_run, reason = _should_run_gate0_check({"gate0_status": "needs_review"}, manual=True)
    assert should_run is True
    assert reason is None


def test_gate0_manual_override_runs_dirty_channel() -> None:
    should_run, reason = _should_run_gate0_check({"gate0_status": "dirty"}, manual=True)
    assert should_run is True
    assert reason is None


# ---------------------------------------------------------------------------
# _compound_confidence and _classify_confidence
# ---------------------------------------------------------------------------

def test_compound_confidence_single_signal() -> None:
    assert _compound_confidence([0.97]) == 0.97


def test_compound_confidence_two_independent_signals() -> None:
    result = _compound_confidence([0.85, 0.45])
    assert abs(result - (1 - 0.15 * 0.55)) < 1e-9


def test_compound_confidence_empty_returns_zero() -> None:
    assert _compound_confidence([]) == 0.0


def test_classify_dirty() -> None:
    assert _classify_confidence(0.97) == "dirty"
    assert _classify_confidence(0.95) == "dirty"


def test_classify_needs_review() -> None:
    assert _classify_confidence(0.85) == "needs_review"
    assert _classify_confidence(0.80) == "needs_review"


def test_classify_clean() -> None:
    assert _classify_confidence(0.79) == "clean"
    assert _classify_confidence(0.0) == "clean"


# ---------------------------------------------------------------------------
# Context detection
# ---------------------------------------------------------------------------

def test_has_promo_context_detects_sponsor_near_brand() -> None:
    assert _has_promo_context("This video is sponsored by Goldco today", "Goldco")


def test_has_promo_context_false_when_no_promo_words() -> None:
    assert not _has_promo_context("I left Goldco last year", "Goldco")


def test_has_negative_context_detects_scam_near_brand() -> None:
    assert _has_negative_context("Goldco is a scam, avoid them", "Goldco")


def test_has_negative_context_false_when_no_negative_words() -> None:
    assert not _has_negative_context("I use Goldco for my IRA", "Goldco")


# ---------------------------------------------------------------------------
# _scan_channel_local
# ---------------------------------------------------------------------------

def test_local_scan_domain_in_contact_is_auto_dirty() -> None:
    result = _scan_channel_local(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": ["https://noblegold.com/partner"],
            "secondary_urls": [],
            "description": "",
        },
        _COMPETITORS,
    )
    assert result.flagged_brand == "noblegold.com"
    assert result.source_url == "https://noblegold.com/partner"
    assert result.confidence >= _THRESHOLD_DIRTY


def test_local_scan_single_neutral_title_is_below_threshold() -> None:
    result = _scan_channel_local(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": [],
            "secondary_urls": [],
            "description": "",
            "video_titles": ["Talking about Goldco and gold IRAs"],
        },
        _COMPETITORS,
    )
    # Single neutral video title should fall below both thresholds.
    assert result.confidence == _W_ONE_TITLE_NEUTRAL
    assert _classify_confidence(result.confidence) == "clean"


def test_local_scan_domain_in_description_neutral_is_clean() -> None:
    # A neutral domain mention in a description (no promo language) is informational,
    # not an affiliation signal — should score below the needs_review threshold.
    result = _scan_channel_local(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": [],
            "secondary_urls": [],
            "description": "Visit goldco.com for more information on gold IRAs.",
        },
        _COMPETITORS,
    )
    assert result.confidence == _W_DOMAIN_IN_DESCRIPTION
    assert _classify_confidence(result.confidence) == "clean"
    # Signal is recorded even if below threshold — source_url should point to the domain.
    assert result.source_url and "goldco" in result.source_url


def test_local_scan_negative_context_suppresses_description_match() -> None:
    result = _scan_channel_local(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": [],
            "secondary_urls": [],
            "description": "goldco.com is a scam — avoid them at all costs.",
        },
        _COMPETITORS,
    )
    # Negative context suppresses the domain match; result should be clean.
    assert _classify_confidence(result.confidence) == "clean"


def test_local_scan_promo_title_raises_confidence_above_neutral() -> None:
    result_promo = _scan_channel_local(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": [],
            "secondary_urls": [],
            "description": "",
            "video_titles": ["Use my link to get a free kit from Goldco today"],
        },
        _COMPETITORS,
    )
    result_neutral = _scan_channel_local(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": [],
            "secondary_urls": [],
            "description": "",
            "video_titles": ["Talking about Goldco"],
        },
        _COMPETITORS,
    )
    assert result_promo.confidence > result_neutral.confidence
    assert result_promo.confidence == _W_ONE_TITLE_PROMO
    # Video title matches should report "Channel video titles" as source.
    assert result_promo.source_url == "Channel video titles"
    assert result_neutral.source_url == "Channel video titles"


def test_local_scan_returns_empty_result_when_no_signals() -> None:
    result = _scan_channel_local(
        {
            "channel_url": "https://rumble.com/c/source",
            "contact_info": [],
            "secondary_urls": [],
            "description": "I talk about history.",
        },
        _COMPETITORS,
    )
    assert result.flagged_brand is None
    assert result.confidence == 0.0
    assert result.signals == []


# ---------------------------------------------------------------------------
# _scan_serper_results
# ---------------------------------------------------------------------------

def test_serper_scan_detects_domain_in_link_for_site_query() -> None:
    brand, source_url, weight = _scan_serper_results(
        [{"title": "Interview", "snippet": "Sponsor details", "link": "https://birchgold.com/show"}],
        _COMPETITORS,
        is_site_query=True,
    )
    assert brand == "birchgold.com"
    assert source_url == "https://birchgold.com/show"
    assert weight == _W_SERPER_DOMAIN_LINK


def test_serper_scan_domain_in_link_suppressed_for_non_site_query() -> None:
    # Competitor homepage appearing in a brand-name query is background noise, not evidence.
    brand, source_url, weight = _scan_serper_results(
        [{"title": "Augusta Precious Metals | Gold IRA", "snippet": "Leading gold IRA company.", "link": "https://www.augustapreciousmetals.com/"}],
        _COMPETITORS,
        is_site_query=False,
    )
    assert brand is None
    assert source_url is None
    assert weight == 0.0


def test_serper_scan_returns_embedded_url_not_result_link() -> None:
    brand, source_url, weight = _scan_serper_results(
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
    assert weight == _W_SERPER_DOMAIN_TEXT


def test_serper_brand_only_match_uses_result_link_as_source() -> None:
    brand, source_url, weight = _scan_serper_results(
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
    assert source_url == "https://rumble.com/c/generic-channel"
    assert weight == _W_SERPER_BRAND_PROMO


def test_serper_brand_match_with_empty_link_returns_none_source() -> None:
    brand, source_url, weight = _scan_serper_results(
        [
            {
                "title": "Creator talks about Noble Gold",
                "snippet": "Sponsor discussion",
                "link": "",
            }
        ],
        _COMPETITORS,
    )
    assert brand == "Noble Gold"
    assert source_url is None
    assert weight == _W_SERPER_BRAND_PROMO


def test_serper_hostname_boundary_prevents_false_match() -> None:
    brand, source_url, weight = _scan_serper_results(
        [{"title": "Not a competitor", "snippet": "notnoblegold.com only", "link": "https://example.com"}],
        (Gate0CompetitorSetting("Noble Gold", ("noblegold.com",)),),
    )
    assert brand is None
    assert source_url is None
    assert weight == 0.0


def test_serper_scan_channel_name_gate_suppresses_unrelated_result() -> None:
    # Augusta's homepage appears for any 'Augusta' brand search but its snippet
    # won't mention the specific channel — should be suppressed.
    brand, source_url, weight = _scan_serper_results(
        [
            {
                "title": "Augusta Precious Metals | Gold IRA",
                "snippet": "Augusta Precious Metals is a leading gold IRA provider.",
                "link": "https://www.augustapreciousmetals.com/",
            }
        ],
        _COMPETITORS,
        channel_identifiers=frozenset({"america mission inc."}),
        is_site_query=False,
    )
    assert brand is None
    assert source_url is None
    assert weight == 0.0


def test_serper_scan_channel_name_gate_passes_when_channel_mentioned() -> None:
    # An article that genuinely co-mentions the channel and competitor passes the gate.
    brand, source_url, weight = _scan_serper_results(
        [
            {
                "title": "America Mission Inc. sponsored by Augusta Precious Metals",
                "snippet": "America Mission Inc. is a partner and affiliate of Augusta.",
                "link": "https://example.com/article",
            }
        ],
        _COMPETITORS,
        channel_identifiers=frozenset({"america mission inc."}),
        is_site_query=False,
    )
    assert brand == "Augusta Precious Metals"
    assert weight == _W_SERPER_BRAND_PROMO


def test_serper_scan_domain_in_link_negative_context_suppressed() -> None:
    # A site: result that carries negative language should not count as evidence.
    brand, source_url, weight = _scan_serper_results(
        [
            {
                "title": "Why We Avoid Augusta Precious Metals",
                "snippet": "This page warns about Augusta's scam practices.",
                "link": "https://www.augustapreciousmetals.com/warning",
            }
        ],
        _COMPETITORS,
        is_site_query=True,
    )
    assert brand is None
    assert weight == 0.0


def test_serper_scan_suppresses_brand_with_negative_context() -> None:
    brand, source_url, weight = _scan_serper_results(
        [
            {
                "title": "Goldco review — is it a scam?",
                "snippet": "We warn you to avoid Goldco and similar companies.",
                "link": "https://example.com/review",
            }
        ],
        _COMPETITORS,
    )
    assert brand is None
    assert source_url is None
    assert weight == 0.0


def test_serper_scan_suppresses_brand_without_promo_context() -> None:
    brand, source_url, weight = _scan_serper_results(
        [
            {
                "title": "Channel discusses Goldco",
                "snippet": "A channel that mentions Goldco in passing",
                "link": "https://example.com/article",
            }
        ],
        _COMPETITORS,
    )
    assert brand is None
    assert source_url is None
    assert weight == 0.0


# ---------------------------------------------------------------------------
# _run_serper_search_multi
# ---------------------------------------------------------------------------

def test_multi_query_serper_records_first_hit_as_winning(monkeypatch) -> None:
    """The winning brand/url/query come from the first query that produced a hit."""

    def fake_serper(query, competitors, **_):
        if "Goldco" in query:
            return "Goldco", "https://goldco.com/partner", _W_SERPER_DOMAIN_LINK
        return None, None, 0.0

    monkeypatch.setattr("tasks.run_gate0._run_serper_search", fake_serper)

    brand, url, winning_query, confidence = _run_serper_search_multi(
        ['"TestChannel" "gold IRA"', '"TestChannel" "Goldco"', '"TestChannel" "Birch Gold"'],
        _COMPETITORS,
    )

    assert brand == "Goldco"
    assert url == "https://goldco.com/partner"
    assert winning_query == '"TestChannel" "Goldco"'
    assert confidence > 0.0


def test_multi_query_serper_returns_zero_confidence_when_all_clean(monkeypatch) -> None:
    monkeypatch.setattr("tasks.run_gate0._run_serper_search", lambda q, c, **_: (None, None, 0.0))

    brand, url, winning_query, confidence = _run_serper_search_multi(
        ['"TestChannel" "gold IRA"', '"TestChannel" "Goldco"'],
        _COMPETITORS,
    )

    assert brand is None
    assert url is None
    assert confidence == 0.0


def test_multi_query_serper_compounds_independent_hits(monkeypatch) -> None:
    """Two hits from different source URLs compound to the correct joint confidence."""
    responses = iter([
        ("Goldco", "https://goldco.com/partners/creator", _W_SERPER_DOMAIN_LINK),
        ("Goldco", "https://some-review-site.com/goldco", _W_SERPER_DOMAIN_TEXT),
    ])
    monkeypatch.setattr("tasks.run_gate0._run_serper_search", lambda q, c, **_: next(responses))

    _, _, _, confidence = _run_serper_search_multi(
        ['"TestChannel" "Goldco" sponsor', 'site:goldco.com "TestChannel"'],
        _COMPETITORS,
    )

    expected = _compound_confidence([_W_SERPER_DOMAIN_LINK, _W_SERPER_DOMAIN_TEXT])
    assert abs(confidence - expected) < 1e-9


def test_multi_query_serper_deduplicates_same_url(monkeypatch) -> None:
    """The same source URL returned by two different queries is only counted once."""
    monkeypatch.setattr(
        "tasks.run_gate0._run_serper_search",
        lambda q, c, **_: ("Goldco", "https://goldco.com/partners", _W_SERPER_DOMAIN_LINK),
    )

    _, _, _, confidence = _run_serper_search_multi(
        ['"TestChannel" "Goldco" sponsor', 'site:goldco.com "TestChannel"'],
        _COMPETITORS,
    )

    # Only one unique URL — should compound a single weight, not two.
    assert abs(confidence - _W_SERPER_DOMAIN_LINK) < 1e-9


def test_multi_query_site_query_flag_set_correctly(monkeypatch) -> None:
    """site: queries must be detected and is_site_query=True passed to _run_serper_search."""
    seen_flags: list[bool] = []

    def capture_site_flag(query, competitors, *, channel_identifiers=frozenset(), is_site_query=False, **_):
        seen_flags.append(is_site_query)
        return None, None, 0.0

    monkeypatch.setattr("tasks.run_gate0._run_serper_search", capture_site_flag)

    _run_serper_search_multi(
        ['"TestChannel" "Goldco" sponsor', 'site:goldco.com "TestChannel"', '"TestChannel" "Goldco"'],
        _COMPETITORS,
    )

    assert seen_flags[0] is False   # affiliation query
    assert seen_flags[1] is True    # site: query
    assert seen_flags[2] is False   # broad query


# ---------------------------------------------------------------------------
# _extract_channel_handle
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# _build_search_queries
# ---------------------------------------------------------------------------

def test_build_search_queries_contains_affiliation_and_site_queries() -> None:
    competitors = (
        Gate0CompetitorSetting("Goldco", ("goldco.com",)),
        Gate0CompetitorSetting("Birch Gold", ("birchgold.com",)),
    )
    queries = _build_search_queries("Dan Bongino", None, competitors)

    assert any("Goldco" in q and "sponsor" in q for q in queries)
    assert any("site:goldco.com" in q for q in queries)
    assert any("site:birchgold.com" in q for q in queries)
    assert any('"Dan Bongino" "gold IRA"' == q for q in queries)


def test_build_search_queries_gold_ira_is_last_resort() -> None:
    competitors = (Gate0CompetitorSetting("Goldco", ("goldco.com",)),)
    queries = _build_search_queries("Test Channel", None, competitors)

    gold_ira_idx = next(i for i, q in enumerate(queries) if "gold IRA" in q)
    # At least one affiliation query must come before the broad gold IRA query.
    assert gold_ira_idx > 0


def test_build_search_queries_includes_handle_variants_when_different() -> None:
    queries = _build_search_queries(
        "Dan Bongino Show",
        "DanBongino",
        (Gate0CompetitorSetting("Goldco", ("goldco.com",)),),
    )
    assert any('"DanBongino"' in q and "sponsor" in q for q in queries)
    assert any("site:goldco.com" in q and '"DanBongino"' in q for q in queries)


def test_build_search_queries_deduplicates_when_handle_equals_name() -> None:
    queries = _build_search_queries(
        "DanBongino",
        "DanBongino",
        (Gate0CompetitorSetting("Goldco", ("goldco.com",)),),
    )
    assert queries.count('"DanBongino" "gold IRA"') == 1


# ---------------------------------------------------------------------------
# Confidence compounding integration
# ---------------------------------------------------------------------------

def test_weak_local_plus_serper_hit_stays_below_dirty() -> None:
    # Single neutral title (0.35) + single Serper hit (0.45): should NOT reach dirty.
    combined = _compound_confidence([_W_ONE_TITLE_NEUTRAL, _W_SERPER_SINGLE])
    assert _classify_confidence(combined) in ("clean", "needs_review")
    assert combined < _THRESHOLD_DIRTY


def test_description_domain_plus_serper_domain_text_reaches_needs_review() -> None:
    # Neutral domain in description (0.60) + Serper domain-text hit (0.55): needs_review.
    # Neither alone crosses the threshold; together they do.
    combined = _compound_confidence([_W_DOMAIN_IN_DESCRIPTION, _W_SERPER_DOMAIN_TEXT])
    assert _classify_confidence(combined) in ("needs_review", "dirty")


def test_domain_in_contact_alone_is_dirty() -> None:
    combined = _compound_confidence([_W_DOMAIN_IN_CONTACT])
    assert _classify_confidence(combined) == "dirty"
