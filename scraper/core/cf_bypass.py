"""Cloudflare bypass helpers: behavior simulation, classification, and rate shaping."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import math
import random
import time
from dataclasses import dataclass

import httpx

from core.runtime_settings import get_runtime_settings

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

# Keep in sync with the Playwright-bundled Chromium version (playwright==1.58 → Chromium 136).
# The UA must match the actual engine version — a mismatch between the JS UA string
# and the TLS/HTTP2 fingerprint is a primary Cloudflare bot-detection signal.
# Windows 10 (NT 10.0) is weighted heavily: ~72% of global desktop traffic.
CHROME_UA_POOL = (
    # Chrome 136 — May 2026 stable, Windows 10 (3× weighted)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    # Chrome 136, macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    # Chrome 135 — April 2026 stable, Windows 10 (2× weighted)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    # Chrome 135, macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
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


# ---------------------------------------------------------------------------
# Redis-backed cross-worker session rate limiter
# ---------------------------------------------------------------------------

# Module-level async Redis client — created once per event loop so every
# guarded_goto() reuses the same connection pool instead of opening a new
# TCP connection on every call.
_aioredis_slot_client = None


async def _get_slot_redis():
    global _aioredis_slot_client
    if _aioredis_slot_client is None:
        import redis.asyncio as aioredis
        from core.config import scraper_settings
        _aioredis_slot_client = aioredis.from_url(
            scraper_settings.redis_url, decode_responses=True
        )
    return _aioredis_slot_client


async def acquire_session_request_slot(rate_limit_key: str | None) -> None:
    """Enforce per-exit-node RPM limit using a Redis sorted-set sliding window.

    ``rate_limit_key`` should be the active proxy URL so the RPM budget is
    shared across all sessions routed through the same exit-node IP.  Falls
    back to session-key-based limiting when no proxy is active.  Keying on
    the proxy URL prevents two concurrent tasks pinned to the same IP from
    each claiming the full RPM allowance (which would double the effective
    per-IP rate and trigger CF challenges).

    Cross-worker safe: all Celery workers share the same Redis state, so the
    configured RPM is honoured globally rather than per-process.
    """
    if not rate_limit_key:
        return
    runtime = get_runtime_settings()
    max_rpm = max(1, runtime.cf_bypass_max_rpm_residential)
    slot_key = "ratelimit:session:" + hashlib.sha1(rate_limit_key.encode()).hexdigest()[:20]
    window_s = 60.0
    now = time.time()
    deadline = now + window_s

    try:
        r = await _get_slot_redis()
        while True:
            pipe = r.pipeline()
            pipe.zremrangebyscore(slot_key, 0, now - window_s)
            pipe.zcard(slot_key)
            results = await pipe.execute()
            count = results[1]
            if count < max_rpm:
                score = now
                member = f"{now:.6f}-{random.getrandbits(32)}"
                await r.zadd(slot_key, {member: score})
                await r.expire(slot_key, 120)
                return
            oldest_raw = await r.zrange(slot_key, 0, 0, withscores=True)
            if oldest_raw:
                oldest_ts = oldest_raw[0][1]
                sleep_s = max(0.1, (oldest_ts + window_s) - time.time())
            else:
                sleep_s = window_s / max_rpm
            sleep_s += random.uniform(0.05, 0.3)
            await asyncio.sleep(min(sleep_s, 5.0))
            now = time.time()
            if now > deadline:
                return
    except Exception:
        # Redis unavailable — fall back to a proportional in-process sleep.
        await asyncio.sleep(window_s / max(1, max_rpm) + random.uniform(0.1, 0.5))


def _generate_bezier_path(start: tuple[float, float], end: tuple[float, float], steps: int) -> list[tuple[float, float]]:
    x0, y0 = start
    x3, y3 = end
    mx = (x0 + x3) / 2
    my = (y0 + y3) / 2
    dist = math.hypot(x3 - x0, y3 - y0)
    
    offset_scale = dist * 0.15
    x1 = x0 + (x3 - x0) * 0.25 + random.uniform(-offset_scale, offset_scale)
    y1 = y0 + (y3 - y0) * 0.25 + random.uniform(-offset_scale, offset_scale)
    x2 = x0 + (x3 - x0) * 0.75 + random.uniform(-offset_scale, offset_scale)
    y2 = y0 + (y3 - y0) * 0.75 + random.uniform(-offset_scale, offset_scale)
    
    path = []
    for i in range(1, steps + 1):
        x = i / steps
        t = 1.0 - (1.0 - x) ** 3  # Cubic ease-out
        u = 1.0 - t
        px = (u**3)*x0 + 3*(u**2)*t*x1 + 3*u*(t**2)*x2 + (t**3)*x3
        py = (u**3)*y0 + 3*(u**2)*t*y1 + 3*u*(t**2)*y2 + (t**3)*y3
        
        jitter_x = random.uniform(-0.5, 0.5) if i < steps else 0
        jitter_y = random.uniform(-0.5, 0.5) if i < steps else 0
        path.append((px + jitter_x, py + jitter_y))
    return path


async def human_click(page, selector: str) -> None:
    element = await page.wait_for_selector(selector, state="visible")
    box = await element.bounding_box()
    if not box:
        await element.click()
        return
    target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
    current = await page.evaluate("() => ({ x: window.__mouseX, y: window.__mouseY })")

    start_x = current.get("x")
    start_y = current.get("y")
    if start_x is None or start_y is None:
        # Fallback: pick a random point in the upper-left quarter of the
        # viewport (typical idle cursor position for a real user).
        viewport = await page.evaluate(
            "() => ({ w: window.innerWidth, h: window.innerHeight })"
        )
        start_x = random.uniform(viewport["w"] * 0.1, viewport["w"] * 0.4)
        start_y = random.uniform(viewport["h"] * 0.1, viewport["h"] * 0.4)

    steps = random.randint(12, 22)
    path = _generate_bezier_path((start_x, start_y), (target_x, target_y), steps)
    for px, py in path:
        await page.mouse.move(px, py)
        await asyncio.sleep(random.uniform(0.008, 0.025))

    await page.evaluate(f"() => {{ window.__mouseX = {target_x}; window.__mouseY = {target_y}; }}")
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.click(target_x, target_y)


async def initialize_mouse_position(page) -> None:
    """Seed the in-page mouse position tracker from the viewport centre.

    Call this immediately after every ``page.goto()`` / ``page.reload()`` so
    that the first ``human_click()`` always has a realistic start position
    rather than a hardcoded fallback.  Cloudflare's behavioural analysis
    tracks mouse entry into the page; a cursor that appears at coordinate
    (0,0) and moves to a target in one step is a bot pattern.
    """
    try:
        viewport = await page.evaluate(
            "() => ({ w: window.innerWidth, h: window.innerHeight })"
        )
        # Initialise near the horizontal centre, slightly above vertical centre
        # — a typical resting position for a desktop user who just loaded a page.
        cx = viewport["w"] * random.uniform(0.35, 0.65)
        cy = viewport["h"] * random.uniform(0.2, 0.45)
        await page.evaluate(
            f"() => {{ window.__mouseX = {cx}; window.__mouseY = {cy}; }}"
        )
        # Also physically move the mouse to that position so Playwright's
        # internal cursor state matches the JS variable.
        await page.mouse.move(cx, cy)
    except Exception:
        pass


async def human_scroll(page, direction: str = "down", steps: int | None = None) -> None:
    viewport = await page.evaluate("() => ({ h: window.innerHeight, total: document.body.scrollHeight })")
    viewport_h = int(viewport.get("h", 800))
    total = int(viewport.get("total", 0))
    runtime = get_runtime_settings()
    if steps is None:
        steps = random.randint(runtime.cf_bypass_scroll_steps_min, runtime.cf_bypass_scroll_steps_max)
    
    for _ in range(max(1, steps)):
        current_y = int(await page.evaluate("() => window.scrollY"))
        if direction == "down" and current_y + viewport_h >= total - 50:
            break
        if direction == "up" and current_y <= 0:
            break

        # Scroll in human-like increments relative to viewport height
        increment = random.uniform(viewport_h * 0.4, viewport_h * 0.8)
        if direction == "up":
            increment = -increment

        # Perform scroll in micro-ticks
        ticks = random.randint(3, 7)
        for t in range(ticks):
            tick_scroll = increment / ticks
            tick_scroll += random.uniform(-10, 10)
            await page.mouse.wheel(0, tick_scroll)
            await asyncio.sleep(random.uniform(0.01, 0.03))

        await asyncio.sleep(random.uniform(0.15, 0.55))


def get_consistent_browser_profile(
    session_key: str | None = None,
    proxy_country: str | None = None,
) -> dict[str, object]:
    """Return a stable browser profile for the given session.

    Seeded from ``session_key`` so the same session always produces the same
    UA, viewport, locale, and timezone. This prevents fingerprint drift across
    retries and multi-page navigations within one scrape, which bot-detection
    systems record per-IP and flag as anomalous.

    ``proxy_country`` is used to align locale and timezone with the proxy IP's
    geographic origin. Mismatched locale/TZ vs. IP country is a primary CF
    detection signal. Falls back to ``"US"`` when not provided.

    Falls back to a random (non-seeded) profile when ``session_key`` is None.
    """
    # Derive a stable seed from the session key so the same session always
    # produces the same profile. Use md5 purely for speed — not security.
    if session_key:
        seed = int(hashlib.md5(session_key.encode("utf-8")).hexdigest(), 16) % (2 ** 32)
        rng = random.Random(seed)
    else:
        rng = random.Random()

    # Select a UA from the Chrome pool. With Playwright Chromium the UA string
    # and TLS fingerprint are both Chrome-based, so setting user_agent via
    # new_context() is safe and required to mask the "HeadlessChrome" token
    # that Playwright injects in headless mode.
    user_agent = rng.choice(CHROME_UA_POOL)

    # Comprehensive country → (locale, timezone) map.
    # Covers the most common residential proxy geographies.
    country_map: dict[str, tuple[str, str]] = {
        "US": ("en-US", "America/New_York"),
        "GB": ("en-GB", "Europe/London"),
        "DE": ("de-DE", "Europe/Berlin"),
        "FR": ("fr-FR", "Europe/Paris"),
        "CA": ("en-CA", "America/Toronto"),
        "AU": ("en-AU", "Australia/Sydney"),
        "NL": ("nl-NL", "Europe/Amsterdam"),
        "SE": ("sv-SE", "Europe/Stockholm"),
        "PL": ("pl-PL", "Europe/Warsaw"),
        "IT": ("it-IT", "Europe/Rome"),
        "ES": ("es-ES", "Europe/Madrid"),
        "BR": ("pt-BR", "America/Sao_Paulo"),
        "JP": ("ja-JP", "Asia/Tokyo"),
        "IN": ("en-IN", "Asia/Kolkata"),
        "SG": ("en-SG", "Asia/Singapore"),
        "MX": ("es-MX", "America/Mexico_City"),
        "CH": ("de-CH", "Europe/Zurich"),
        "AT": ("de-AT", "Europe/Vienna"),
        "NO": ("nb-NO", "Europe/Oslo"),
        "DK": ("da-DK", "Europe/Copenhagen"),
        "FI": ("fi-FI", "Europe/Helsinki"),
        "NZ": ("en-NZ", "Pacific/Auckland"),
        "IE": ("en-IE", "Europe/Dublin"),
        "ZA": ("en-ZA", "Africa/Johannesburg"),
    }
    country_code = (proxy_country or "US").upper().strip()
    locale, timezone = country_map.get(country_code, ("en-US", "America/New_York"))

    viewport = rng.choice(
        (
            {"width": 1920, "height": 1080},
            {"width": 1440, "height": 900},
            {"width": 1366, "height": 768},
            {"width": 1536, "height": 864},
            {"width": 1280, "height": 800},
            {"width": 1600, "height": 900},
        )
    )
    return {
        "locale": locale,
        "timezone_id": timezone,
        "viewport": viewport,
        "user_agent": user_agent,
        "extra_http_headers": {
            "Accept-Language": f"{locale},en;q=0.9",
        },
    }


async def verify_fingerprint(page) -> dict[str, bool]:
    """Evaluate key browser fingerprint signals in the page context.

    Returns a dict of signal name → bool where ``True`` means the signal
    looks like a real browser (pass) and ``False`` means it looks like
    an automation artifact (fail).

    Designed for Playwright Chromium — window.chrome is expected present.
    Call this after ``wait_for_content`` and log any failures.
    """
    return await page.evaluate(
        """() => ({
            webdriver_hidden: navigator.webdriver === undefined || navigator.webdriver === false,
            plugins_present: navigator.plugins.length > 0,
            languages_present: !!(navigator.languages && navigator.languages.length > 0),
            chrome_present: typeof window.chrome !== 'undefined',
            no_webdriver_attr: !document.documentElement.getAttribute('webdriver'),
            canvas_functional: (() => { try { const c = document.createElement('canvas'); c.getContext('2d'); return true; } catch(e) { return false; } })(),
            screen_realistic: screen.width >= 1024 && screen.height >= 768,
            has_history: typeof window.history !== 'undefined' && window.history.length >= 1,
            no_cdc_leak: typeof window.cdc_adoQpoasnfa76pfcZLmcfl_Array === 'undefined',
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


async def wait_for_cf_resolution(page, *, max_wait_s: float = 15.0) -> bool:
    """Poll until the CF challenge clears, injecting behavioral signals.

    Scrolls the page every ~3 s so Cloudflare's Turnstile widget sees
    user-like activity instead of a static headless page.  A page that
    generates no events during the challenge window is a strong bot signal.

    Returns True if the challenge resolved within ``max_wait_s``, False if
    still present at timeout.
    """
    steps = max(1, int(max_wait_s / 0.5))
    for i in range(steps):
        await asyncio.sleep(0.5)
        if i % 6 == 0:  # every ~3 s
            try:
                await human_scroll(page, direction="down", steps=1)
            except Exception:
                pass
        if not await check_for_cf_challenge(page):
            return True
    return False


async def check_for_cf_challenge(page) -> bool:
    """Return True if the page is still showing any Cloudflare challenge.

    This catches modern Turnstile / Managed Challenge pages which are
    full-size (bypassing the byte-count heuristic in ``wait_for_content``)
    but still block the real content behind a challenge widget.

    Checks both the classic JS challenge selectors AND the modern
    Turnstile iframe pattern.
    """
    # Classic JS challenge / browser verification
    classic = await page.query_selector(
        "#challenge-form, #challenge-running, .cf-browser-verification, "
        ".cf-challenge-running, #cf-challenge-hcaptcha-container"
    )
    if classic:
        return True
    # Modern Turnstile / Managed Challenge embedded iframe
    turnstile = await page.query_selector(
        "iframe[src*='challenges.cloudflare.com'], "
        "iframe[src*='cloudflare.com/cdn-cgi/challenge-platform']"
    )
    if turnstile:
        return True
    # Title-based detection for "Just a moment..." interstitials
    title = (await page.title() or "").lower()
    if "just a moment" in title or "checking your browser" in title:
        return True
    return False


def is_cloudflare_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in ipaddress.ip_network(network) for network in _CF_RANGES)


# ---------------------------------------------------------------------------
# In-process sliding-window rate limiter (lightweight / test-friendly)
# ---------------------------------------------------------------------------

class SessionRateLimiter:
    """Simple in-process sliding-window rate limiter.

    Tracks request timestamps in memory and enforces ``max_rpm`` per minute.
    Suitable for single-worker testing and as a lightweight fallback when
    Redis is unavailable.  For cross-worker rate limiting use
    ``acquire_session_request_slot`` (Redis-backed).
    """

    def __init__(self, max_rpm: int = 20) -> None:
        self.max_rpm = max(1, max_rpm)
        self.timestamps: list[float] = []

    async def acquire(self) -> None:
        """Wait until a request slot is available within the RPM limit."""
        window = 60.0
        while True:
            now = time.time()
            # Evict timestamps outside the sliding window.
            self.timestamps = [t for t in self.timestamps if now - t < window]
            if len(self.timestamps) < self.max_rpm:
                self.timestamps.append(now)
                return
            # Sleep until the oldest timestamp falls outside the window.
            oldest = self.timestamps[0]
            sleep_s = max(0.05, (oldest + window) - now)
            sleep_s += random.uniform(0.02, 0.1)  # jitter
            await asyncio.sleep(min(sleep_s, 5.0))


# ---------------------------------------------------------------------------
# Backward-compatible re-exports
# ---------------------------------------------------------------------------
# ProxySessionManager was previously defined in this module. It has been moved
# to core.proxy for better separation of concerns. Re-exported here so that
# existing imports (e.g. in tests) continue to work without changes.
from core.proxy import ProxySessionManager  # noqa: E402
