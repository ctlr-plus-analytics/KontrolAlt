import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pytest import MonkeyPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

from tasks.compute_velocity import (
    _compute_velocity_sync,
    _find_snapshot_for_date,
    _safe_velocity,
)


class _Response:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data


class _FakeQuery:
    def __init__(self, client: "_FakeClient", table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.upsert_data: dict[str, object] | None = None

    def select(self, _columns: str) -> "_FakeQuery":
        return self

    def eq(self, _column: str, _value: str) -> "_FakeQuery":
        return self

    def order(self, _column: str, desc: bool = False) -> "_FakeQuery":
        return self

    def upsert(
        self, data: dict[str, object], on_conflict: str
    ) -> "_FakeQuery":
        self.upsert_data = data
        return self

    def execute(self) -> _Response:
        if self.table_name == "channel_snapshots":
            return _Response(self.client.snapshots)
        if self.upsert_data is not None:
            self.client.upserted = self.upsert_data
            return _Response([self.upsert_data])
        return _Response([])


class _FakeClient:
    def __init__(self, snapshots: list[dict[str, object]]) -> None:
        self.snapshots = snapshots
        self.upserted: dict[str, object] | None = None

    def table(self, table_name: str) -> _FakeQuery:
        return _FakeQuery(self, table_name)


def test_safe_velocity_returns_null_for_missing_or_zero_history() -> None:
    assert _safe_velocity(100, None) is None
    assert _safe_velocity(100, 0) is None


def test_safe_velocity_computes_percentage() -> None:
    assert _safe_velocity(150, 100) == 50.0
    assert _safe_velocity(75, 100) == -25.0


def test_find_snapshot_for_date_matches_utc_date() -> None:
    snapshot = {"scraped_at": "2026-04-03T02:00:00+00:00"}

    assert _find_snapshot_for_date(
        [snapshot],
        datetime(2026, 4, 3, 23, 0, tzinfo=timezone.utc),
    ) == snapshot


def test_compute_velocity_upserts_null_row_without_history(
    monkeypatch: MonkeyPatch,
) -> None:
    fake_client = _FakeClient([])
    monkeypatch.setattr(
        "tasks.compute_velocity.get_supabase_client",
        lambda: fake_client,
    )

    result = _compute_velocity_sync("channel-1")

    assert result["status"] == "computed"
    assert fake_client.upserted is not None
    assert fake_client.upserted["view_velocity_30d"] is None
    assert fake_client.upserted["comment_velocity_90d"] is None
