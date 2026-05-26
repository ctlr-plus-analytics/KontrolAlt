"""Camoufox browser launch with stealth config and proxy support."""

import asyncio
import json
import logging
import math
import os
import random
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import unquote, urlsplit

from playwright.async_api import BrowserContext
from camoufox.async_api import AsyncCamoufox

from core.cf_bypass import (
    acquire_session_request_slot,
    check_for_cf_challenge,
    get_consistent_browser_profile,
    human_delay_value,
    human_scroll,
    initialize_mouse_position,
    verify_fingerprint,
)
from core.config import scraper_settings
from core.exceptions import CloudflareBlockError
from core.proxy import (
    get_weighted_proxy,
    get_random_proxy,
    extract_proxy_country,
    record_proxy_success,
    record_proxy_failure,
)
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
    # NOTE: cloudflareinsights.com is intentionally NOT blocked.
    # Blocking Cloudflare's own analytics beacon may lower the trust score
    # assigned by Cloudflare's bot management system on sites that also use
    # Cloudflare Web Analytics. The beacon is tiny and safe to allow.
)


@dataclass
class BrowserTelemetry:
    """Best-effort transfer telemetry for quota observability."""

    response_header_bytes: int = 0
    response_body_bytes_est: int = 0
    response_count: int = 0
    geoip_enabled: bool = False
    # The proxy URL actually selected for this browser launch.
    # Populated by launch_browser() so callers can observe which proxy was used.
    selected_proxy: str | None = None

    @property
    def total_bytes_est(self) -> int:
        return self.response_header_bytes + self.response_body_bytes_est


# ---------------------------------------------------------------------------
# Persistent browser state — storage_state save / load
# ---------------------------------------------------------------------------

_PROFILE_BASE_DIR = Path(
    os.environ.get("BROWSER_PROFILE_DIR", "/tmp/cf_profiles")
)


def _profile_dir(session_key: str | None) -> Path | None:
    """Return the persistent profile directory for a session key, or None."""
    if not session_key:
        return None
    import hashlib
    key_hash = hashlib.sha256(session_key.encode()).hexdigest()[:24]
    return _PROFILE_BASE_DIR / key_hash


def _load_browser_state(profile_dir: Path | None) -> dict | None:
    """Load Playwright storage state (cookies + localStorage) from disk.

    Returns the parsed JSON dict or None if no saved state exists.
    Never raises — storage state loss is non-fatal.
    """
    if profile_dir is None:
        return None
    state_file = profile_dir / "storage_state.json"
    if not state_file.exists():
        return None
    try:
        with state_file.open("r", encoding="utf-8") as fh:
            state = json.load(fh)
        logger.debug("Loaded browser state from %s", state_file)
        return state
    except Exception as exc:
        logger.debug("Could not load browser state from %s: %s", state_file, exc)
        return None


async def _save_browser_state(context: BrowserContext, profile_dir: Path | None) -> None:
    """Persist Playwright storage state (cookies + localStorage) to disk.

    Saving the cf_clearance cookie means subsequent scrapes of the same
    session avoid the Cloudflare challenge entirely until it expires.
    Never raises — storage state loss is non-fatal.
    """
    if profile_dir is None:
        return
    try:
        state = await context.storage_state()
        profile_dir.mkdir(parents=True, exist_ok=True)
        state_file = profile_dir / "storage_state.json"
        with state_file.open("w", encoding="utf-8") as fh:
            json.dump(state, fh)
        logger.debug("Saved browser state to %s", state_file)
    except Exception as exc:
        logger.debug("Could not save browser state to %s: %s", profile_dir, exc)


def _state_has_cf_clearance(state: dict | None) -> bool:
    """Return True if the loaded storage state contains a cf_clearance cookie."""
    if not state:
        return False
    for cookie in state.get("cookies", []):
        if cookie.get("name") == "cf_clearance":
            return True
    return False


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

    Production default is ``virtual`` (Xvfb on Linux servers), which provides
    the headed-mode rendering profile required to minimise Cloudflare detection
    while remaining compatible with headless server deployments.

    Environment values:
      ``virtual`` (default) — headed inside Xvfb on Linux; headed on Windows.
      ``false``             — fully headed (requires a display server / desktop).
      ``true``              — standard headless (highest detection risk; avoid).
    """
    raw = os.environ.get("BROWSER_HEADLESS", "virtual").strip().lower()

    if raw == "true":
        logger.warning(
            "BROWSER_HEADLESS=true: running in full headless mode — highest CF detection risk. "
            "Set BROWSER_HEADLESS=virtual (default) for production deployments."
        )
        return True

    if raw == "false":
        return False

    # Default: "virtual" — Xvfb on Linux, headed on Windows/macOS.
    if raw not in {"", "virtual"}:
        logger.warning(
            "Unknown BROWSER_HEADLESS=%r; using virtual browser mode by default.",
            raw,
        )

    # Default: "virtual" uses Xvfb on Linux; headed fallback elsewhere.
    if sys.platform != "linux":
        # Windows/macOS have no Xvfb; fall back to headed mode for dev machines.
        return False

    return "virtual"


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


async def _post_navigation_check(page, *, context_label: str = "") -> None:
    """Run post-navigation stealth diagnostics after a page loads.

    Logs fingerprint verification results and warns if a CF challenge is
    still present after ``wait_for_content`` reports the page as loaded.
    Called opportunistically — never raises; failures are debug-logged only.
    """
    try:
        fingerprint = await verify_fingerprint(page)
        issues = [k for k, v in fingerprint.items() if not v]
        if issues:
            logger.warning(
                "Fingerprint check failed for %s: %s", context_label, issues
            )
        else:
            logger.debug("Fingerprint check passed for %s", context_label)
    except Exception as exc:
        logger.debug("Fingerprint check error for %s: %s", context_label, exc)


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

    Production default is ``BROWSER_HEADLESS=virtual`` (Xvfb on Linux), which
    provides the headed-mode rendering profile required to minimise Cloudflare
    detection while remaining compatible with headless server deployments.

    Improvements over naive launch:
    * Health-weighted proxy selection — burned proxies receive proportionally
      less traffic; quarantined proxies are skipped entirely.
    * Storage-state persistence — cookies (incl. ``cf_clearance``) and
      localStorage are saved to disk keyed by session and restored on the
      next run, eliminating the cold-start Cloudflare challenge on repeat
      visits to the same channel.
    * ``extra_http_headers`` (Accept-Language) wired into the context so it
      always matches the proxy IP's geographic locale.
    * Proxy health feedback — CloudflareBlockError automatically penalises
      the selected proxy; clean exits recover its score.

    Yields:
        A configured BrowserContext ready for scraping.
    """
    attempt = _parse_attempt_from_session_key(session_key)
    proxy = get_weighted_proxy()

    headless = _resolve_headless_mode()
    proxy_settings = _parse_proxy_settings(proxy)

    # Extract country from proxy URL for fingerprint coherence.
    # Many residential providers encode country in the username (e.g. user-country-us).
    proxy_country = extract_proxy_country(proxy)

    logger.debug(
        "Launching browser: headless=%s display=%s attempt=%d proxy_server=%s proxy_country=%s",
        headless,
        os.environ.get("DISPLAY", ""),
        attempt,
        proxy_settings.get("server"),
        proxy_country or "unknown",
    )

    geoip_enabled = _resolve_camoufox_geoip_enabled(has_proxy=bool(proxy_settings.get("server")))
    if telemetry is not None:
        telemetry.geoip_enabled = geoip_enabled
        telemetry.selected_proxy = proxy

    # Build a deterministic fingerprint profile seeded from the session key so
    # the same session always presents the same viewport/locale across retries.
    # Proxy country is wired in so locale/timezone match the IP's geographic origin.
    profile = get_consistent_browser_profile(
        session_key=session_key,
        proxy_country=proxy_country,
    )

    # Load persisted storage state (cookies + localStorage) for this session.
    # If a valid cf_clearance cookie is present it will be restored, avoiding
    # a fresh Cloudflare challenge on every scrape run.
    pdir = _profile_dir(session_key)
    saved_state = _load_browser_state(pdir)
    has_clearance = _state_has_cf_clearance(saved_state)
    if has_clearance:
        logger.debug("launch_browser: restoring session with cf_clearance cookie")

    # Always spoof Windows — it accounts for ~72% of global desktop traffic.
    # Linux residential is <3% and is statistically unusual for a real user.
    # Running on a Linux Docker host but spoofing Windows is correct because
    # Camoufox patches the OS signals at the C++ engine level.
    _cf_blocked = False
    _cf_error_code: int | None = None
    async with AsyncCamoufox(
        headless=headless,
        proxy=proxy_settings,
        geoip=geoip_enabled,
        os="windows",
    ) as browser:
        context: BrowserContext = await browser.new_context(
            viewport=profile["viewport"],
            # service_workers omitted: real browsers use service workers.
            # Blocking them is both a bot-tell and can break CF's invisible
            # proof-of-work challenges that rely on service worker execution.
            permissions=["geolocation"],
            locale=str(profile["locale"]),
            timezone_id=str(profile["timezone_id"]),
            # Wire in Accept-Language so it matches the proxy country locale.
            # Previously this was computed but never passed — now correctly applied.
            extra_http_headers=dict(profile["extra_http_headers"]),
            # Restore prior session state (cookies + localStorage) if available.
            # Playwright merges this with any cookies set during the session.
            storage_state=saved_state,
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

        # NOTE: No custom headers injected here.
        # Previously, X-KA-Session was set via set_extra_http_headers().
        # That header is a non-standard bot fingerprint signal (real Firefox
        # never sends it) and has been removed. Session tracking remains
        # internal via Redis keys only.

        try:
            yield context
        except CloudflareBlockError as exc:
            _cf_blocked = True
            _cf_error_code = exc.error_code
            raise
        finally:
            # Persist storage state so cf_clearance and session cookies survive
            # across Celery task runs for the same session key.
            await _save_browser_state(context, pdir)
            # Record proxy health feedback so the weighted rotator learns which
            # proxies are healthy and which should be sidelined.
            if _cf_blocked:
                record_proxy_failure(proxy, _cf_error_code)
            else:
                record_proxy_success(proxy)
            await context.close()


async def is_cold_session(context: BrowserContext) -> bool:
    """Return True if the browser context has no cf_clearance cookie.

    Used by scrapers to decide whether to run a homepage warm-up visit before
    navigating directly to a deep channel URL.  A context loaded from a
    persisted storage state will typically return False.
    """
    try:
        cookies = await context.cookies()
        return not any(c.get("name") == "cf_clearance" for c in cookies)
    except Exception:
        return True


async def pre_warm_homepage(page, base_url: str, session_key: str | None = None) -> None:
    """Visit the site homepage briefly before navigating to a deep channel URL.

    Real users don't arrive at a channel URL (e.g. /channel/xyz/) with a blank
    cookie jar and zero browsing history on the domain.  This warm-up visit
    establishes a plausible entry-point, building minimal referrer/cookie
    history before the actual scrape navigation.

    Only call this when ``is_cold_session()`` returns True.  Sessions loaded
    from a persisted storage state already have cookies and do not need it.

    This is a best-effort helper — any exception is swallowed so warm-up
    failure never aborts the actual scrape.
    """
    try:
        logger.debug("pre_warm_homepage: visiting %s", base_url)
        await acquire_session_request_slot(session_key)
        await page.goto(base_url, wait_until="domcontentloaded", timeout=20_000)
        await human_delay(1.5, 4.0)
        await initialize_mouse_position(page)
        await human_scroll(page, direction="down", steps=2)
        await human_delay(0.8, 2.5)
        logger.debug("pre_warm_homepage: completed for %s", base_url)
    except Exception as exc:
        logger.debug("pre_warm_homepage: skipped for %s: %s", base_url, exc)


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
    """Throttle per-session request rate before navigation.

    Applies the Redis cross-worker RPM rate limit before issuing the
    ``page.goto`` call, then initialises the in-page mouse position tracker
    so that subsequent ``human_click`` calls have a realistic start point.
    """
    await acquire_session_request_slot(session_key)
    response = await page.goto(url, **kwargs)
    # Seed the in-page mouse position variable from the viewport centre so
    # human_click() always has a valid start point, even on the first click.
    try:
        await initialize_mouse_position(page)
    except Exception:
        pass
    return response
