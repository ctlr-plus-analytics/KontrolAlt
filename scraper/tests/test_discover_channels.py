import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

if "httpx" not in sys.modules:
    httpx_stub = types.ModuleType("httpx")
    httpx_stub.HTTPError = Exception
    httpx_stub.Client = object
    sys.modules["httpx"] = httpx_stub
if "redis" not in sys.modules:
    redis_stub = types.ModuleType("redis")

    class RedisError(Exception):
        pass

    class Redis:
        @staticmethod
        def from_url(*_args, **_kwargs):
            return Redis()

        def exists(self, *_args, **_kwargs):
            return 0

        def incr(self, *_args, **_kwargs):
            return 0

        def expire(self, *_args, **_kwargs):
            return None

        def set(self, *_args, **_kwargs):
            return None

        def delete(self, *_args, **_kwargs):
            return None

    redis_stub.Redis = Redis
    redis_stub.RedisError = RedisError
    sys.modules["redis"] = redis_stub
if "postgrest.exceptions" not in sys.modules:
    postgrest_stub = types.ModuleType("postgrest")
    exceptions_stub = types.ModuleType("postgrest.exceptions")

    class APIError(Exception):
        pass

    exceptions_stub.APIError = APIError
    postgrest_stub.exceptions = exceptions_stub
    sys.modules["postgrest"] = postgrest_stub
    sys.modules["postgrest.exceptions"] = exceptions_stub
if "celery" not in sys.modules:
    celery_stub = types.ModuleType("celery")

    class Celery:
        def __init__(self, *args, **kwargs):
            self.conf = types.SimpleNamespace(update=lambda **_kwargs: None)

        def task(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    class Task:
        pass

    celery_stub.Celery = Celery
    celery_stub.Task = Task
    celery_stub.chord = lambda *_args, **_kwargs: None
    sys.modules["celery"] = celery_stub
if "worker" not in sys.modules:
    worker_stub = types.ModuleType("worker")

    class FakeCeleryApp:
        @staticmethod
        def task(*args, **kwargs):
            def decorator(func):
                return func

            return decorator

    worker_stub.celery_app = FakeCeleryApp()
    sys.modules["worker"] = worker_stub
if "core.config" not in sys.modules:
    core_config_stub = types.ModuleType("core.config")
    core_config_stub.scraper_settings = types.SimpleNamespace(serp_api_key="serper-key")
    sys.modules["core.config"] = core_config_stub
if "core.supabase" not in sys.modules:
    core_supabase_stub = types.ModuleType("core.supabase")
    core_supabase_stub.get_supabase_client = lambda: None
    sys.modules["core.supabase"] = core_supabase_stub
for module_name, attr_name in (
    ("tasks.scrape_bitchute", "scrape_bitchute_channel"),
    ("tasks.scrape_rumble", "scrape_rumble_channel"),
):
    if module_name not in sys.modules:
        task_stub = types.ModuleType(module_name)

        class FakeScrapeTask:
            @staticmethod
            def delay(_channel_url):
                return None

        setattr(task_stub, attr_name, FakeScrapeTask)
        sys.modules[module_name] = task_stub

import tasks.discover_channels as discover_channels


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, table):
        self.table = table
        self.range_start = 0
        self.range_end = None
        self.eq_field = None
        self.eq_value = None
        self.payload = None
        self.insert_payload = None
        self.single = False

    def select(self, _columns):
        return self

    def range(self, start, end):
        self.range_start = start
        self.range_end = end
        return self

    def eq(self, field, value):
        self.eq_field = field
        self.eq_value = value
        return self

    def maybe_single(self):
        self.single = True
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def execute(self):
        if self.insert_payload is not None:
            self.table.rows.append(self.insert_payload)
            self.table.inserts.append(self.insert_payload)
            return FakeResult([self.insert_payload])
        if self.payload is not None:
            self.table.updates.append((self.eq_value, self.payload))
            for row in self.table.rows:
                if row.get(self.eq_field) == self.eq_value:
                    row.update(self.payload)
            return FakeResult([self.payload])
        if self.single:
            for row in self.table.rows:
                if row.get(self.eq_field) == self.eq_value:
                    return FakeResult(row)
            return FakeResult(None)
        rows = self.table.rows[self.range_start : self.range_end + 1]
        return FakeResult(rows)


class FakeNoneResponseQuery(FakeQuery):
    def execute(self):
        if self.single:
            return None
        return super().execute()


class FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []
        self.inserts = []

    def select(self, columns):
        return FakeQuery(self).select(columns)

    def update(self, payload):
        return FakeQuery(self).update(payload)

    def insert(self, payload):
        return FakeQuery(self).insert(payload)


class FakeNoneResponseTable(FakeTable):
    def select(self, columns):
        return FakeNoneResponseQuery(self).select(columns)


class FakeClient:
    def __init__(self, rows):
        self.channels = FakeTable(rows)

    def table(self, name):
        assert name == "channels"
        return self.channels


class FakeNoneResponseClient(FakeClient):
    def __init__(self, rows):
        self.channels = FakeNoneResponseTable(rows)


def test_iter_channel_rows_reads_all_pages(monkeypatch) -> None:
    rows = [{"id": str(index)} for index in range(5)]
    client = FakeClient(rows)
    monkeypatch.setattr(discover_channels, "_CHANNEL_PAGE_SIZE", 2)

    result = list(discover_channels._iter_channel_rows(client, "id"))

    assert result == rows


def test_existing_channel_by_url_handles_missing_response() -> None:
    client = FakeNoneResponseClient([])

    result = discover_channels._existing_channel_by_url(
        client, "https://rumble.com/c/hannel"
    )

    assert result is None


def test_extract_serp_candidates_reads_snippet_urls() -> None:
    result = discover_channels._extract_serp_candidates(
        {
            "title": "Signal Desk",
            "link": "https://example.com/not-supported",
            "snippet": "Creator moved to rumble.com/SignalDesk and old.bitchute.com/channel/SignalDesk.",
        }
    )

    urls = {candidate.channel_url for candidate in result}
    assert "https://rumble.com/SignalDesk" in urls
    assert "https://bitchute.com/channel/SignalDesk" in urls


def test_extract_serp_candidates_reads_nested_rich_results() -> None:
    result = discover_channels._extract_serp_candidates(
        {
            "title": "Preparedness channels",
            "link": "https://example.com/roundup",
            "richSnippet": {
                "top": {
                    "extensions": [
                        "Also on Rumble channel rumble.com/c/GridDownRadio",
                        {"url": "https://old.bitchute.com/channel/HomesteadWire/"},
                    ]
                }
            },
            "sitelinks": [
                {"title": "Mirror", "link": "https://rumble.com/user/SignalDesk"},
            ],
        }
    )

    urls = {candidate.channel_url for candidate in result}
    assert "https://rumble.com/c/GridDownRadio" in urls
    assert "https://bitchute.com/channel/HomesteadWire" in urls
    assert "https://rumble.com/user/SignalDesk" in urls


def test_query_for_keyword_excludes_video_paths() -> None:
    rumble_query = discover_channels._query_for_keyword("gold ira", "rumble")
    bitchute_query = discover_channels._query_for_keyword("gold ira", "bitchute")

    assert "-inurl:/v" in rumble_query
    assert "-inurl:/video/" in bitchute_query
    assert "OR -inurl" not in rumble_query


def test_keyword_templates_include_loose_channel_discovery_queries() -> None:
    queries = discover_channels._keyword_templates(
        "prepper_survival_homesteading", "water storage"
    )

    assert '"water storage" "Rumble channel"' in queries
    assert '"water storage" "BitChute channel"' in queries
    assert 'site:rumble.com/c/ "water storage" -inurl:/v -inurl:/embed/' in queries
    assert any('"prepper survival homesteading"' in query for query in queries)


def test_search_serper_retries_transient_failures(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self.payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise discover_channels.httpx.HTTPStatusError(
                    "transient",
                    request=discover_channels.httpx.Request(
                        "POST", "https://example.com"
                    ),
                    response=discover_channels.httpx.Response(self.status_code),
                )

        def json(self):
            return self.payload

    class FakeHttp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                return FakeResponse(503)
            return FakeResponse(
                200, {"organic": [{"link": "https://rumble.com/c/SignalDesk"}]}
            )

    monkeypatch.setattr(discover_channels.httpx, "Client", lambda timeout: FakeHttp())
    monkeypatch.setattr(discover_channels.time, "sleep", lambda _seconds: None)

    results = discover_channels._search_serper("site:rumble.com SignalDesk")

    assert len(calls) == 2
    assert results == [{"link": "https://rumble.com/c/SignalDesk"}]


def test_keyword_discovery_confidence_scores_loose_and_direct_hits() -> None:
    candidate = discover_channels.ChannelUrlCandidate(
        channel_url="https://rumble.com/c/SignalDesk",
        platform="rumble",
    )
    loose_confidence = discover_channels._keyword_discovery_confidence(
        query='"gold ira" "Rumble channel"',
        query_kind="base",
        item={
            "title": "Signal Desk",
            "snippet": "Watch this creator at rumble.com/c/SignalDesk.",
            "link": "https://example.com/roundup",
        },
        candidate=candidate,
    )
    direct_confidence = discover_channels._keyword_discovery_confidence(
        query='site:rumble.com/c/ "gold ira" -inurl:/v',
        query_kind="base",
        item={
            "title": "Signal Desk",
            "link": "https://rumble.com/c/SignalDesk",
        },
        candidate=candidate,
    )

    assert loose_confidence < direct_confidence
    assert loose_confidence == 0.58
    assert direct_confidence == 0.82


def test_iter_search_queries_round_robins_categories(monkeypatch) -> None:
    taxonomy = {
        "alpha": ["one", "two"],
        "beta": ["three", "four"],
        "gamma": ["five", "six"],
    }
    monkeypatch.setattr(discover_channels, "KEYWORD_TAXONOMY", taxonomy)
    monkeypatch.setattr(discover_channels, "_QUERY_LIMIT", 9)

    queries = discover_channels._iter_search_queries()

    assert [query[0] for query in queries[:6]] == [
        "alpha",
        "beta",
        "gamma",
        "alpha",
        "beta",
        "gamma",
    ]
    assert all(query[3] == "base" for query in queries)


def test_feedback_queries_append_round_robin_by_category(monkeypatch) -> None:
    monkeypatch.setattr(
        discover_channels,
        "KEYWORD_TAXONOMY",
        {"alpha": ["one"], "beta": ["two"], "gamma": ["three"]},
    )
    active = []
    feedback_by_category = {
        "alpha": [
            ("alpha", "one", "alpha-q1", "feedback"),
            ("alpha", "one", "alpha-q2", "feedback"),
        ],
        "beta": [("beta", "two", "beta-q1", "feedback")],
        "gamma": [("gamma", "three", "gamma-q1", "feedback")],
    }

    discover_channels._append_feedback_queries_round_robin(
        active_queries=active,
        feedback_by_category=feedback_by_category,
        max_queries=4,
    )

    assert [query[0] for query in active] == ["alpha", "beta", "gamma", "alpha"]


def test_keyword_discovery_reports_category_metrics(monkeypatch) -> None:
    class EmptyClient:
        pass

    monkeypatch.setattr(
        discover_channels,
        "_iter_search_queries",
        lambda: [
            ("alpha", "one", "site:rumble.com one", "base"),
            ("beta", "two", "site:bitchute.com two", "base"),
        ],
    )
    monkeypatch.setattr(
        discover_channels,
        "KEYWORD_TAXONOMY",
        {"alpha": ["one"], "beta": ["two"]},
    )
    monkeypatch.setattr(discover_channels, "_MAX_PAGES_PER_QUERY", 1)
    monkeypatch.setattr(discover_channels, "_search_serper", lambda _query, page=1: [])

    result = discover_channels._discover_from_keywords(EmptyClient())

    assert result["category_metrics"]["alpha"]["searched_queries"] == 1
    assert result["category_metrics"]["beta"]["searched_queries"] == 1
    assert result["category_metrics"]["alpha"]["base_queries"] == 1
    assert result["category_metrics"]["beta"]["base_queries"] == 1


def test_discover_channels_isolates_seed_phase_failure(monkeypatch) -> None:
    monkeypatch.setattr(discover_channels, "get_supabase_client", lambda: object())

    def fail_seed(_client):
        raise ValueError("seed failed")

    def keyword_ok(_client):
        return {
            "searched_queries": 1,
            "pages_fetched": 1,
            "raw_links": 1,
            "discovered": 1,
            "inserted": 1,
            "refreshed": 0,
            "duplicates": 0,
            "invalid": 0,
            "inserted_rumble": 1,
            "inserted_bitchute": 0,
            "feedback_terms": [],
            "new_urls": [{"channel_url": "https://rumble.com/SignalDesk", "platform": "rumble"}],
        }

    monkeypatch.setattr(discover_channels, "_discover_from_known_channels", fail_seed)
    monkeypatch.setattr(discover_channels, "_discover_from_keywords", keyword_ok)

    result = discover_channels.discover_channels_now(queue_scrapes=False)

    assert result["discovery_failed"] is True
    assert result["inserted"] == 1
    assert result["keyword_expansion"]["searched_queries"] == 1
    assert "error" in result["seed_expansion"]


def test_queue_discovered_channel_scrapes_marks_rows_queued(monkeypatch) -> None:
    client = FakeClient([])
    queued_urls = []

    class FakeTask:
        @staticmethod
        def delay(channel_url):
            queued_urls.append(channel_url)

    monkeypatch.setattr(discover_channels, "get_supabase_client", lambda: client)
    monkeypatch.setattr(discover_channels, "scrape_rumble_channel", FakeTask)
    monkeypatch.setattr(discover_channels, "is_open", lambda _platform: False)

    queued = discover_channels.queue_discovered_channel_scrapes(
        [{"channel_url": "https://rumble.com/SignalDesk", "platform": "rumble"}]
    )

    assert queued == 1
    assert queued_urls == ["https://rumble.com/SignalDesk"]
    assert client.channels.updates[0][0] == "https://rumble.com/SignalDesk"
    assert client.channels.updates[0][1]["discovery_status"] == "queued"


def test_queue_discovered_channel_scrapes_prioritizes_confidence(monkeypatch) -> None:
    client = FakeClient([])
    queued_urls = []

    class FakeTask:
        @staticmethod
        def delay(channel_url):
            queued_urls.append(channel_url)

    monkeypatch.setattr(discover_channels, "_SCRAPE_NEW_LIMIT", 2)
    monkeypatch.setattr(discover_channels, "get_supabase_client", lambda: client)
    monkeypatch.setattr(discover_channels, "scrape_rumble_channel", FakeTask)
    monkeypatch.setattr(discover_channels, "is_open", lambda _platform: False)

    queued = discover_channels.queue_discovered_channel_scrapes(
        [
            {
                "channel_url": "https://rumble.com/Low",
                "platform": "rumble",
                "confidence": 0.58,
            },
            {
                "channel_url": "https://rumble.com/High",
                "platform": "rumble",
                "confidence": 0.82,
            },
            {
                "channel_url": "https://rumble.com/Mid",
                "platform": "rumble",
                "confidence": 0.75,
            },
        ]
    )

    assert queued == 2
    assert queued_urls == ["https://rumble.com/High", "https://rumble.com/Mid"]


def test_queue_discovered_channel_scrapes_skips_open_breaker(monkeypatch) -> None:
    client = FakeClient([])
    queued_urls = []

    class FakeTask:
        @staticmethod
        def delay(channel_url):
            queued_urls.append(channel_url)

    monkeypatch.setattr(discover_channels, "get_supabase_client", lambda: client)
    monkeypatch.setattr(discover_channels, "scrape_rumble_channel", FakeTask)
    monkeypatch.setattr(
        discover_channels,
        "is_open",
        lambda platform: platform == "rumble",
    )

    queued = discover_channels.queue_discovered_channel_scrapes(
        [{"channel_url": "https://rumble.com/SignalDesk", "platform": "rumble"}]
    )

    assert queued == 0
    assert queued_urls == []
    assert client.channels.updates == []


def test_seed_discovery_extracts_messy_platform_mentions() -> None:
    channel = {
        "platform": "rumble",
        "description": "Find me on Rumble: @SignalDesk and BitChute channel: LibertyRoom",
        "video_titles": ["Guest also said rumble /c/ MacroAlpha and linked /user/GridDown"],
    }

    candidates = discover_channels._collect_known_channel_candidates(channel)

    urls = {candidate.channel_url for candidate, _field in candidates}
    assert "https://rumble.com/SignalDesk" in urls
    assert "https://bitchute.com/channel/LibertyRoom" in urls
    assert "https://rumble.com/c/MacroAlpha" in urls
    assert "https://rumble.com/user/GridDown" in urls


def test_seed_discovery_inserts_directly_and_reports_source_metrics(monkeypatch) -> None:
    rows = [
        {
            "id": "source-1",
            "channel_url": "https://rumble.com/c/Source",
            "description": "Also watch Rumble: @SignalDesk",
            "video_titles": [],
            "contact_info": [],
            "secondary_urls": [],
        }
    ]
    client = FakeClient(rows)
    monkeypatch.setattr(discover_channels, "_CHANNEL_PAGE_SIZE", 10)

    result = discover_channels._discover_from_known_channels(client)

    assert result["inserted"] == 1
    assert result["discovered"] == 1
    assert result["self_links"] == 1
    assert result["field_metrics"]["description"] == 1
    assert result["field_metrics"]["channel_url"] == 0
    assert result["self_link_field_metrics"]["channel_url"] == 1
    assert result["platform_metrics"]["rumble"] == 1
    assert result["inserted_platform_metrics"]["rumble"] == 1
    assert client.channels.inserts[0]["channel_url"] == "https://rumble.com/SignalDesk"
    assert client.channels.inserts[0]["discovery_confidence"] == 0.92
    assert client.channels.inserts[0]["is_active"] is True
    assert result["new_urls"][0]["confidence"] == 0.92


def test_seed_discovery_refreshes_existing_without_overwriting_scraped_name(monkeypatch) -> None:
    rows = [
        {
            "id": "source-1",
            "channel_url": "https://rumble.com/c/Source",
            "description": "Also watch https://rumble.com/SignalDesk",
            "video_titles": [],
            "contact_info": [],
            "secondary_urls": [],
        },
        {
            "id": "existing-1",
            "channel_url": "https://rumble.com/SignalDesk",
            "name": "Scraped Signal Desk",
            "has_been_scraped": True,
            "discovery_confidence": 0.5,
            "discovery_evidence_count": 3,
        },
    ]
    client = FakeClient(rows)
    monkeypatch.setattr(discover_channels, "_CHANNEL_PAGE_SIZE", 10)

    result = discover_channels._discover_from_known_channels(client)

    assert result["refreshed"] == 1
    assert result["duplicates"] == 1
    assert result["self_links"] == 2
    updated_row = next(row for row in client.channels.rows if row.get("id") == "existing-1")
    assert updated_row["name"] == "Scraped Signal Desk"
    assert updated_row["discovery_confidence"] == 0.92
    assert updated_row["discovery_evidence_count"] == 4


def test_seed_discovery_insert_limit_counts_insertions_not_self_duplicates(
    monkeypatch,
) -> None:
    rows = [
        {
            "id": "source-1",
            "channel_url": "https://rumble.com/c/Source",
            "description": "Also watch Rumble: @SignalDesk",
            "video_titles": [],
            "contact_info": [],
            "secondary_urls": [],
        },
        {
            "id": "source-2",
            "channel_url": "https://rumble.com/c/SourceTwo",
            "description": "Also watch Rumble: @MacroAlpha",
            "video_titles": [],
            "contact_info": [],
            "secondary_urls": [],
        },
    ]
    client = FakeClient(rows)
    monkeypatch.setattr(discover_channels, "_CHANNEL_PAGE_SIZE", 10)
    monkeypatch.setattr(discover_channels, "_INSERT_LIMIT", 1)

    result = discover_channels._discover_from_known_channels(client)

    assert result["inserted"] == 1
    assert result["duplicates"] == 0
    assert result["self_links"] == 1
    assert len(client.channels.inserts) == 1
