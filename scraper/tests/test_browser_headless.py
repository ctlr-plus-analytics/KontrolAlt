import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PROXY_LIST", "http://user:pass@example.com:8080")
os.environ.setdefault("SERP_API_KEY", "serper-key")

from core import browser


def test_headless_defaults_to_virtual_on_linux_even_with_display(monkeypatch) -> None:
    monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setattr(browser.sys, "platform", "linux")

    assert browser._resolve_headless_mode() == "virtual"


def test_headless_virtual_is_explicit_on_linux(monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_HEADLESS", "virtual")
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setattr(browser.sys, "platform", "linux")

    assert browser._resolve_headless_mode() == "virtual"


def test_headless_true_remains_available_for_local_override(monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_HEADLESS", "true")

    assert browser._resolve_headless_mode() is True
