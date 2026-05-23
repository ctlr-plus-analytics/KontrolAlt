"""Camoufox browser launch with stealth config and proxy support."""

import asyncio
import hashlib
import logging
import os
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator
from urllib.parse import unquote, urlsplit

from playwright.async_api import BrowserContext
from camoufox.async_api import AsyncCamoufox

from core.config import scraper_settings
from core.proxy import get_random_proxy
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
        logger.warning(
            "BROWSER_HEADLESS=false but DISPLAY is unset; fallback to headless=virtual"
        )
        return "virtual"
    return False


def build_session_id(key: str) -> str:
    """Build a deterministic sticky-session id from a channel key."""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    # Evomi session ids must be 6-10 chars; keep deterministic 10-char value.
    return f"ka{digest[:8]}"


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
    configured_min = runtime.scraper_human_delay_min_seconds
    configured_max = runtime.scraper_human_delay_max_seconds
    resolved_min = max(0.0, max(min_s, configured_min))
    resolved_max = max(resolved_min, max_s, configured_max)
    await asyncio.sleep(random.uniform(resolved_min, resolved_max))


async def wait_for_content(
    page,
    min_bytes: int = 5000,
    timeout_s: float = 20.0,
    poll_interval_s: float = 1.5,
) -> bool:
    """Poll until the page HTML is large enough to contain real content.

    Cloudflare challenge pages are tiny (< 600 bytes). Real channel pages
    are > 50 KB. This helper waits up to ``timeout_s`` seconds for the
    page content to grow beyond ``min_bytes``, indicating the CF challenge
    has been resolved and the real page has loaded.
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
    """Launch a Camoufox browser context with stealth flags.

    When ``BROWSER_HEADLESS=false`` is set in the environment, the browser
    launches in headed mode.

    Yields:
        A configured BrowserContext ready for scraping.
    """
    attempt = _parse_attempt_from_session_key(session_key)
    base_proxy = get_random_proxy()
    proxy = base_proxy
    
    headless = _resolve_headless_mode()
    proxy_settings = _parse_proxy_settings(proxy)

    logger.debug(
        "Launching browser: headless=%s display=%s attempt=%d proxy_server=%s",
        headless,
        os.environ.get("DISPLAY", ""),
        attempt,
        proxy_settings.get("server"),
    )

    async with AsyncCamoufox(
        headless=headless,
        proxy=proxy_settings,
        geoip=True,
    ) as browser:
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            service_workers="block",
            permissions=["geolocation"],
        )

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
