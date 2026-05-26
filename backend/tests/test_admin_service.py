import pytest
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.admin import UpdateKeywordTaxonomyRequest
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
