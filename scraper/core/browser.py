"""Playwright Chromium browser launch with stealth config and proxy support."""

import asyncio
import hashlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import unquote, urlsplit

from playwright.async_api import async_playwright, BrowserContext, Error as PlaywrightError

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
    get_pinned_proxy,
    get_pinned_proxy_for_platform,
    extract_proxy_country,
    record_proxy_success,
    record_proxy_failure,
    proxy_health_tracker,
)
from core.runtime_settings import get_runtime_settings

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
_CF_PROFILE_REDIS_PREFIX = "cf_profile:"
_CF_PROFILE_REDIS_MAX_TTL = 30 * 24 * 3600  # 30 days ceiling

_browser_state_redis = None


def _get_browser_state_redis():
    """Return a lazily-created sync Redis client for cf_profile state.

    Reuses the same URL as the rest of the scraper.  Returns None if Redis
    is unavailable so callers can silently fall back to disk.
    """
    global _browser_state_redis
    if _browser_state_redis is None:
        try:
            import redis as _redis_lib
            _browser_state_redis = _redis_lib.Redis.from_url(
                scraper_settings.redis_url, decode_responses=True, socket_timeout=2
            )
        except Exception:
            return None
    return _browser_state_redis


def _cf_profile_redis_key(profile_dir: Path) -> str:
    return f"{_CF_PROFILE_REDIS_PREFIX}{profile_dir.name}"


def _cf_profile_ttl(state: dict) -> int:
    """Derive Redis TTL from the cf_clearance cookie expiry, capped at 30 days."""
    import time as _time
    now = _time.time()
    best: float = 0.0
    for cookie in state.get("cookies", []):
        if cookie.get("name") == "cf_clearance":
            exp = float(cookie.get("expires") or 0)
            if exp > best:
                best = exp
    remaining = int(best - now) if best > now else 0
    return max(min(remaining, _CF_PROFILE_REDIS_MAX_TTL), 3600)  # 1 h floor


def _extract_domain(session_key: str) -> str | None:
    """Extract the hostname from a session key that is a URL.

    Returns e.g. 'rumble.com' from 'https://rumble.com/c/Chan|attempt:0|task:x'.
    Returns None when the session key is not a URL (e.g. scratch scripts).
    """
    base = session_key.split("|")[0] if "|" in session_key else session_key
    try:
        from urllib.parse import urlsplit as _urlsplit
        parsed = _urlsplit(base)
        return parsed.hostname or None
    except Exception:
        return None


def _profile_dir(session_key: str | None, proxy: str = "") -> Path | None:
    """Return the persistent profile directory for a (domain, proxy) pair.

    Keying on domain + proxy device means all channels on the same site that
    are pinned to the same exit node share one cf_clearance cookie. The first
    channel to solve the CF challenge writes the cookie; every subsequent
    channel on that device loads it and skips the challenge entirely.

    Falls back to a per-session-key directory when the session key is not a
    URL (e.g. one-off scratch scripts) so those paths are unaffected.
    """
    if not session_key:
        return None
    domain = _extract_domain(session_key)
    if domain and proxy:
        # Shared profile: one directory per (domain, proxy endpoint).
        composite = f"{domain}:{proxy}"
        key_hash = hashlib.sha256(composite.encode()).hexdigest()[:24]
        return _PROFILE_BASE_DIR / "shared" / key_hash
    # Fallback: per-channel profile (scratch scripts, no-proxy runs).
    stable_key = session_key.split("|task:")[0] if "|task:" in session_key else session_key
    key_hash = hashlib.sha256(stable_key.encode()).hexdigest()[:24]
    return _PROFILE_BASE_DIR / key_hash


def _load_browser_state(profile_dir: Path | None) -> dict | None:
    """Load Playwright storage state — Redis first, disk fallback.

    Never raises — storage state loss is non-fatal.
    """
    if profile_dir is None:
        return None
    # Redis primary
    try:
        r = _get_browser_state_redis()
        if r is not None:
            raw = r.get(_cf_profile_redis_key(profile_dir))
            if raw:
                state = json.loads(raw)
                logger.debug("Loaded browser state from Redis (%s)", profile_dir.name)
                return state
    except Exception as exc:
        logger.debug("Redis browser state load failed, trying disk: %s", exc)
    # Disk fallback
    state_file = profile_dir / "storage_state.json"
    if not state_file.exists():
        return None
    try:
        with state_file.open("r", encoding="utf-8") as fh:
            state = json.load(fh)
        logger.debug("Loaded browser state from disk (%s)", state_file)
        return state
    except Exception as exc:
        logger.debug("Could not load browser state from disk %s: %s", state_file, exc)
        return None


async def _save_browser_state(context: BrowserContext, profile_dir: Path | None) -> None:
    """Persist Playwright storage state — Redis primary, disk secondary.

    Saving the cf_clearance cookie means subsequent scrapes on the same
    (domain, proxy) skip the Cloudflare challenge.  Never raises.
    """
    if profile_dir is None:
        return
    try:
        state = await context.storage_state()
    except Exception as exc:
        logger.debug("Could not capture browser storage state: %s", exc)
        return
    # Redis primary
    try:
        r = _get_browser_state_redis()
        if r is not None:
            ttl = _cf_profile_ttl(state)
            r.setex(_cf_profile_redis_key(profile_dir), ttl, json.dumps(state))
            logger.debug(
                "Saved browser state to Redis (%s, ttl=%ds)", profile_dir.name, ttl
            )
    except Exception as exc:
        logger.debug("Redis browser state save failed: %s", exc)
    # Disk secondary
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        state_file = profile_dir / "storage_state.json"
        with state_file.open("w", encoding="utf-8") as fh:
            json.dump(state, fh)
        logger.debug("Saved browser state to disk (%s)", state_file)
    except Exception as exc:
        logger.debug("Could not save browser state to disk %s: %s", profile_dir, exc)


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

def _resolve_headless_mode() -> bool:
    """Resolve effective headless mode.

    Production default on Linux is True (headless Chromium; no Xvfb required).
    Dev machines (Windows/macOS) run headed by default for observability.

    Set ``BROWSER_HEADLESS=true`` to force headless, ``false`` to force headed.
    """
    raw = os.environ.get("BROWSER_HEADLESS", "").strip().lower()
    if raw == "true":
        return True
    if raw == "false":
        return False
    return sys.platform == "linux"


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


async def human_delay(min_s: float | None = None, max_s: float | None = None) -> None:
    """Sleep for a random lognormal duration to mimic human behaviour.

    When called with no arguments, uses scraper_human_delay_min/max_seconds
    from RuntimeSettings.  Explicit arguments are used as-is so callers can
    request shorter delays (e.g. pre-warm scrolls) without being overridden.
    """
    runtime = get_runtime_settings()
    effective_min = min_s if min_s is not None else runtime.scraper_human_delay_min_seconds
    effective_max = max_s if max_s is not None else runtime.scraper_human_delay_max_seconds
    effective_max = max(effective_min, effective_max)
    value = human_delay_value()
    if value < effective_min:
        value = effective_min
    if value > effective_max:
        value = effective_max
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


# Injected into every new page at the context level.
# Masks the primary automation signal; plugins and chrome.runtime are patched
# so headless Chromium looks identical to a standard desktop install.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ]
    });
}
if (!window.chrome) { window.chrome = {}; }
if (!window.chrome.runtime) { window.chrome.runtime = {}; }
"""


@asynccontextmanager
async def launch_browser(
    *,
    session_key: str | None = None,
    telemetry: BrowserTelemetry | None = None,
    use_proxy: bool = True,
    platform: str | None = None,
) -> AsyncGenerator[BrowserContext, None]:
    """Launch a Playwright Chromium browser context with stealth flags.

    Uses the per-worker browser pool when available (avoids 2–5 s Chromium
    cold-start per task).  Falls back to a fresh browser launch during tests
    or when the pool is unavailable.

    Proxy is always set at context level so pool and fallback paths behave
    identically and different tasks can use different proxy endpoints.

    Args:
        platform: "rumble" or "substack" — selects the platform-specific proxy
            pool (PROXY_LIST_RUMBLE / PROXY_LIST_SUBSTACK).  Falls back to the
            shared PROXY_LIST when None or unrecognised.

    Yields:
        A configured BrowserContext ready for scraping.
    """
    attempt = _parse_attempt_from_session_key(session_key)
    # Pin each channel to a specific proxy so cf_clearance cookies (tied to the
    # exit node IP) remain valid across runs.  Use the platform-specific pool
    # when available so Rumble and Substack failures don't cross-contaminate
    # each other's health scores.
    if use_proxy:
        stable_key = session_key.split("|task:")[0] if session_key and "|task:" in session_key else session_key
        if stable_key:
            proxy = get_pinned_proxy_for_platform(stable_key, platform or "")
        else:
            proxy = get_weighted_proxy()
    else:
        proxy = ""
    proxy_for_playwright = proxy
    headless = _resolve_headless_mode()
    proxy_settings = _parse_proxy_settings(proxy_for_playwright) if proxy_for_playwright else {}
    proxy_country = extract_proxy_country(proxy_for_playwright) if proxy_for_playwright else None
    proxy_active = bool(proxy_settings.get("server"))

    logger.debug(
        "Launching browser: headless=%s attempt=%d proxy_server=%s proxy_country=%s",
        headless,
        attempt,
        proxy_settings.get("server"),
        proxy_country or "unknown",
    )

    if telemetry is not None:
        telemetry.geoip_enabled = proxy_active
        telemetry.selected_proxy = proxy

    profile = get_consistent_browser_profile(
        session_key=session_key,
        proxy_country=proxy_country,
    )

    pdir = _profile_dir(session_key, proxy)
    saved_state = _load_browser_state(pdir)
    if _state_has_cf_clearance(saved_state):
        logger.debug("launch_browser: restoring session with cf_clearance cookie")

    _cf_blocked = False
    _cf_error_code: int | None = None
    _proxy_failed = False  # network/timeout failure — penalise proxy score
    _ssl_error = False     # exit-node TLS failure — don't penalise the proxy endpoint
    proxy_arg = proxy_settings if proxy_active else None

    async def _build_context(browser) -> BrowserContext:
        """Create and configure a BrowserContext from *browser*."""
        context: BrowserContext = await browser.new_context(
            viewport=profile["viewport"],
            permissions=["geolocation"],
            locale=str(profile["locale"]),
            timezone_id=str(profile["timezone_id"]),
            extra_http_headers=dict(profile["extra_http_headers"]),
            storage_state=saved_state,
            user_agent=str(profile["user_agent"]),
            proxy=proxy_arg,  # proxy at context level; supports pool + per-task rotation
        )
        await context.add_init_script(_STEALTH_JS)

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

        return context

    # Try to reuse the shared browser from the worker pool (no cold start).
    _pool_browser = None
    try:
        from core.browser_pool import worker_pool
        _pool_browser = await worker_pool.ensure_browser()
    except Exception:
        pass

    if _pool_browser is not None:
        # Fast path: new context from shared browser process.
        context = await _build_context(_pool_browser)
        try:
            yield context
        except CloudflareBlockError as exc:
            _cf_blocked = True
            _cf_error_code = exc.error_code
            raise
        except PlaywrightError as exc:
            err = str(exc)
            if "ERR_SSL" in err or "ERR_CERT_" in err:
                # TLS handshake failure from a faulty exit node, not the proxy
                # endpoint itself. Don't penalise — rotating the session on the
                # next launch will assign a different device.
                _ssl_error = True
            else:
                _proxy_failed = True
            raise
        finally:
            await _save_browser_state(context, pdir)
            if proxy:
                if _cf_blocked:
                    record_proxy_failure(proxy, _cf_error_code)
                elif _proxy_failed:
                    # Don't re-penalize an already-quarantined proxy — that would
                    # reset its 30-minute TTL and prevent natural recovery.
                    if not proxy_health_tracker.is_quarantined(proxy):
                        record_proxy_failure(proxy, None)
                elif not _ssl_error:
                    # SSL exit-node errors: no score change (neither success nor failure).
                    record_proxy_success(proxy)
            await context.close()
    else:
        # Fallback: fresh Playwright + Chromium launch (tests / pool unavailable).
        # Proxy is not set at browser level — _build_context() sets it at context
        # level so the pool and fallback paths behave identically.
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--ignore-certificate-errors",
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                context = await _build_context(browser)
                try:
                    yield context
                except CloudflareBlockError as exc:
                    _cf_blocked = True
                    _cf_error_code = exc.error_code
                    raise
                except PlaywrightError:
                    _proxy_failed = True
                    raise
                finally:
                    await _save_browser_state(context, pdir)
                    if _cf_blocked:
                        record_proxy_failure(proxy, _cf_error_code)
                    elif _proxy_failed:
                        record_proxy_failure(proxy, None)
                    else:
                        record_proxy_success(proxy)
                    await context.close()
            finally:
                await browser.close()


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
        await human_delay(0.5, 1.5)
        await initialize_mouse_position(page)
        await human_scroll(page, direction="down", steps=2)
        await human_delay(0.3, 0.8)
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
