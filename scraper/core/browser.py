"""Camoufox browser launch with stealth config and proxy support."""

import asyncio
import hashlib
import logging
import math
import os
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator
from urllib.parse import unquote, urlsplit

from playwright.async_api import BrowserContext
from camoufox.async_api import AsyncCamoufox

from core.cf_bypass import acquire_session_request_slot, get_consistent_browser_profile, human_delay_value
from core.config import scraper_settings
from core.proxy import get_random_proxy
from core.system_settings import get_runtime_settings

logger = logging.getLogger(__name__)
_HEAVY_MEDIA_URL_MARKERS = (
    ".m3u8",
    ".mp4",
    ".webm",
    ".m4s",
    ".ts",
    ".mp3",
    ".aac",
    ".mov",
    ".mkv",
)
_BLOCKED_URL_PATTERNS = (
    "**/*google-analytics*",
    "**/*googlesyndication*",
    "**/*doubleclick*",
    "**/*facebook.com/tr*",
    "**/*hotjar*",
    "**/*segment.io*",
    "**/*mixpanel*",
    "**/*sentry.io*",
    "**/*cloudflareinsights.com*",
)


@dataclass
class BrowserTelemetry:
    """Best-effort transfer telemetry for quota observability."""

    response_header_bytes: int = 0
    response_body_bytes_est: int = 0
    response_count: int = 0
    geoip_enabled: bool = False

    @property
    def total_bytes_est(self) -> int:
        return self.response_header_bytes + self.response_body_bytes_est


def _blocked_resource_types() -> set[str]:
    """Return resource types to block for bandwidth-heavy scraping flows."""
    runtime = get_runtime_settings()
    blocked: set[str] = set()
    if runtime.scraper_block_resource_images:
        blocked.add("image")
    if runtime.scraper_block_resource_media:
        blocked.add("media")
        blocked.add("texttrack")
    if runtime.scraper_block_resource_fonts:
        blocked.add("font")
    return blocked


# ---------------------------------------------------------------------------
# Runtime config
# ---------------------------------------------------------------------------

def _resolve_headless_mode() -> bool | str:
    """Resolve effective headless mode from env and display availability.
    
    Returns True for headless, False for headed, or "virtual" if headed is
    requested but no display server is available.
    """
    requested_headless = os.environ.get("BROWSER_HEADLESS", "true").lower() != "false"
    if requested_headless:
        return True
        
    display = os.environ.get("DISPLAY", "").strip()
    if not display:
        # Camoufox virtual display is Linux-only. On Windows/macOS, preserve
        # true headed mode when explicitly requested.
        if os.name == "nt":
            return False
        logger.warning(
            "BROWSER_HEADLESS=false but DISPLAY is unset; fallback to headless=virtual"
        )
        return "virtual"
    return False


def _resolve_camoufox_geoip_enabled(*, has_proxy: bool) -> bool:
    """Resolve whether Camoufox GeoIP should be enabled.

    With proxies, Camoufox recommends GeoIP enabled for fingerprint coherence.
    Allow explicit env override; otherwise default to enabled when proxying.
    """
    if has_proxy:
        # Always enable GeoIP for proxied sessions to avoid Camoufox proxy leak warnings
        # and keep locale/timezone behavior coherent with residential proxy routing.
        return True
    raw = os.environ.get("CAMOUFOX_GEOIP", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _parse_attempt_from_session_key(session_key: str | None) -> int:
    """Extract integer attempt marker from a session key."""
    if not session_key:
        return 0
    marker = "attempt:"
    idx = session_key.rfind(marker)
    if idx < 0:
        return 0
    raw = session_key[idx + len(marker):].split("|", 1)[0].strip()
    try:
        parsed = int(raw)
    except ValueError:
        return 0
    return parsed if parsed >= 0 else 0


async def human_delay(min_s: float = 2.0, max_s: float = 8.0) -> None:
    """Sleep for a random duration to mimic human behaviour.

    Args:
        min_s: Minimum delay in seconds.
        max_s: Maximum delay in seconds.
    """
    runtime = get_runtime_settings()
    resolved_min = max(0.0, max(min_s, runtime.scraper_human_delay_min_seconds))
    resolved_max = max(resolved_min, max(max_s, runtime.scraper_human_delay_max_seconds))
    value = human_delay_value()
    if value < resolved_min:
        value = resolved_min
    if value > resolved_max:
        value = resolved_max
    await asyncio.sleep(value)


async def wait_for_content(
    page,
    min_bytes: int | None = None,
    timeout_s: float | None = None,
    poll_interval_s: float | None = None,
) -> bool:
    """Poll until the page HTML is large enough to contain real content.

    Cloudflare challenge pages are tiny (< 600 bytes). Real channel pages
    are > 50 KB. This helper waits up to ``timeout_s`` seconds for the
    page content to grow beyond ``min_bytes``, indicating the CF challenge
    has been resolved and the real page has loaded.

    When parameters are ``None`` (the default), values are sourced from
    runtime settings.  Callers may pass explicit values to override.
    """
    runtime = get_runtime_settings()
    min_bytes = min_bytes if min_bytes is not None else runtime.scraper_content_wait_min_bytes
    timeout_s = timeout_s if timeout_s is not None else runtime.scraper_content_wait_timeout_seconds
    poll_interval_s = poll_interval_s if poll_interval_s is not None else runtime.scraper_content_wait_poll_seconds
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
    """Launch a Camoufox browser context with stealth flags.

    When ``BROWSER_HEADLESS=false`` is set in the environment, the browser
    launches in headed mode.

    Yields:
        A configured BrowserContext ready for scraping.
    """
    attempt = _parse_attempt_from_session_key(session_key)
    proxy = get_random_proxy()
    
    headless = _resolve_headless_mode()
    proxy_settings = _parse_proxy_settings(proxy)

    logger.debug(
        "Launching browser: headless=%s display=%s attempt=%d proxy_server=%s",
        headless,
        os.environ.get("DISPLAY", ""),
        attempt,
        proxy_settings.get("server"),
    )

    geoip_enabled = _resolve_camoufox_geoip_enabled(has_proxy=bool(proxy_settings.get("server")))
    if telemetry is not None:
        telemetry.geoip_enabled = geoip_enabled

    profile = get_consistent_browser_profile()
    target_os = "windows" if os.name == "nt" else "linux"
    async with AsyncCamoufox(
        headless=headless,
        proxy=proxy_settings,
        geoip=geoip_enabled,
        os=target_os,
    ) as browser:
        context: BrowserContext = await browser.new_context(
            viewport=profile["viewport"],
            service_workers="block",
            permissions=["geolocation"],
            locale=str(profile["locale"]),
            timezone_id=str(profile["timezone_id"]),
        )
        blocked_types = _blocked_resource_types()
        if blocked_types:
            async def _route_guard(route) -> None:
                request = route.request
                request_url = request.url.lower()
                if request.resource_type in blocked_types:
                    await route.abort()
                    return
                if any(marker in request_url for marker in _HEAVY_MEDIA_URL_MARKERS):
                    await route.abort()
                    return
                await route.continue_()

            await context.route("**/*", _route_guard)
        async def _abort_route(route) -> None:
            await route.abort()

        for pattern in _BLOCKED_URL_PATTERNS:
            await context.route(pattern, _abort_route)

        if telemetry is not None:
            async def _accumulate_response(response) -> None:
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

            def _on_response(response) -> None:
                asyncio.create_task(_accumulate_response(response))

            context.on("response", _on_response)
        if session_key:
            await context.set_extra_http_headers(
                {
                    "X-KA-Session": hashlib.sha1(session_key.encode("utf-8")).hexdigest()[:12],
                }
            )

        try:
            yield context
        finally:
            await context.close()


def _parse_proxy_settings(proxy_url: str) -> dict[str, str]:
    """Convert an env proxy URL into Playwright proxy settings."""
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


async def guarded_goto(page, url: str, *, session_key: str | None, **kwargs):
    """Throttle per-session request rate before navigation."""
    await acquire_session_request_slot(session_key)
    return await page.goto(url, **kwargs)
