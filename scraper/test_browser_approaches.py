"""Research: compare Camoufox vs lighter alternatives for Substack and Rumble scraping.

Tests multiple approaches and reports CF bypass success, page size, and content
extraction counts for both target sites.

Run from the scraper/ directory:
    python test_browser_approaches.py                                # all Substack tests
    python test_browser_approaches.py --target rumble                # Rumble, no proxy
    python test_browser_approaches.py --target rumble --proxy auto   # Rumble, use first proxy from .env
    python test_browser_approaches.py --proxy "http://user:pass@host:port" --approach rumble-chromium-proxy
    python test_browser_approaches.py --approach chromium-headless   # headless Chromium, Substack

Available --approach values:
  Substack:
    httpx                    raw httpx (baseline)
    substack-api             /api/v1/publication/leaderboard (no auth)
    chromium                 Playwright Chromium, headed + webdriver patch
    chromium-headless        Playwright Chromium, headless=True
    chromium-headless-new    Playwright Chromium, headless="new" (Chrome native)
    firefox                  Playwright Firefox, headed, no Camoufox patches
    camoufox                 Camoufox (production baseline)

  Rumble (no proxy):
    rumble-httpx             raw httpx
    rumble-chromium          Chromium headed
    rumble-chromium-headless Chromium headless
    rumble-camoufox          Camoufox

  Rumble (with proxy — pass --proxy auto or --proxy <url>):
    rumble-chromium-proxy          Chromium headed + proxy
    rumble-chromium-headless-proxy Chromium headless + proxy
    rumble-camoufox-proxy          Camoufox + proxy (production-equivalent)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, unquote

# ---------------------------------------------------------------------------
# Target URLs
# ---------------------------------------------------------------------------

_SUBSTACK_TARGET = "https://substack.com/leaderboard/business/paid"
_SUBSTACK_API_URL = "https://substack.com/api/v1/publication/leaderboard?category=business&limit=25&page=0"
_SUBSTACK_HOME = "https://substack.com/"

_RUMBLE_TARGET = "https://rumble.com/c/DanBongino"
_RUMBLE_HOME = "https://rumble.com/"

_MIN_SUBSTACK_LINKS = 5
_MIN_RUMBLE_LINKS = 3
_SETTLE_S = 4.0

# ---------------------------------------------------------------------------
# Proxy helpers
# ---------------------------------------------------------------------------

def _canonicalize_proxy(proxy: str) -> str:
    """Normalize host:port:user:pass or user:pass@host:port to scheme://user:pass@host:port."""
    proxy = proxy.strip()
    if "://" in proxy:
        scheme, raw = proxy.split("://", 1)
    else:
        scheme, raw = "http", proxy
    if "@" in raw:
        # Already user:pass@host:port form
        return f"{scheme}://{raw}"
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, username, password = parts
        return f"{scheme}://{username}:{password}@{host}:{port}"
    # Unknown format — return as-is with scheme
    return f"{scheme}://{raw}"


def _load_first_proxy_from_env() -> str | None:
    """Read PROXY_LIST from .env (repo root) and return the first entry canonicalized, or None."""
    raw_list: str = ""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("PROXY_LIST="):
                raw_list = line[len("PROXY_LIST="):].strip().strip('"').strip("'")
                break
    if not raw_list:
        raw_list = os.environ.get("PROXY_LIST", "")
    first = raw_list.split(",")[0].strip()
    return _canonicalize_proxy(first) if first else None


def _parse_proxy_settings(proxy_url: str) -> dict[str, str]:
    """Convert a canonical proxy URL into a Playwright proxy dict."""
    canonical = _canonicalize_proxy(proxy_url)
    parsed = urlsplit(canonical)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port is not None:
        server = f"{server}:{parsed.port}"
    settings: dict[str, str] = {"server": server}
    if parsed.username:
        settings["username"] = unquote(parsed.username)
    if parsed.password:
        settings["password"] = unquote(parsed.password)
    return settings


def _proxy_label(proxy_url: str | None) -> str:
    if not proxy_url:
        return "none"
    canonical = _canonicalize_proxy(proxy_url)
    parsed = urlsplit(canonical)
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"


# ---------------------------------------------------------------------------
# Shared JS snippets
# ---------------------------------------------------------------------------

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        ]
    });
}
window.chrome = window.chrome || { runtime: {} };
"""

_CF_CHALLENGE_JS = """
() => {
    const s = ['#challenge-form','#challenge-running','.cf-browser-verification',
                '.cf-challenge-running','iframe[src*="challenges.cloudflare.com"]'];
    for (const sel of s) if (document.querySelector(sel)) return true;
    const t = (document.title || '').toLowerCase();
    return t.includes('just a moment') || t.includes('checking your browser');
}
"""

_COUNT_SUBSTACK_LINKS_JS = """
() => new Set(
    Array.from(document.querySelectorAll('a[href]'))
        .map(a => a.href.split('?')[0])
        .filter(h => h.includes('.substack.com') || h.includes('substack.com/@'))
).size
"""

_COUNT_RUMBLE_LINKS_JS = r"""
() => {
    const NAV = /rumble\.com\/(login|register|browse|shorts|videos|my-library|playlists|editor-picks)\b/;
    return new Set(
        Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href.split('?')[0])
            .filter(h => h.includes('rumble.com/') && !NAV.test(h)
                      && (h.includes('/v') || h.includes('/c/') || h.endsWith('.html'))
                      && !h.match(/rumble\.com\/($|#)/)
            )
    ).size;
}
"""

_FINGERPRINT_JS = """
() => ({
    webdriver: navigator.webdriver,
    plugins: navigator.plugins.length,
    languages: (navigator.languages || []).slice(0, 2),
    chrome: typeof window.chrome,
})
"""

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ApproachResult:
    name: str
    success: bool = False
    cf_challenged: bool = False
    http_status: int = 0
    page_bytes: int = 0
    link_count: int = 0
    duration_s: float = 0.0
    error: str = ""
    notes: list[str] = field(default_factory=list)

    @staticmethod
    def _safe(text: str) -> str:
        return text.encode("ascii", errors="replace").decode("ascii")

    def print_summary(self) -> None:
        status_icon = "PASS" if self.success else "FAIL"
        print(f"\n{'='*62}")
        print(f"  [{status_icon}]  {self.name}")
        print(f"{'='*62}")
        print(f"  Success       : {self.success}")
        print(f"  CF challenged : {self.cf_challenged}")
        if self.http_status:
            print(f"  HTTP status   : {self.http_status}")
        print(f"  Page bytes    : {self.page_bytes:,}")
        print(f"  Content links : {self.link_count}")
        print(f"  Duration      : {self.duration_s:.1f}s")
        if self.error:
            print(f"  Error         : {self._safe(self.error[:250])}")
        for note in self.notes:
            print(f"  Note          : {self._safe(note)}")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def _scroll_and_count(page, count_js: str, scrolls: int = 3, pause: float = 1.5) -> int:
    for _ in range(scrolls):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(pause)
    return await page.evaluate(count_js)


def _chromium_ua() -> str:
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )


async def _make_chromium_browser(pw, *, headless: bool, proxy_url: str | None = None):
    proxy_settings = _parse_proxy_settings(proxy_url) if proxy_url else None
    kwargs: dict = dict(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-first-run", "--disable-infobars"],
    )
    if proxy_settings:
        kwargs["proxy"] = proxy_settings
    return await pw.chromium.launch(**kwargs)


async def _make_chromium_context(browser, *, proxy_url: str | None = None):
    return await browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
        user_agent=_chromium_ua(),
    )


async def _rumble_navigate(page, result: ApproachResult) -> bool:
    """Pre-warm Rumble homepage, check for CF, then navigate to target channel.
    Returns True if channel page loaded without CF challenge."""
    await page.goto(_RUMBLE_HOME, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(3.0)
    if await page.evaluate(_CF_CHALLENGE_JS):
        result.cf_challenged = True
        result.notes.append("CF challenge on Rumble homepage")
        result.notes.append(f"Title: {await page.title()!r}")
        return False
    await page.goto(_RUMBLE_TARGET, wait_until="domcontentloaded", timeout=45_000)
    await asyncio.sleep(_SETTLE_S)
    html = await page.content()
    result.page_bytes = len(html)
    result.cf_challenged = await page.evaluate(_CF_CHALLENGE_JS)
    result.notes.append(f"Title: {await page.title()!r}")
    return not result.cf_challenged


# ---------------------------------------------------------------------------
# Substack: raw httpx
# ---------------------------------------------------------------------------

async def test_httpx() -> ApproachResult:
    import httpx
    result = ApproachResult(name="httpx (raw, no browser) — Substack")
    t0 = time.perf_counter()
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(_SUBSTACK_TARGET)
        result.http_status = resp.status_code
        body = resp.text
        result.page_bytes = len(body)
        result.cf_challenged = resp.status_code in (403, 503) or "just a moment" in body.lower()
        if resp.status_code == 200 and not result.cf_challenged:
            result.link_count = body.lower().count(".substack.com")
            result.success = result.link_count >= _MIN_SUBSTACK_LINKS
        result.notes.append(f"CF-Ray: {resp.headers.get('cf-ray', 'N/A')}")
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Substack: undocumented API
# ---------------------------------------------------------------------------

async def test_substack_api() -> ApproachResult:
    import httpx
    result = ApproachResult(name="Substack /api/v1/publication/leaderboard (httpx, no auth)")
    t0 = time.perf_counter()
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
            "Accept": "application/json",
            "Referer": "https://substack.com/",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(_SUBSTACK_API_URL)
        result.http_status = resp.status_code
        result.page_bytes = len(resp.content)
        result.notes.append(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                pubs = data.get("publications") or data.get("results") or (data if isinstance(data, list) else [])
                result.link_count = len(pubs)
                result.success = result.link_count >= _MIN_SUBSTACK_LINKS
                if result.success:
                    result.notes.append(f"Sample: {[p.get('name') or p.get('handle') for p in pubs[:3]]}")
            except Exception as e:
                result.notes.append(f"Parse error: {e} | preview: {resp.text[:200]}")
        else:
            result.cf_challenged = resp.status_code in (403, 503)
            result.notes.append(f"CF-Ray: {resp.headers.get('cf-ray', 'N/A')}")
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Substack: Playwright Chromium headed
# ---------------------------------------------------------------------------

async def test_playwright_chromium() -> ApproachResult:
    from playwright.async_api import async_playwright
    result = ApproachResult(name="Playwright Chromium, headed + webdriver patch — Substack")
    t0 = time.perf_counter()
    try:
        async with async_playwright() as pw:
            browser = await _make_chromium_browser(pw, headless=False)
            ctx = await _make_chromium_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(_STEALTH_JS)
            await page.goto(_SUBSTACK_HOME, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2.0)
            await page.goto(_SUBSTACK_TARGET, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(_SETTLE_S)
            html = await page.content()
            result.page_bytes = len(html)
            result.cf_challenged = await page.evaluate(_CF_CHALLENGE_JS)
            if not result.cf_challenged:
                result.link_count = await _scroll_and_count(page, _COUNT_SUBSTACK_LINKS_JS)
                result.success = result.link_count >= _MIN_SUBSTACK_LINKS
            result.notes.append(f"Title: {await page.title()!r}")
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
            await browser.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Substack: Playwright Chromium headless=True
# ---------------------------------------------------------------------------

async def test_chromium_headless() -> ApproachResult:
    from playwright.async_api import async_playwright
    result = ApproachResult(name="Playwright Chromium, headless=True + webdriver patch — Substack")
    t0 = time.perf_counter()
    try:
        async with async_playwright() as pw:
            browser = await _make_chromium_browser(pw, headless=True)
            ctx = await _make_chromium_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(_STEALTH_JS)
            await page.goto(_SUBSTACK_HOME, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2.0)
            await page.goto(_SUBSTACK_TARGET, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(_SETTLE_S)
            html = await page.content()
            result.page_bytes = len(html)
            result.cf_challenged = await page.evaluate(_CF_CHALLENGE_JS)
            if not result.cf_challenged:
                result.link_count = await _scroll_and_count(page, _COUNT_SUBSTACK_LINKS_JS)
                result.success = result.link_count >= _MIN_SUBSTACK_LINKS
            result.notes.append(f"Title: {await page.title()!r}")
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
            await browser.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Substack: Playwright Chromium headless="new"
# ---------------------------------------------------------------------------

async def test_chromium_headless_new() -> ApproachResult:
    from playwright.async_api import async_playwright
    result = ApproachResult(name='Playwright Chromium, headless="new" + webdriver patch — Substack')
    t0 = time.perf_counter()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--headless=new", "--no-first-run"],
            )
            ctx = await _make_chromium_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(_STEALTH_JS)
            await page.goto(_SUBSTACK_HOME, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2.0)
            await page.goto(_SUBSTACK_TARGET, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(_SETTLE_S)
            html = await page.content()
            result.page_bytes = len(html)
            result.cf_challenged = await page.evaluate(_CF_CHALLENGE_JS)
            if not result.cf_challenged:
                result.link_count = await _scroll_and_count(page, _COUNT_SUBSTACK_LINKS_JS)
                result.success = result.link_count >= _MIN_SUBSTACK_LINKS
            result.notes.append(f"Title: {await page.title()!r}")
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
            await browser.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Substack: Playwright Firefox
# ---------------------------------------------------------------------------

async def test_playwright_firefox() -> ApproachResult:
    from playwright.async_api import async_playwright
    result = ApproachResult(name="Playwright Firefox, headed, no Camoufox patches — Substack")
    t0 = time.perf_counter()
    try:
        async with async_playwright() as pw:
            browser = await pw.firefox.launch(headless=False)
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = await ctx.new_page()
            await page.add_init_script(_STEALTH_JS)
            await page.goto(_SUBSTACK_HOME, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2.0)
            await page.goto(_SUBSTACK_TARGET, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(_SETTLE_S)
            html = await page.content()
            result.page_bytes = len(html)
            result.cf_challenged = await page.evaluate(_CF_CHALLENGE_JS)
            if not result.cf_challenged:
                result.link_count = await _scroll_and_count(page, _COUNT_SUBSTACK_LINKS_JS)
                result.success = result.link_count >= _MIN_SUBSTACK_LINKS
            result.notes.append(f"Title: {await page.title()!r}")
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
            await browser.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Substack: Camoufox
# ---------------------------------------------------------------------------

async def test_camoufox() -> ApproachResult:
    result = ApproachResult(name="Camoufox (production baseline) — Substack")
    t0 = time.perf_counter()
    try:
        from camoufox.async_api import AsyncCamoufox
        headless = "virtual" if sys.platform == "linux" else False
        async with AsyncCamoufox(headless=headless, os="windows") as browser:
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = await ctx.new_page()
            await page.goto(_SUBSTACK_HOME, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(2.0)
            await page.goto(_SUBSTACK_TARGET, wait_until="domcontentloaded", timeout=45_000)
            await asyncio.sleep(_SETTLE_S)
            html = await page.content()
            result.page_bytes = len(html)
            result.cf_challenged = await page.evaluate(_CF_CHALLENGE_JS)
            if not result.cf_challenged:
                result.link_count = await _scroll_and_count(page, _COUNT_SUBSTACK_LINKS_JS)
                result.success = result.link_count >= _MIN_SUBSTACK_LINKS
            result.notes.append(f"Title: {await page.title()!r}")
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Rumble: raw httpx (no proxy)
# ---------------------------------------------------------------------------

async def test_rumble_httpx() -> ApproachResult:
    import httpx
    result = ApproachResult(name="httpx (raw, no browser) — Rumble")
    t0 = time.perf_counter()
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(_RUMBLE_TARGET)
        result.http_status = resp.status_code
        body = resp.text
        result.page_bytes = len(body)
        result.cf_challenged = resp.status_code in (403, 503) or "just a moment" in body.lower()
        if resp.status_code == 200 and not result.cf_challenged:
            result.link_count = len(re.findall(r"rumble\.com/[a-z0-9_-]+\.html", body))
            result.success = result.link_count >= _MIN_RUMBLE_LINKS
        result.notes.append(f"CF-Ray: {resp.headers.get('cf-ray', 'N/A')}")
        result.notes.append(f"Server: {resp.headers.get('server', 'N/A')}")
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Rumble: Chromium headed (no proxy)
# ---------------------------------------------------------------------------

async def test_rumble_chromium() -> ApproachResult:
    from playwright.async_api import async_playwright
    result = ApproachResult(name="Playwright Chromium, headed — Rumble (no proxy)")
    t0 = time.perf_counter()
    try:
        async with async_playwright() as pw:
            browser = await _make_chromium_browser(pw, headless=False)
            ctx = await _make_chromium_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(_STEALTH_JS)
            if await _rumble_navigate(page, result):
                result.link_count = await _scroll_and_count(page, _COUNT_RUMBLE_LINKS_JS, scrolls=2)
                result.success = result.link_count >= _MIN_RUMBLE_LINKS
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
            await browser.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Rumble: Chromium headless (no proxy)
# ---------------------------------------------------------------------------

async def test_rumble_chromium_headless() -> ApproachResult:
    from playwright.async_api import async_playwright
    result = ApproachResult(name="Playwright Chromium, headless=True — Rumble (no proxy)")
    t0 = time.perf_counter()
    try:
        async with async_playwright() as pw:
            browser = await _make_chromium_browser(pw, headless=True)
            ctx = await _make_chromium_context(browser)
            page = await ctx.new_page()
            await page.add_init_script(_STEALTH_JS)
            if await _rumble_navigate(page, result):
                result.link_count = await _scroll_and_count(page, _COUNT_RUMBLE_LINKS_JS, scrolls=2)
                result.success = result.link_count >= _MIN_RUMBLE_LINKS
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
            await browser.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Rumble: Camoufox (no proxy)
# ---------------------------------------------------------------------------

async def test_rumble_camoufox() -> ApproachResult:
    result = ApproachResult(name="Camoufox — Rumble (no proxy)")
    t0 = time.perf_counter()
    try:
        from camoufox.async_api import AsyncCamoufox
        headless = "virtual" if sys.platform == "linux" else False
        async with AsyncCamoufox(headless=headless, os="windows") as browser:
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = await ctx.new_page()
            if await _rumble_navigate(page, result):
                result.link_count = await _scroll_and_count(page, _COUNT_RUMBLE_LINKS_JS, scrolls=2)
                result.success = result.link_count >= _MIN_RUMBLE_LINKS
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Rumble + PROXY: Chromium headed
# ---------------------------------------------------------------------------

async def test_rumble_chromium_proxy(proxy_url: str) -> ApproachResult:
    from playwright.async_api import async_playwright
    result = ApproachResult(name=f"Playwright Chromium, headed + proxy — Rumble [{_proxy_label(proxy_url)}]")
    t0 = time.perf_counter()
    try:
        async with async_playwright() as pw:
            browser = await _make_chromium_browser(pw, headless=False, proxy_url=proxy_url)
            ctx = await _make_chromium_context(browser, proxy_url=proxy_url)
            page = await ctx.new_page()
            await page.add_init_script(_STEALTH_JS)
            if await _rumble_navigate(page, result):
                result.link_count = await _scroll_and_count(page, _COUNT_RUMBLE_LINKS_JS, scrolls=2)
                result.success = result.link_count >= _MIN_RUMBLE_LINKS
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
            await browser.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Rumble + PROXY: Chromium headless
# ---------------------------------------------------------------------------

async def test_rumble_chromium_headless_proxy(proxy_url: str) -> ApproachResult:
    from playwright.async_api import async_playwright
    result = ApproachResult(name=f"Playwright Chromium, headless=True + proxy — Rumble [{_proxy_label(proxy_url)}]")
    t0 = time.perf_counter()
    try:
        async with async_playwright() as pw:
            browser = await _make_chromium_browser(pw, headless=True, proxy_url=proxy_url)
            ctx = await _make_chromium_context(browser, proxy_url=proxy_url)
            page = await ctx.new_page()
            await page.add_init_script(_STEALTH_JS)
            if await _rumble_navigate(page, result):
                result.link_count = await _scroll_and_count(page, _COUNT_RUMBLE_LINKS_JS, scrolls=2)
                result.success = result.link_count >= _MIN_RUMBLE_LINKS
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
            await browser.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Rumble + PROXY: Camoufox (production-equivalent)
# ---------------------------------------------------------------------------

async def test_rumble_camoufox_proxy(proxy_url: str) -> ApproachResult:
    from camoufox.async_api import AsyncCamoufox
    proxy_settings = _parse_proxy_settings(proxy_url)
    result = ApproachResult(name=f"Camoufox + proxy — Rumble [{_proxy_label(proxy_url)}]")
    t0 = time.perf_counter()
    try:
        headless = "virtual" if sys.platform == "linux" else False
        async with AsyncCamoufox(headless=headless, os="windows", proxy=proxy_settings) as browser:
            ctx = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = await ctx.new_page()
            if await _rumble_navigate(page, result):
                result.link_count = await _scroll_and_count(page, _COUNT_RUMBLE_LINKS_JS, scrolls=2)
                result.success = result.link_count >= _MIN_RUMBLE_LINKS
            result.notes.append(f"Fingerprint: {await page.evaluate(_FINGERPRINT_JS)}")
            await ctx.close()
    except Exception as exc:
        result.error = str(exc)
    result.duration_s = time.perf_counter() - t0
    return result


# ---------------------------------------------------------------------------
# Approach registry
# ---------------------------------------------------------------------------

SUBSTACK_APPROACHES = {
    "httpx":                  (test_httpx,               False),
    "substack-api":           (test_substack_api,         False),
    "chromium":               (test_playwright_chromium,  False),
    "chromium-headless":      (test_chromium_headless,    False),
    "chromium-headless-new":  (test_chromium_headless_new, False),
    "firefox":                (test_playwright_firefox,   False),
    "camoufox":               (test_camoufox,             False),
}

RUMBLE_NO_PROXY = {
    "rumble-httpx":              (test_rumble_httpx,             False),
    "rumble-chromium":           (test_rumble_chromium,          False),
    "rumble-chromium-headless":  (test_rumble_chromium_headless, False),
    "rumble-camoufox":           (test_rumble_camoufox,          False),
}

RUMBLE_PROXY = {
    "rumble-chromium-proxy":          (test_rumble_chromium_proxy,          True),
    "rumble-chromium-headless-proxy": (test_rumble_chromium_headless_proxy, True),
    "rumble-camoufox-proxy":          (test_rumble_camoufox_proxy,          True),
}

ALL_APPROACHES = {**SUBSTACK_APPROACHES, **RUMBLE_NO_PROXY, **RUMBLE_PROXY}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare browser approaches for Substack and Rumble scraping.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--approach",
        choices=list(ALL_APPROACHES.keys()),
        default=None,
        help="Run a single named approach",
    )
    parser.add_argument(
        "--target",
        choices=["substack", "rumble", "rumble-proxy", "all"],
        default="substack",
        help=(
            "Which group to run: substack | rumble (no proxy) | "
            "rumble-proxy (needs --proxy) | all"
        ),
    )
    parser.add_argument(
        "--proxy",
        default=None,
        metavar="URL|auto",
        help=(
            'Proxy URL for proxy-enabled Rumble tests, or "auto" to read the '
            "first entry from PROXY_LIST in .env"
        ),
    )
    args = parser.parse_args()

    # Resolve proxy URL
    proxy_url: str | None = None
    if args.proxy:
        if args.proxy.lower() == "auto":
            proxy_url = _load_first_proxy_from_env()
            if not proxy_url:
                print("ERROR: --proxy auto specified but PROXY_LIST not found in .env or environment.")
                sys.exit(1)
            print(f"Using proxy from .env: {_proxy_label(proxy_url)}")
        else:
            proxy_url = args.proxy

    # Determine which approaches to run
    if args.approach:
        to_run = [args.approach]
        needs_proxy = ALL_APPROACHES[args.approach][1]
        if needs_proxy and not proxy_url:
            print(f"ERROR: approach '{args.approach}' requires --proxy <url|auto>")
            sys.exit(1)
    elif args.target == "rumble":
        to_run = list(RUMBLE_NO_PROXY.keys())
    elif args.target == "rumble-proxy":
        if not proxy_url:
            print("ERROR: --target rumble-proxy requires --proxy <url|auto>")
            sys.exit(1)
        to_run = list(RUMBLE_PROXY.keys())
    elif args.target == "all":
        to_run = list(SUBSTACK_APPROACHES.keys()) + list(RUMBLE_NO_PROXY.keys())
        if proxy_url:
            to_run += list(RUMBLE_PROXY.keys())
    else:
        to_run = list(SUBSTACK_APPROACHES.keys())

    print(f"\nTarget    : {args.target}")
    print(f"Proxy     : {_proxy_label(proxy_url) if proxy_url else 'none'}")
    print(f"Approaches: {', '.join(to_run)}")

    results: list[ApproachResult] = []
    for name in to_run:
        print(f"\n>>> Running: {name} ...")
        fn, needs_proxy = ALL_APPROACHES[name]
        if needs_proxy:
            result = await fn(proxy_url)
        else:
            result = await fn()
        result.print_summary()
        results.append(result)

    # Summary table
    print(f"\n{'='*62}")
    print("  FINAL SUMMARY")
    print(f"{'='*62}")
    print(f"  {'Approach':<48} {'Pass':>4}  {'CF':>3}  {'Links':>5}  {'Time':>6}")
    print(f"  {'-'*48} {'-'*4}  {'-'*3}  {'-'*5}  {'-'*6}")
    for r in results:
        mark = "YES" if r.success else ("ERR" if r.error else "NO")
        cf = "YES" if r.cf_challenged else "no"
        print(f"  {r.name[:48]:<48} {mark:>4}  {cf:>3}  {r.link_count:>5}  {r.duration_s:>5.1f}s")

    print()
    passing = [r for r in results if r.success]
    if passing:
        fastest = min(passing, key=lambda r: r.duration_s)
        print(f"Fastest passing : {fastest.name}  ({fastest.duration_s:.1f}s)")
        print(f"Passing total   : {len(passing)}/{len(results)}")
    else:
        print("No approach succeeded.")


if __name__ == "__main__":
    asyncio.run(main())
