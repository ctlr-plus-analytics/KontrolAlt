"""Tests for scrape task helper reliability behavior."""

from types import SimpleNamespace

from tasks.scrape_helpers import retry_countdown_seconds


class _DummyTask:
    def __init__(self, retries: int) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.max_retries = 3


def test_retry_countdown_seconds_has_jitter_bounds_retry0() -> None:
    task = _DummyTask(retries=0)
    for _ in range(50):
        countdown = retry_countdown_seconds(task)
        assert 48 <= countdown <= 72


def test_retry_countdown_seconds_has_jitter_bounds_retry2() -> None:
    task = _DummyTask(retries=2)
    for _ in range(50):
        countdown = retry_countdown_seconds(task)
        assert 192 <= countdown <= 288
