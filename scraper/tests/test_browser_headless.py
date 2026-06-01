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


def test_headless_defaults_to_true_on_linux(monkeypatch) -> None:
    monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
    monkeypatch.setattr(browser.sys, "platform", "linux")

    assert browser._resolve_headless_mode() is True


def test_headless_defaults_to_false_on_non_linux(monkeypatch) -> None:
    monkeypatch.delenv("BROWSER_HEADLESS", raising=False)
    monkeypatch.setattr(browser.sys, "platform", "win32")

    assert browser._resolve_headless_mode() is False


def test_headless_true_env_override(monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_HEADLESS", "true")
    monkeypatch.setattr(browser.sys, "platform", "win32")

    assert browser._resolve_headless_mode() is True


def test_headless_false_env_override(monkeypatch) -> None:
    monkeypatch.setenv("BROWSER_HEADLESS", "false")
    monkeypatch.setattr(browser.sys, "platform", "linux")

    assert browser._resolve_headless_mode() is False
