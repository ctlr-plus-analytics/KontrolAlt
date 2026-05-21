"""Canary tests for Rumble parser helpers."""

from scrapers.rumble import (
    parse_count_text,
    parse_follower_count,
    parse_rumble_datetime,
)


def test_parse_follower_count_m_suffix() -> None:
    assert parse_follower_count("3.64M Followers") == 3_640_000


def test_parse_follower_count_k_suffix() -> None:
    assert parse_follower_count("18.3K followers") == 18_300


def test_parse_follower_count_invalid_returns_none() -> None:
    assert parse_follower_count("unknown") is None


def test_parse_count_text_variants() -> None:
    assert parse_count_text("1,234") == 1234
    assert parse_count_text("12.5K comments") == 12500
    assert parse_count_text("3M") == 3000000
    assert parse_count_text("") is None


def test_parse_rumble_datetime() -> None:
    assert parse_rumble_datetime("2026-05-06T12:34:56-04:00") is not None
    assert parse_rumble_datetime("2026-05-06T12:34:56") is not None
    assert parse_rumble_datetime("invalid-date") is None
