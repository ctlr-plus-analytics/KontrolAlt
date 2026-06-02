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


class _FakeTask:
    def __init__(self, task_id: str):
        self.id = task_id


def test_scrape_never_scraped_rumble_substack_dispatches_by_platform(
    monkeypatch: MonkeyPatch,
) -> None:
    queued_rumble: list[tuple[str, int, str]] = []
    queued_substack: list[tuple[str, int, str]] = []

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
    monkeypatch.setattr("tasks.scrape_never_scraped.random.uniform", lambda _a, _b: 1.0)
    monkeypatch.setattr(
        "tasks.scrape_never_scraped.scrape_rumble_channel.apply_async",
        lambda args, countdown, queue: queued_rumble.append(
            (args[0], countdown, queue)
        )
        or _FakeTask("rumble-task-1"),
    )
    monkeypatch.setattr(
        "tasks.scrape_never_scraped.scrape_substack_channel.apply_async",
        lambda args, countdown, queue: queued_substack.append(
            (args[0], countdown, queue)
        )
        or _FakeTask("substack-task-1"),
    )

    result = scrape_never_scraped_rumble_substack()

    assert result["queued"] == 2
    assert result["queued_by_platform"] == {"rumble": 1, "substack": 1}
    assert result["queued_tasks"] == [
        {
            "task_id": "rumble-task-1",
            "platform": "rumble",
            "channel_url": "https://rumble.com/c/test",
            "countdown_seconds": 0,
        },
        {
            "task_id": "substack-task-1",
            "platform": "substack",
            "channel_url": "https://substack.com/@test",
            "countdown_seconds": 1,
        },
    ]
    assert queued_rumble == [("https://rumble.com/c/test", 0, "rumble")]
    assert queued_substack == [("https://substack.com/@test", 1, "substack")]
