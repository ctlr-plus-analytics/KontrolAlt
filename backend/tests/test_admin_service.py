import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.exceptions import WorkerUnavailableError
from models.admin import UpdateKeywordTaxonomyRequest, WorkerInfo
from services import admin_service


class _FakeExecuteResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, client, select_field=None, update_payload=None):
        self._client = client
        self._select_field = select_field
        self._update_payload = update_payload

    def eq(self, *_args, **_kwargs):
        return self

    def single(self):
        return self

    def execute(self):
        if self._update_payload is not None:
            self._client.updated_payloads.append(self._update_payload)
            self._client.current.update(self._update_payload)
            return _FakeExecuteResult([self._update_payload])
        if self._select_field:
            return _FakeExecuteResult({self._select_field: self._client.current.get(self._select_field)})
        return _FakeExecuteResult({})


class _FakeSupabaseAdmin:
    def __init__(self, initial):
        self.current = dict(initial)
        self.updated_payloads = []

    def table(self, _name):
        return self

    def select(self, field):
        return _FakeQuery(self, select_field=field)

    def update(self, payload):
        return _FakeQuery(self, update_payload=payload)


class _FakeCeleryTask:
    id = "bootstrap-task-1"


class _FakeCelery:
    def __init__(self):
        self.sent_tasks = []

    def send_task(self, task_name, *args, **kwargs):
        self.sent_tasks.append((task_name, args, kwargs))
        return _FakeCeleryTask()


def test_get_worker_preflight_reports_blocking_and_warning_services(monkeypatch):
    workers = [
        WorkerInfo(service="worker-discovery", online=True, container_status="running"),
        WorkerInfo(service="worker-classify", online=True, container_status="running"),
        WorkerInfo(service="worker-gate0", online=False, container_status="exited"),
        WorkerInfo(service="worker-rumble", online=True, container_status="running"),
        WorkerInfo(service="worker-substack", online=True, container_status="running"),
        WorkerInfo(service="beat", online=False, container_status="exited"),
    ]
    monkeypatch.setattr(
        admin_service,
        "_collect_worker_statuses",
        lambda: (workers, datetime.now(timezone.utc)),
    )

    result = asyncio.run(admin_service.get_worker_preflight("gate0"))

    assert result.ready is False
    assert result.blocking_services == ["worker-gate0"]
    assert result.warning_services == ["beat"]
    assert "worker-gate0" in result.message
    assert "beat" in result.message


def test_trigger_gate0_batch_blocks_before_pending_when_worker_offline(monkeypatch):
    fake_celery = _FakeCelery()
    updates = []

    class _FakeChannelsTable:
        def update(self, payload):
            updates.append(payload)
            return self

        def eq(self, *_args, **_kwargs):
            return self

        def execute(self):
            return _FakeExecuteResult([])

    class _FakeSupabase:
        def table(self, _name):
            return _FakeChannelsTable()

    async def _blocked(_task_kind: str):
        raise WorkerUnavailableError("Gate 0 batch is blocked because worker-gate0 is offline.")

    monkeypatch.setattr(admin_service, "_celery", fake_celery)
    monkeypatch.setattr(admin_service, "supabase_admin", _FakeSupabase())
    monkeypatch.setattr(admin_service, "_require_workers", _blocked)

    with pytest.raises(WorkerUnavailableError):
        asyncio.run(
            admin_service.trigger_gate0_batch(
                actor={"id": "u1", "email": "admin@example.com"},
                channel_ids=[],
                reason="test",
            )
        )

    assert fake_celery.sent_tasks == []
    assert updates == []


def test_trigger_never_scraped_bootstrap_dispatches_task_and_audits(monkeypatch):
    fake_celery = _FakeCelery()
    audit_calls = []
    monkeypatch.setattr(admin_service, "_celery", fake_celery)
    monkeypatch.setattr(admin_service, "_audit", lambda **kwargs: audit_calls.append(kwargs))

    async def _allowed(_task_kind: str):
        return None

    monkeypatch.setattr(admin_service, "_require_workers", _allowed)

    result = asyncio.run(
        admin_service.trigger_never_scraped_bootstrap(
            actor={"id": "u1", "email": "admin@example.com"},
            reason="test",
        )
    )

    assert fake_celery.sent_tasks == [
        (
            admin_service.TASK_SCRAPE_NEVER_SCRAPED_RUMBLE_SUBSTACK,
            (),
            {"queue": admin_service.QUEUE_DISCOVERY},
        )
    ]
    assert result.task_id == "bootstrap-task-1"
    assert result.task_ids == ["bootstrap-task-1"]
    assert audit_calls[-1]["target"] == "scrape.never_scraped_rumble_substack"
    assert audit_calls[-1]["metadata"] == {
        "task_ids": ["bootstrap-task-1"],
        "reason": "test",
    }


def test_get_keyword_taxonomy_returns_db_value(monkeypatch):
    fake = _FakeSupabaseAdmin(
        {"keyword_taxonomy": [{"niche": "alpha", "keywords": ["one"]}]}
    )
    monkeypatch.setattr(admin_service, "supabase_admin", fake)

    result = asyncio.run(admin_service.get_keyword_taxonomy())

    assert result == [{"niche": "alpha", "keywords": ["one"]}]


def test_update_keyword_taxonomy_writes_and_audits(monkeypatch):
    fake = _FakeSupabaseAdmin(
        {"keyword_taxonomy": [{"niche": "old", "keywords": ["legacy"]}]}
    )
    audit_calls = []
    monkeypatch.setattr(admin_service, "supabase_admin", fake)
    monkeypatch.setattr(admin_service, "_audit", lambda **kwargs: audit_calls.append(kwargs))
    payload = [{"niche": "new", "keywords": ["fresh"]}]

    result = asyncio.run(
        admin_service.update_keyword_taxonomy(
            actor={"id": "u1", "email": "admin@example.com"},
            taxonomy=payload,
        )
    )

    assert result == payload
    assert fake.updated_payloads[-1] == {"keyword_taxonomy": payload}
    assert audit_calls[-1]["target"] == "keyword_taxonomy"
    assert audit_calls[-1]["old_value"] == {
        "keyword_taxonomy": [{"niche": "old", "keywords": ["legacy"]}]
    }
    assert audit_calls[-1]["new_value"] == {"keyword_taxonomy": payload}


def test_keyword_taxonomy_validation_rejects_empty_values():
    with pytest.raises(Exception):
        UpdateKeywordTaxonomyRequest.model_validate(
            {"taxonomy": [{"niche": " ", "keywords": ["ok"]}]}
        )
    with pytest.raises(Exception):
        UpdateKeywordTaxonomyRequest.model_validate(
            {"taxonomy": [{"niche": "valid", "keywords": [" "]}]}
        )
