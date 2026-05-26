import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pytest import MonkeyPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

from tasks.run_daily_scrape import (  # noqa: E402
    _passes_weekly_velocity_threshold,
    _prioritize_channels_for_scrape,
    _select_weekly_velocity_channels,
    _stage_scrape_signatures,
)
from core.system_settings import RuntimeSettings  # noqa: E402


class FakeSignature:
    def __init__(self) -> None:
        self.options: dict[str, int] = {}

    def set(self, **options: int) -> "FakeSignature":
        self.options.update(options)
        return self


def test_stage_scrape_signatures_batches_by_runtime_settings(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tasks.run_daily_scrape.get_runtime_settings",
        lambda: RuntimeSettings(
            scrape_dispatch_batch_size=8,
            scrape_dispatch_pause_seconds=2.0,
        ),
    )

    signatures = [FakeSignature() for _ in range(9)]
    staged = _stage_scrape_signatures([("dummy", sig) for sig in signatures])

    assert staged == signatures
    assert [sig.options["countdown"] for sig in signatures] == [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        2,
    ]


def test_daily_prioritization_keeps_only_new_or_missing_metrics(
    monkeypatch: MonkeyPatch,
) -> None:
    old_snapshot = datetime.now(timezone.utc) - timedelta(days=10)
    complete_id = "00000000-0000-0000-0000-000000000001"
    missing_id = "00000000-0000-0000-0000-000000000002"
    new_id = "00000000-0000-0000-0000-000000000003"
    monkeypatch.setattr(
        "tasks.run_daily_scrape._latest_snapshot_by_channel_id",
        lambda _ids: {
            complete_id: old_snapshot,
            missing_id: old_snapshot,
            new_id: old_snapshot,
        },
    )
    monkeypatch.setattr(
        "tasks.run_daily_scrape.get_runtime_settings",
        lambda: RuntimeSettings(),
    )

    result = _prioritize_channels_for_scrape(
        [
            {
                "id": complete_id,
                "platform": "rumble",
                "has_been_scraped": True,
                "discovery_status": "scraped",
                "subscriber_count": 1000,
                "avg_views": 500,
                "avg_comments": 30,
                "last_active_date": "2026-05-01",
            },
            {
                "id": missing_id,
                "platform": "rumble",
                "has_been_scraped": True,
                "discovery_status": "scraped",
                "subscriber_count": 1000,
                "avg_views": None,
                "avg_comments": 30,
                "last_active_date": "2026-05-01",
            },
            {
                "id": new_id,
                "platform": "bitchute",
                "has_been_scraped": False,
                "discovery_status": "new",
                "subscriber_count": None,
                "avg_views": None,
                "avg_comments": None,
                "last_active_date": None,
            },
        ]
    )

    assert [row["id"] for row in result] == [new_id, missing_id]


def test_weekly_velocity_threshold_prefers_clean_higher_metrics(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tasks.run_daily_scrape.get_runtime_settings",
        lambda: RuntimeSettings(),
    )

    assert _passes_weekly_velocity_threshold({"comment_tier": "whale"})
    assert _passes_weekly_velocity_threshold({"avg_comments": 20})
    assert not _passes_weekly_velocity_threshold({"avg_comments": 9})


def test_weekly_velocity_selection_skips_recent_snapshots(
    monkeypatch: MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    recent_id = "00000000-0000-0000-0000-000000000004"
    stale_id = "00000000-0000-0000-0000-000000000005"
    monkeypatch.setattr(
        "tasks.run_daily_scrape._latest_snapshot_by_channel_id",
        lambda _ids: {
            recent_id: now - timedelta(hours=12),
            stale_id: now - timedelta(days=8),
        },
    )
    monkeypatch.setattr(
        "tasks.run_daily_scrape.get_runtime_settings",
        lambda: RuntimeSettings(),
    )

    result = _select_weekly_velocity_channels(
        [
            {
                "id": recent_id,
                "platform": "rumble",
                "comment_tier": "sweet_spot",
                "avg_comments": 25,
            },
            {
                "id": stale_id,
                "platform": "rumble",
                "comment_tier": "sweet_spot",
                "avg_comments": 25,
            },
        ]
    )

    assert [row["id"] for row in result] == [stale_id]
