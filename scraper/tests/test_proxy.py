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

if "core.config" not in sys.modules:
    core_config_stub = types.ModuleType("core.config")
    core_config_stub.scraper_settings = types.SimpleNamespace(
        proxy_list="http://user:pass@example.com:8080",
        serp_api_key="serper-key",
    )
    sys.modules["core.config"] = core_config_stub

from core.proxy import _normalize_proxy


def test_normalize_proxy_supports_evomi_host_port_user_pass() -> None:
    normalized = _normalize_proxy(
        "http://core-residential.evomi.com:1000:analytics8:secret"
    )

    assert normalized == "http://analytics8:secret@core-residential.evomi.com:1000"

def test_normalize_proxy_keeps_preconfigured_evomi_sticky_password_suffix() -> None:
    normalized = _normalize_proxy(
        "http://core-residential.evomi.com:1000:analytics8:secret_session-abc123_lifetime-10"
    )

    assert normalized == (
        "http://analytics8:secret_session-abc123_lifetime-10"
        "@core-residential.evomi.com:1000"
    )
