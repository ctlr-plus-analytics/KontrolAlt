"""Patchright browser launch with stealth config and proxy support."""

import asyncio
import hashlib
import logging
import os
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator
from urllib.parse import unquote, urlsplit

from patchright.async_api import async_playwright, Browser, BrowserContext, Page

from core.config import scraper_settings
from core.proxy import build_session_proxy, get_random_proxy
from core.system_settings import get_runtime_settings

logger = logging.getLogger(__name__)


@dataclass
class BrowserTelemetry:
    """Best-effort transfer telemetry for quota observability."""

    response_header_bytes: int = 0
    response_body_bytes_est: int = 0
    response_count: int = 0

    @property
    def total_bytes_est(self) -> int:
        return self.response_header_bytes + self.response_body_bytes_est

# ---------------------------------------------------------------------------
# Runtime config
# ---------------------------------------------------------------------------

def _resolve_headless_mode() -> bool:
    """Resolve effective headless mode from env and display availability."""
    requested_headless = os.environ.get("BROWSER_HEADLESS", "true").lower() != "false"
    display = os.environ.get("DISPLAY", "").strip()

    # Never allow headed Chromium without a display server.
    if not requested_headless and not display:
        logger.warning(
            "BROWSER_HEADLESS=false but DISPLAY is unset; forcing headless=true"
        )
        return True
    return requested_headless

# ---------------------------------------------------------------------------
# 10 realistic Chrome user agents (Chrome 120–124, Windows + Mac)
# ---------------------------------------------------------------------------
_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------------------------
# Deep stealth init script — injected before page content loads.
# Patches the most common Cloudflare bot fingerprinting signals.
# ---------------------------------------------------------------------------
_STEALTH_SCRIPT = """
// --- navigator.webdriver ---
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// --- navigator.plugins (non-empty array) ---
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const p = {0: {name:'Chrome PDF Plugin'}, 1: {name:'Chrome PDF Viewer'}, 2: {name:'Native Client'}, length: 3};
        return p;
    }
});

// --- navigator.languages ---
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

// --- navigator.permissions.query spoof (CF checks notification/clipboard) ---
if (navigator.permissions) {
    const origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (parameters) => {
        if (parameters.name === 'notifications' || parameters.name === 'clipboard-read') {
            return Promise.resolve({state: 'prompt', onchange: null});
        }
        return origQuery(parameters);
    };
}

// --- window.chrome (full object real browsers expose) ---
window.chrome = {
    app: {isInstalled: false, InstallState: {DISABLED:'a',INSTALLED:'b',NOT_INSTALLED:'c'}, RunningState: {CANNOT_RUN:'a',READY_TO_RUN:'b',RUNNING:'c'}},
    runtime: {OnInstalledReason: {}, OnRestartRequiredReason: {}, PlatformArch: {}, PlatformNaClArch: {}, PlatformOs: {}, RequestUpdateCheckStatus: {}},
    webstore: {onInstallStageChanged: {}, onDownloadProgress: {}},
    csi: function() {},
    loadTimes: function() {},
};

// --- Canvas 2D noise (subtle pixel-level randomisation) ---
(function() {
    const origGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
        const ctx = origGetContext.call(this, type, ...args);
        if (ctx && type === '2d') {
            const origFillText = ctx.fillText.bind(ctx);
            ctx.fillText = function(...a) {
                ctx.globalAlpha = 0.9999 + Math.random() * 0.0001;
                return origFillText(...a);
            };
        }
        return ctx;
    };
})();

// --- WebGL vendor / renderer spoof ---
(function() {
    const origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Intel Inc.';
        if (param === 37446) return 'Intel Iris OpenGL Engine';
        return origGetParam.call(this, param);
    };
    try {
        const origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {
            if (param === 37445) return 'Intel Inc.';
            if (param === 37446) return 'Intel Iris OpenGL Engine';
            return origGetParam2.call(this, param);
        };
    } catch(e) {}
})();

// --- AudioContext fingerprint spoof ---
(function() {
    try {
        const origCreateOscillator = AudioContext.prototype.createOscillator;
        AudioContext.prototype.createOscillator = function() {
            const osc = origCreateOscillator.call(this);
            osc.frequency.value += Math.random() * 0.0001;
            return osc;
        };
    } catch(e) {}
})();

// --- Outer dimensions (headless reports 0x0 without this) ---
if (window.outerWidth === 0) Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth});
if (window.outerHeight === 0) Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 88});
"""


def get_random_user_agent() -> str:
    """Return a randomly selected user agent string."""
    return random.choice(_USER_AGENTS)


def build_session_id(key: str) -> str:
    """Build a deterministic sticky-session id from a channel key."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"ka{digest[:12]}"


async def human_delay(min_s: float = 2.0, max_s: float = 8.0) -> None:
    """Sleep for a random duration to mimic human behaviour.

    Args:
        min_s: Minimum delay in seconds.
        max_s: Maximum delay in seconds.
    """
    runtime = get_runtime_settings()
    configured_min = runtime.scraper_human_delay_min_seconds
    configured_max = runtime.scraper_human_delay_max_seconds
    resolved_min = max(0.0, max(min_s, configured_min))
    resolved_max = max(resolved_min, max_s, configured_max)
    await asyncio.sleep(random.uniform(resolved_min, resolved_max))


async def wait_for_content(
    page: Page,
    min_bytes: int = 5000,
    timeout_s: float = 20.0,
    poll_interval_s: float = 1.5,
) -> bool:
    """Poll until the page HTML is large enough to contain real content.

    Cloudflare challenge pages are tiny (< 600 bytes). Real channel pages
    are > 50 KB. This helper waits up to ``timeout_s`` seconds for the
    page content to grow beyond ``min_bytes``, indicating the CF challenge
    has been resolved and the real page has loaded.

    Args:
        page: The Patchright Page to check.
        min_bytes: Minimum HTML length that indicates real content.
        timeout_s: Maximum seconds to wait before giving up.
        poll_interval_s: Seconds between content-length checks.

    Returns:
        True if content reached ``min_bytes`` within ``timeout_s``.
        False if the page still looks like a challenge stub after the timeout.
    """
    runtime = get_runtime_settings()
    min_bytes = runtime.scraper_content_wait_min_bytes
    timeout_s = runtime.scraper_content_wait_timeout_seconds
    poll_interval_s = runtime.scraper_content_wait_poll_seconds
    elapsed = 0.0
    while elapsed < timeout_s:
        html = await page.content()
        if len(html) >= min_bytes:
            logger.debug(
                "wait_for_content: got %d bytes after %.1f s", len(html), elapsed
            )
            return True
        await asyncio.sleep(poll_interval_s)
        elapsed += poll_interval_s

    html = await page.content()
    logger.warning(
        "wait_for_content: timed out after %.1f s — page is only %d bytes "
        "(likely still a CF challenge stub)",
        timeout_s,
        len(html),
    )
    return False


@asynccontextmanager
async def launch_browser(
    *,
    session_key: str | None = None,
    telemetry: BrowserTelemetry | None = None,
) -> AsyncGenerator[BrowserContext, None]:
    """Launch a Patchright browser context with stealth flags.

    When ``BROWSER_HEADLESS=false`` is set in the environment, the browser
    launches in headed mode. In Docker this requires the celery process to be
    wrapped with ``xvfb-run -a`` so a virtual display is available.

    Yields:
        A configured BrowserContext ready for scraping.
    """
    base_proxy = get_random_proxy()
    session_minutes = scraper_settings.proxy_session_minutes
    platform_filter = scraper_settings.proxy_platform_filter
    session_id = build_session_id(session_key) if session_key else None
    proxy = (
        build_session_proxy(
            base_proxy=base_proxy,
            session_id=session_id,
            session_minutes=session_minutes,
            platform_filter=platform_filter,
        )
        if session_id
        else base_proxy
    )
    async with async_playwright() as pw:
        headless = _resolve_headless_mode()
        launch_args: dict[str, object] = {
            "headless": headless,
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-extensions",
                "--no-first-run",
                "--disable-default-apps",
            ],
        }

        launch_args["proxy"] = _parse_proxy_settings(proxy)

        logger.debug(
            "Launching browser: headless=%s display=%s proxy_server=%s",
            headless,
            os.environ.get("DISPLAY", ""),
            _parse_proxy_settings(proxy).get("server"),
        )

        browser: Browser = await pw.chromium.launch(**launch_args)

        context: BrowserContext = await browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/New_York",
            service_workers="block",
            extra_http_headers={
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-US,en;q=0.9",
            },
            # Provide real-looking geolocation matching the US proxy
            geolocation={"latitude": 40.7128, "longitude": -74.0060},
            permissions=["geolocation"],
        )

        if telemetry is not None:
            async def _accumulate_response(response: object) -> None:
                try:
                    headers = await response.all_headers()
                    header_size = sum(len(k) + len(v) + 4 for k, v in headers.items())
                    telemetry.response_header_bytes += header_size
                    content_length = headers.get("content-length")
                    if content_length:
                        telemetry.response_body_bytes_est += int(content_length)
                    telemetry.response_count += 1
                except Exception:
                    return

            def _on_response(response: object) -> None:
                asyncio.create_task(_accumulate_response(response))

            context.on("response", _on_response)

        # Inject stealth script before any page content
        await context.add_init_script(_STEALTH_SCRIPT)

        try:
            yield context
        finally:
            await context.close()
            await browser.close()


def _parse_proxy_settings(proxy_url: str) -> dict[str, str]:
    """Convert an env proxy URL into Patchright proxy settings."""
    parsed = urlsplit(proxy_url)
    if parsed.scheme and parsed.hostname:
        server = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port is not None:
            server = f"{server}:{parsed.port}"

        settings: dict[str, str] = {"server": server}
        if parsed.username:
            settings["username"] = unquote(parsed.username)
        if parsed.password:
            settings["password"] = unquote(parsed.password)
        return settings

    return {"server": proxy_url}
