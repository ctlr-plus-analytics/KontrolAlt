import os
import sys
from pathlib import Path

from pytest import MonkeyPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

from core.runtime_settings import RuntimeSettings  # noqa: E402
from tasks.scrape_never_scraped import scrape_never_scraped_rumble_substack  # noqa: E402


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *_args, **_kwargs):
        return self

    def in_(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def is_(self, *_args, **_kwargs):
        return self

    def execute(self):
        class _Result:
            pass

        res = _Result()
        res.data = self._data
        return res


class _FakeClient:
    def __init__(self, data):
        self._data = data

    def table(self, _name: str):
        return _FakeQuery(self._data)


def test_scrape_never_scraped_rumble_substack_dispatches_by_platform(
    monkeypatch: MonkeyPatch,
) -> None:
    queued_rumble: list[str] = []
    queued_substack: list[str] = []

    monkeypatch.setattr(
        "tasks.scrape_never_scraped.get_runtime_settings",
        lambda: RuntimeSettings(),
    )
    monkeypatch.setattr(
        "tasks.scrape_never_scraped.get_supabase_client",
        lambda: _FakeClient(
            [
                {"platform": "rumble", "channel_url": "https://rumble.com/c/test"},
                {"platform": "substack", "channel_url": "https://substack.com/@test"},
                {"platform": "youtube", "channel_url": "https://youtube.com/@test"},
            ]
        ),
    )
    monkeypatch.setattr("tasks.scrape_never_scraped.is_open", lambda _platform: False)
    monkeypatch.setattr("tasks.scrape_never_scraped.random.uniform", lambda _a, _b: 1.0)
    monkeypatch.setattr(
        "tasks.scrape_never_scraped.scrape_rumble_channel.apply_async",
        lambda args, countdown: queued_rumble.append(f"{args[0]}|{countdown}"),
    )
    monkeypatch.setattr(
        "tasks.scrape_never_scraped.scrape_substack_channel.apply_async",
        lambda args, countdown: queued_substack.append(f"{args[0]}|{countdown}"),
    )

    result = scrape_never_scraped_rumble_substack()

    assert result["queued"] == 2
    assert queued_rumble == ["https://rumble.com/c/test|0"]
    assert queued_substack == ["https://substack.com/@test|1"]

