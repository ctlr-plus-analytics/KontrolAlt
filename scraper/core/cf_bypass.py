"""Cloudflare bypass helpers: behavior simulation, classification, and rate shaping."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import math
import random
import socket
import time
from dataclasses import dataclass

import httpx

from core.system_settings import get_runtime_settings

CLOUDFLARE_ERROR_CODES: dict[int, tuple[str, str, bool]] = {
    1020: ("CF_ACCESS_DENIED", "firewall_rule", False),
    1010: ("CF_FINGERPRINT_BLOCK", "fingerprint", False),
    1015: ("CF_RATE_LIMITED", "rate_limit", True),
    1009: ("CF_GEO_BLOCKED", "geo_block", True),
    503: ("CF_UNDER_ATTACK", "under_attack_mode", False),
}

_CF_RANGES = (
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "198.41.128.0/17",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
)

FIREFOX_UA_POOL = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
)


def human_delay_value() -> float:
    runtime = get_runtime_settings()
    min_s = runtime.cf_bypass_delay_min_s
    max_s = runtime.cf_bypass_delay_max_s
    long_prob = runtime.cf_bypass_delay_long_pause_probability
    long_max = runtime.cf_bypass_delay_long_pause_max_s
    if random.random() < long_prob:
        return random.uniform(max_s, max(long_max, max_s))
    mu = math.log(min_s + (max_s - min_s) * 0.3)
    sigma = 0.6
    return min(max(random.lognormvariate(mu, sigma), min_s), max_s)


async def inter_request_jitter() -> None:
    runtime = get_runtime_settings()
    delay = runtime.cf_bypass_inter_request_base_s + random.gauss(
        0.0, runtime.cf_bypass_inter_request_variance
    )
    await asyncio.sleep(max(0.3, delay))


class SessionRateLimiter:
    """Sliding-window requests-per-minute limiter per session."""

    def __init__(self, max_rpm: int = 20) -> None:
        self.max_rpm = max(1, max_rpm)
        self.window = 60.0
        self.timestamps: list[float] = []

    async def acquire(self) -> None:
        now = asyncio.get_event_loop().time()
        self.timestamps = [t for t in self.timestamps if now - t < self.window]
        if len(self.timestamps) >= self.max_rpm:
            wait = self.window - (now - self.timestamps[0]) + random.uniform(0.1, 0.5)
            await asyncio.sleep(max(0.1, wait))
        self.timestamps.append(asyncio.get_event_loop().time())


_SESSION_LIMITERS: dict[str, SessionRateLimiter] = {}

def _max_rpm_for_session(session_key: str, default_rpm: int, bitchute_rpm: int) -> int:
    key = session_key.lower()
    if "bitchute.com" in key or "bitchute|" in key:
        return max(1, bitchute_rpm)
    return max(1, default_rpm)


async def acquire_session_request_slot(session_key: str | None) -> None:
    if not session_key:
        return
    runtime = get_runtime_settings()
    limiter = _SESSION_LIMITERS.get(session_key)
    if limiter is None:
        limiter = SessionRateLimiter(
            max_rpm=_max_rpm_for_session(
                session_key,
                runtime.cf_bypass_max_rpm_residential,
                runtime.cf_bypass_max_rpm_bitchute,
            )
        )
        _SESSION_LIMITERS[session_key] = limiter
    await limiter.acquire()


async def human_click(page, selector: str) -> None:
    element = await page.wait_for_selector(selector, state="visible")
    box = await element.bounding_box()
    if not box:
        await element.click()
        return
    target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
    current = await page.evaluate("() => ({ x: window.__mouseX || 100, y: window.__mouseY || 100 })")
    steps = random.randint(8, 18)
    for i in range(steps):
        t = (i + 1) / steps
        deviation = math.sin(t * math.pi) * random.uniform(-8, 8)
        x = current["x"] + (target_x - current["x"]) * t + deviation
        y = current["y"] + (target_y - current["y"]) * t
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.01, 0.04))
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.click(target_x, target_y)


async def human_scroll(page, direction: str = "down", steps: int | None = None) -> None:
    viewport = await page.evaluate("() => ({ h: window.innerHeight, total: document.body.scrollHeight })")
    total = int(viewport.get("total", 0))
    current = int(await page.evaluate("() => window.scrollY"))
    runtime = get_runtime_settings()
    if steps is None:
        steps = random.randint(runtime.cf_bypass_scroll_steps_min, runtime.cf_bypass_scroll_steps_max)
    target = total if direction == "down" else 0
    for i in range(max(1, steps)):
        progress = (i + 1) / steps
        ease = progress * (2 - progress)
        new_pos = int(current + (target - current) * ease)
        scroll_amount = new_pos - current
        await page.mouse.wheel(0, scroll_amount + random.randint(-30, 30))
        await asyncio.sleep(random.uniform(0.15, 0.55))


def get_consistent_browser_profile(proxy_country: str | None = None) -> dict[str, object]:
    ua = random.choice(FIREFOX_UA_POOL)
    country_map = {
        "US": ("en-US", "America/New_York"),
        "GB": ("en-GB", "Europe/London"),
        "DE": ("de-DE", "Europe/Berlin"),
        "FR": ("fr-FR", "Europe/Paris"),
        "CA": ("en-CA", "America/Toronto"),
    }
    locale, timezone = country_map.get((proxy_country or "US").upper(), ("en-US", "America/New_York"))
    return {
        "user_agent": ua,
        "locale": locale,
        "timezone_id": timezone,
        "viewport": random.choice(
            (
                {"width": 1920, "height": 1080},
                {"width": 1440, "height": 900},
                {"width": 1366, "height": 768},
                {"width": 1536, "height": 864},
            )
        ),
        "extra_http_headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": f"{locale},en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        },
    }


async def verify_fingerprint(page) -> dict[str, bool]:
    return await page.evaluate(
        """() => ({
            webdriver_absent: navigator.webdriver === undefined || navigator.webdriver === false,
            plugins_present: navigator.plugins.length > 0,
            languages_present: !!(navigator.languages && navigator.languages.length > 0),
            chrome_absent: typeof window.chrome === 'undefined',
            automation_absent: !document.documentElement.getAttribute('webdriver'),
            canvas_not_blocked: (() => { try { const c = document.createElement('canvas'); c.getContext('2d'); return true; } catch(e) { return false; } })(),
            screen_realistic: screen.width >= 1024 && screen.height >= 768,
        })"""
    )


async def classify_cloudflare_block(page) -> tuple[str, str, bool, int | None] | None:
    title = (await page.title() or "")
    body = ""
    body_node = await page.query_selector("body")
    if body_node is not None:
        body = (await body_node.inner_text()) or ""
    lowered = body.lower()
    for code, (name, block_type, rotation_helps) in CLOUDFLARE_ERROR_CODES.items():
        if str(code) in title or f"Error {code}" in body or f"error code {code}" in lowered:
            return (name, block_type, rotation_helps, code)
    if await page.query_selector("#challenge-form, #challenge-running, .cf-browser-verification"):
        return ("CF_CHALLENGE", "js_challenge", True, None)
    return None


async def detect_captcha(page) -> bool:
    selectors = (
        "#challenge-form input[name='cf_captcha_kind']",
        "iframe[src*='challenges.cloudflare.com']",
        "iframe[src*='hcaptcha.com']",
        "iframe[src*='recaptcha']",
        ".hcaptcha-box",
    )
    for selector in selectors:
        if await page.query_selector(selector):
            return True
    return False


def is_cloudflare_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in ipaddress.ip_network(network) for network in _CF_RANGES)


async def try_resolve_origin_ip(domain: str, timeout: float = 5.0) -> str | None:
    try:
        ip = socket.gethostbyname(domain)
    except Exception:
        return None
    if is_cloudflare_ip(ip):
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"https://{domain}/",
                headers={"Host": domain},
                follow_redirects=False,
            )
            if response.status_code < 400:
                return ip
    except Exception:
        return None
    return None


@dataclass
class ProxySessionManager:
    cooldown_seconds: int = 1800
    _used_sessions: set[str] = None  # type: ignore[assignment]
    _blocked_sessions: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._used_sessions = set()
        self._blocked_sessions = {}

    def get_session_for_channel(self, channel_url: str) -> str:
        base = hashlib.sha256(f"{channel_url}:{int(time.time() // 3600)}".encode()).hexdigest()[:16]
        session_id = base
        if session_id in self._used_sessions:
            session_id = hashlib.sha256(f"{channel_url}:{time.time()}".encode()).hexdigest()[:16]
        self._used_sessions.add(session_id)
        return session_id

    def mark_blocked(self, session_id: str) -> None:
        self._blocked_sessions[session_id] = time.time()

    def is_blocked(self, session_id: str) -> bool:
        blocked_at = self._blocked_sessions.get(session_id)
        if blocked_at is None:
            return False
        return (time.time() - blocked_at) < self.cooldown_seconds
