import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from import_channel_names_serper import (  # noqa: E402
    _best_candidate,
    _extract_candidates_from_result,
    _split_seed_aliases,
    _strict_channel_candidate,
    CandidateRecord,
)


def test_split_seed_aliases_keeps_primary_phrase_and_soft_variants() -> None:
    aliases = _split_seed_aliases("VNN - Maria Zeee; Elijah Schaffer")

    assert aliases[0] == "VNN - Maria Zeee; Elijah Schaffer"
    assert "VNN - Maria Zeee" in aliases
    assert "Elijah Schaffer" in aliases


def test_strict_channel_candidate_rejects_rumble_root_slugs() -> None:
    assert _strict_channel_candidate("https://rumble.com/playlists") is None
    assert _strict_channel_candidate("https://rumble.com/c/PatriotUnderground") is not None


def test_extract_candidates_filters_generic_rumble_pages() -> None:
    item = {
        "link": "https://rumble.com/playlists",
        "title": "Playlists - Rumble",
        "snippet": "Browse playlists",
        "displayedLink": "rumble.com",
    }
    assert _extract_candidates_from_result(item) == []


def test_best_candidate_rejects_ambiguous_close_scores() -> None:
    candidates = [
        CandidateRecord(
            channel_url="https://rumble.com/c/example-a",
            platform="rumble",
            confidence=0.90,
            display_name="Example A",
            source="serper",
            query="q1",
        ),
        CandidateRecord(
            channel_url="https://rumble.com/c/example-b",
            platform="rumble",
            confidence=0.86,
            display_name="Example B",
            source="serper",
            query="q2",
        ),
    ]

    assert _best_candidate(candidates) is None
