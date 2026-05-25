import asyncio
import os
import sys
import time
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

from core.cf_bypass import (
    ProxySessionManager,
    SessionRateLimiter,
    classify_cloudflare_block,
    detect_captcha,
    human_delay_value,
    is_cloudflare_ip,
)


class _FakePage:
    def __init__(self, title: str = "", body_text: str = "", selectors: set[str] | None = None):
        self._title = title
        self._body_text = body_text
        self._selectors = selectors or set()

    async def title(self) -> str:
        return self._title

    async def query_selector(self, selector: str):
        return object() if selector in self._selectors else None

    async def inner_text(self, selector: str) -> str:
        if selector == "body":
            return self._body_text
        return ""


def test_human_delay_value_bounds() -> None:
    for _ in range(200):
        val = human_delay_value()
        assert val >= 0.0
        assert val <= 12.0


def test_is_cloudflare_ip() -> None:
    assert is_cloudflare_ip("104.16.0.1") is True
    assert is_cloudflare_ip("8.8.8.8") is False


def test_proxy_session_manager_unique_per_channel() -> None:
    manager = ProxySessionManager(cooldown_seconds=60)
    sid_a = manager.get_session_for_channel("https://rumble.com/c/a")
    sid_b = manager.get_session_for_channel("https://rumble.com/c/b")
    assert sid_a != sid_b


def test_proxy_session_manager_cooldown() -> None:
    manager = ProxySessionManager(cooldown_seconds=1)
    sid = manager.get_session_for_channel("https://rumble.com/c/a")
    manager.mark_blocked(sid)
    assert manager.is_blocked(sid) is True
    time.sleep(1.1)
    assert manager.is_blocked(sid) is False


def test_classify_cloudflare_block_1015() -> None:
    page = _FakePage(title="Error 1015", body_text="Rate limited")
    result = asyncio.run(classify_cloudflare_block(page))
    assert result is not None
    assert result[0] == "CF_RATE_LIMITED"
    assert result[1] == "rate_limit"
    assert result[2] is True
    assert result[3] == 1015


def test_classify_cloudflare_js_challenge() -> None:
    page = _FakePage(selectors={"#challenge-form, #challenge-running, .cf-browser-verification"})
    result = asyncio.run(classify_cloudflare_block(page))
    assert result is not None
    assert result[1] == "js_challenge"


def test_detect_captcha_positive() -> None:
    page = _FakePage(selectors={"iframe[src*='hcaptcha.com']"})
    assert asyncio.run(detect_captcha(page)) is True


def test_detect_captcha_negative() -> None:
    page = _FakePage()
    assert asyncio.run(detect_captcha(page)) is False


def test_session_rate_limiter_blocks_when_exceeded() -> None:
    limiter = SessionRateLimiter(max_rpm=2)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(limiter.acquire())
        loop.run_until_complete(limiter.acquire())
        # Third call should still complete, but only after internal wait path.
        loop.run_until_complete(limiter.acquire())
        assert len(limiter.timestamps) <= 3
    finally:
        loop.close()
