"""Proxy rotation logic with Redis-backed health scoring and quarantine."""

import asyncio
import logging
import random
import re
import time
import hashlib
from urllib.parse import urlsplit

import redis

from core.config import scraper_settings

logger = logging.getLogger(__name__)

# Singleton Redis client so every ProxyHealthTracker / ProxySessionManager call
# reuses the same client rather than opening a new TCP connection each time.
_proxy_redis_client: redis.Redis | None = None


def _proxy_redis() -> redis.Redis:
    global _proxy_redis_client
    if _proxy_redis_client is None:
        _proxy_redis_client = redis.Redis.from_url(
            scraper_settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.1,
            socket_timeout=1.0,
        )
    return _proxy_redis_client


PLATFORM_PROXY_REQUIREMENTS = {
    "rumble": {
        "type": "residential",
        "preferred_countries": ("US",),
        # Sticky behavior is provided by upstream proxy credentials (.env),
        # not rewritten in scraper code.
        "sticky_session": "provider_configured",
    },
}


def _canonicalize_proxy_url(proxy: str) -> str:
    """Normalize proxy credentials into user:pass@host:port form.

    Supported inputs:
    - user:pass@host:port
    - host:port:user:pass
    - with or without scheme
    """
    proxy = proxy.strip()
    if not proxy:
        raise ValueError("empty proxy")

    if "://" in proxy:
        scheme, raw = proxy.split("://", 1)
    else:
        scheme, raw = "http", proxy

    if "@" in raw:
        auth, host_port = raw.rsplit("@", 1)
        if ":" not in auth or ":" not in host_port:
            raise ValueError(f"invalid proxy format: {proxy}")
        username, password = auth.split(":", 1)
        host, port = host_port.rsplit(":", 1)
    else:
        parts = raw.split(":")
        if len(parts) != 4:
            raise ValueError(f"invalid proxy format: {proxy}")
        host, port, username, password = parts

    if not port.isdigit():
        raise ValueError(f"invalid proxy port: {port}")
    return f"{scheme}://{username}:{password}@{host}:{port}"



def _normalize_proxy(proxy: str) -> str:
    """Ensure a proxy string has an http:// scheme so urlsplit can parse it.

    Oxylabs and most residential proxy providers accept URLs in the format:
        http://user:pass@host:port
    Some providers, including Evomi, also document credentials as:
        host:port:user:pass
    If the scheme is missing, urlsplit cannot extract credentials and auth
    is silently dropped, causing the browser to exit via the datacenter IP.

    Args:
        proxy: Raw proxy string from PROXY_LIST env var.

    Returns:
        Proxy string guaranteed to have a scheme prefix.
    """
    try:
        return _canonicalize_proxy_url(proxy)
    except ValueError:
        # Keep backward compatibility for already-canonical inputs that include
        # uncommon auth chars we did not parse above.
        if "://" not in proxy:
            return f"http://{proxy.strip()}"
        return proxy.strip()


# Common residential proxy country-encoding patterns:
#   Oxylabs:    pr.oxylabs.io:... username contains  "country-US"
#   Bright Data: username contains  "country-us"
#   Evomi:      username contains  "-cc-US"
#   Smartproxy: username contains  "_country-US" or ".country.US"
_COUNTRY_PATTERNS = (
    re.compile(r"[_\-]country[_\-]([a-z]{2})", re.IGNORECASE),
    re.compile(r"-cc-([a-z]{2})", re.IGNORECASE),
    re.compile(r"\.country\.([a-z]{2})", re.IGNORECASE),
    re.compile(r"-([a-z]{2})-", re.IGNORECASE),  # some providers embed country mid-username
)


def extract_proxy_country(proxy_url: str) -> str | None:
    """Extract a 2-letter ISO country code from a proxy URL, if present.

    Supports the encoding conventions used by Oxylabs, Bright Data, Evomi,
    Smartproxy, and similar residential proxy providers.

    Returns the uppercase country code (e.g. ``"US"``) or ``None`` if the
    URL does not encode a country.
    """
    if not proxy_url:
        return None
    try:
        normalized = _normalize_proxy(proxy_url)
        parsed = urlsplit(normalized)
        username = parsed.username or ""
    except Exception:
        username = proxy_url

    password = parsed.password or ""
    # Some providers (e.g. Evomi) encode the country in the password, not the username.
    for field in (username, password):
        for pattern in _COUNTRY_PATTERNS:
            match = pattern.search(field)
            if match:
                code = match.group(1).upper()
                if len(code) == 2 and code.isalpha():
                    return code
    return None


class ProxyHealthTracker:
    """Redis-backed per-proxy health scoring and quarantine.

    Each proxy IP is assigned a score in [0.0, 1.0] that starts at 1.0.

    Penalties applied on scrape failure:
      - Hard CF block (error_code 403 / 1020 / 1010): −0.5
      - Soft CF block (rate limit, geo, general): −0.25

    Recovery applied on scrape success:
      - +0.1 per successful scrape (capped at 1.0)

    Quarantine:
      - Score ≤ 0.1 triggers a QUARANTINE_TTL-second Redis key.
      - Quarantined proxies are excluded from weighted selection.
      - Quarantine auto-expires; the proxy re-enters the pool with a
        fresh score of 0.2 on next selection.
    """

    QUARANTINE_TTL: int = 1800  # 30 minutes
    SCORE_TTL: int = 7200       # 2 hours
    _SCORE_PREFIX = "proxy:score:"
    _QUARANTINE_PREFIX = "proxy:quarantine:"

    @staticmethod
    def _hash(proxy: str) -> str:
        return hashlib.sha1(proxy.encode()).hexdigest()[:20]

    def _score_key(self, proxy: str) -> str:
        return self._SCORE_PREFIX + self._hash(proxy)

    def _quarantine_key(self, proxy: str) -> str:
        return self._QUARANTINE_PREFIX + self._hash(proxy)

    def _redis(self) -> redis.Redis:
        return _proxy_redis()

    def get_score(self, proxy: str) -> float:
        """Return the current health score for a proxy (default 1.0)."""
        try:
            val = self._redis().get(self._score_key(proxy))
            return float(val) if val is not None else 1.0
        except Exception:
            return 1.0

    def is_quarantined(self, proxy: str) -> bool:
        """Return True if the proxy is in the quarantine cooldown period."""
        try:
            return bool(self._redis().exists(self._quarantine_key(proxy)))
        except Exception:
            return False

    def record_success(self, proxy: str) -> None:
        """Recover health score after a successful scrape."""
        try:
            r = self._redis()
            score_key = self._score_key(proxy)
            score = float(r.get(score_key) or 1.0)
            score = min(1.0, score + 0.1)
            r.setex(score_key, self.SCORE_TTL, str(score))
            r.delete(self._quarantine_key(proxy))
        except Exception as exc:
            logger.debug("ProxyHealthTracker.record_success: %s", exc)

    def record_failure(
        self, proxy: str, error_code: int | None = None
    ) -> None:
        """Apply a health penalty after a CF block or scrape failure.

        Hard blocks (403, error 1020, fingerprint 1010) carry a −0.5 penalty.
        All other failures carry a −0.25 penalty.
        Score ≤ 0.1 triggers a 30-minute quarantine.
        """
        try:
            r = self._redis()
            score_key = self._score_key(proxy)
            quarantine_key = self._quarantine_key(proxy)
            score = float(r.get(score_key) or 1.0)
            # Hard block: firewall rule (1020), fingerprint block (1010), or HTTP 403
            penalty = 0.5 if error_code in (403, 1020, 1010) else 0.25
            score = max(0.0, score - penalty)
            r.setex(score_key, self.SCORE_TTL, str(score))
            if score <= 0.1:
                r.setex(quarantine_key, self.QUARANTINE_TTL, "1")
                logger.info(
                    "Proxy quarantined for %ds (score=%.2f error_code=%s hash=%s)",
                    self.QUARANTINE_TTL,
                    score,
                    error_code,
                    self._hash(proxy),
                )
            else:
                logger.debug(
                    "Proxy health degraded to %.2f (error_code=%s hash=%s)",
                    score,
                    error_code,
                    self._hash(proxy),
                )
        except Exception as exc:
            logger.debug("ProxyHealthTracker.record_failure: %s", exc)


class ProxyRotator:
    """Manages a pool of proxy strings for rotation.

    Args:
        proxy_list_str: Comma-separated proxy URLs.
    """

    def __init__(self, proxy_list_str: str) -> None:
        raw = [p.strip() for p in proxy_list_str.split(",") if p.strip()]
        self.proxies: list[str] = []
        for proxy in raw:
            normalized = _normalize_proxy(proxy)
            try:
                parsed = urlsplit(normalized)
                _ = parsed.port
            except ValueError as exc:
                logger.warning("Skipping malformed proxy entry: %s", exc)
                continue
            self.proxies.append(normalized)
        logger.info("ProxyRotator: loaded %d proxy endpoint(s)", len(self.proxies))

    def get_random(self) -> str:
        """Return a random proxy string (legacy; prefer get_weighted)."""
        if not self.proxies:
            raise RuntimeError("PROXY_LIST must contain at least one proxy")
        return random.choice(self.proxies)

    def get_weighted(self, health_tracker: "ProxyHealthTracker") -> str:
        """Return a proxy selected by health-weighted random choice.

        Quarantined proxies are excluded from the candidate pool.  If
        *all* proxies are quarantined (e.g. pool size 1 and it is burned)
        the full pool is used as a best-effort fallback so scraping does
        not halt entirely.
        """
        if not self.proxies:
            raise RuntimeError("PROXY_LIST must contain at least one proxy")
        available = [
            p for p in self.proxies if not health_tracker.is_quarantined(p)
        ]
        if not available:
            logger.warning(
                "ProxyRotator: all %d proxies quarantined — falling back to full pool.",
                len(self.proxies),
            )
            available = self.proxies
        # Weight floor of 0.05 ensures quarantine-expired proxies still get
        # occasional traffic so their score can recover.
        weights = [max(0.05, health_tracker.get_score(p)) for p in available]
        return random.choices(available, weights=weights, k=1)[0]

    def get_pinned(self, channel_key: str, health_tracker: "ProxyHealthTracker") -> str:
        """Return a deterministically pinned proxy for a channel key.

        The same channel always maps to the same proxy so that cf_clearance
        cookies (which are tied to a specific exit node IP) remain valid across
        runs. Falls back to the next proxy in the list if the pinned one is
        quarantined, cycling through all available proxies before giving up.
        """
        if not self.proxies:
            raise RuntimeError("PROXY_LIST must contain at least one proxy")
        n = len(self.proxies)
        # Stable index derived from the channel key — same channel, same slot.
        base = int(hashlib.sha256(channel_key.encode()).hexdigest(), 16) % n
        for i in range(n):
            proxy = self.proxies[(base + i) % n]
            if not health_tracker.is_quarantined(proxy):
                return proxy
        # All proxies quarantined — return the pinned one as a last resort.
        return self.proxies[base % n]

    def has_proxies(self) -> bool:
        """Return True if at least one proxy is available."""
        return len(self.proxies) > 0


# Module-level singletons
proxy_rotator = ProxyRotator(scraper_settings.proxy_list)
proxy_health_tracker = ProxyHealthTracker()

# Per-platform rotators — fall back to the shared list when the platform-
# specific env var (PROXY_LIST_RUMBLE / PROXY_LIST_SUBSTACK) is not set.
_proxy_rotator_rumble = ProxyRotator(
    scraper_settings.proxy_list_rumble or scraper_settings.proxy_list
)
_proxy_rotator_substack = ProxyRotator(
    scraper_settings.proxy_list_substack or scraper_settings.proxy_list
)
_PLATFORM_ROTATORS: dict[str, ProxyRotator] = {
    "rumble": _proxy_rotator_rumble,
    "substack": _proxy_rotator_substack,
}


def get_weighted_proxy() -> str:
    """Return a health-weighted proxy from the active pool.

    Healthy proxies receive proportionally more traffic; quarantined proxies
    are excluded until their cooldown expires.  Falls back to pure-random
    selection when Redis is unavailable.
    """
    return proxy_rotator.get_weighted(proxy_health_tracker)


def get_pinned_proxy(channel_key: str) -> str:
    """Return a deterministically pinned proxy for a channel (shared pool)."""
    return proxy_rotator.get_pinned(channel_key, proxy_health_tracker)


def get_pinned_proxy_for_platform(channel_key: str, platform: str) -> str:
    """Return a deterministically pinned proxy from the platform-specific pool.

    Uses PROXY_LIST_RUMBLE or PROXY_LIST_SUBSTACK when set, otherwise falls
    back to the shared PROXY_LIST.  Health scoring is global across platforms
    so a quarantined proxy is avoided regardless of which platform flagged it.
    """
    rotator = _PLATFORM_ROTATORS.get(platform, proxy_rotator)
    return rotator.get_pinned(channel_key, proxy_health_tracker)


def get_random_proxy() -> str:
    """Return a configured proxy string (delegates to health-weighted selection)."""
    return get_weighted_proxy()


def record_proxy_success(proxy: str) -> None:
    """Record a successful scrape and recover the proxy's health score."""
    proxy_health_tracker.record_success(proxy)


def record_proxy_failure(proxy: str, error_code: int | None = None) -> None:
    """Apply a health penalty to a proxy after a Cloudflare block.

    Pass ``error_code`` from the ``CloudflareBlockError.error_code`` attribute
    so that hard blocks (1020 firewall, 1010 fingerprint, HTTP 403) receive
    a larger penalty than soft blocks (rate limit, geo, captcha).
    """
    proxy_health_tracker.record_failure(proxy, error_code)


class ProxySessionManager:
    """One channel per session with Redis-backed blocked-session cooldown tracking.

    Blocked session state is stored in Redis so it:
    - Survives worker restarts.
    - Is consistent across multiple Celery workers sharing the same Redis instance.
    """

    def __init__(self, cooldown_seconds: int = 1800) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._used_sessions: set[str] = set()
        # In-memory fallback for when Redis is unavailable.
        self._blocked_sessions_local: dict[str, float] = {}

    def _redis_key(self, session_id: str) -> str:
        return "blocked:session:" + hashlib.sha1(session_id.encode()).hexdigest()[:20]

    def get_session_for_channel(self, channel_key: str) -> str:
        seed = int(time.time() // 3600)
        for _ in range(6):
            candidate = hashlib.sha256(
                f"{channel_key}:{seed}".encode()
            ).hexdigest()[:16]
            seed += 1
            if candidate in self._used_sessions:
                continue
            if self.is_blocked(candidate):
                continue
            self._used_sessions.add(candidate)
            return candidate
        fallback = hashlib.sha256(f"{channel_key}:{time.time()}".encode()).hexdigest()[:16]
        self._used_sessions.add(fallback)
        return fallback

    def mark_blocked(self, session_id: str) -> None:
        """Record session as blocked in Redis (with TTL) and local fallback."""
        self._blocked_sessions_local[session_id] = time.time()
        try:
            _proxy_redis().setex(self._redis_key(session_id), self.cooldown_seconds, "1")
        except Exception as exc:
            logger.debug("ProxySessionManager: Redis mark_blocked failed (local fallback): %s", exc)

    def is_blocked(self, session_id: str) -> bool:
        """Check Redis first; also check in-memory dict as a safety net.

        The in-memory dict is always checked so that a transient Redis write
        failure in mark_blocked does not cause a blocked session to appear
        unblocked on the very next is_blocked call.
        """
        try:
            if _proxy_redis().exists(self._redis_key(session_id)):
                return True
        except Exception as exc:
            logger.debug("ProxySessionManager: Redis is_blocked failed (local fallback): %s", exc)
        # Local dict acts as fallback and safety net.
        blocked_at = self._blocked_sessions_local.get(session_id)
        if blocked_at is None:
            return False
        expired = (time.time() - blocked_at) >= self.cooldown_seconds
        if expired:
            del self._blocked_sessions_local[session_id]
        return not expired

    def extract_session_id(self, key: str | None) -> str | None:
        if not key:
            return None
        marker = "session:"
        idx = key.rfind(marker)
        if idx < 0:
            return None
        raw = key[idx + len(marker):].split("|", 1)[0].strip()
        return raw or None


proxy_session_manager = ProxySessionManager()


# ---------------------------------------------------------------------------
# Startup proxy health validation
# ---------------------------------------------------------------------------

async def _check_single_proxy_health(proxy_url: str, timeout: float = 12.0) -> tuple[bool, str]:
    """Check whether a proxy is reachable and returns a valid response.

    Makes a lightweight GET request to https://api.ipify.org through the proxy.
    Returns (is_healthy, reason_string).
    """
    try:
        import httpx
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
        ) as client:
            resp = await client.get("https://api.ipify.org?format=json")
            if resp.status_code == 200:
                return True, "ok"
            return False, f"http_{resp.status_code}"
    except httpx.ProxyError as exc:
        return False, f"proxy_error:{type(exc).__name__}"
    except httpx.ConnectTimeout:
        return False, "connect_timeout"
    except httpx.ReadTimeout:
        return False, "read_timeout"
    except Exception as exc:
        return False, f"exception:{type(exc).__name__}"


_STARTUP_LOCK_KEY = "proxy:startup_check_lock"
_STARTUP_LOCK_TTL = 120  # seconds — one check per 2-minute window across all workers


async def validate_proxy_pool_on_startup(
    rotator: "ProxyRotator",
    health_tracker: "ProxyHealthTracker",
    *,
    timeout: float = 12.0,
    concurrency: int = 4,
) -> None:
    """Check every proxy in the pool at worker startup.

    Only the first worker process to acquire the Redis lock actually runs the
    check; all others skip.  This prevents the N-worker cascade where each of
    the N forked processes independently applies a -0.25 penalty, driving a
    single proxy from score 1.0 to 0.0 in one startup cycle.

    The lock TTL is 120 s so each fresh container startup gets one real check.
    """
    # Deduplicate across forked worker processes.
    try:
        acquired = bool(_proxy_redis().set(_STARTUP_LOCK_KEY, "1", nx=True, ex=_STARTUP_LOCK_TTL))
    except Exception:
        acquired = True  # Redis unavailable — proceed so startup never stalls

    if not acquired:
        logger.info("validate_proxy_pool_on_startup: skipped (another worker process is running this check)")
        return

    proxies = rotator.proxies
    if not proxies:
        logger.warning("validate_proxy_pool_on_startup: proxy pool is empty")
        return

    logger.info(
        "validate_proxy_pool_on_startup: checking %d proxy(ies) with concurrency=%d timeout=%.1fs",
        len(proxies),
        concurrency,
        timeout,
    )

    semaphore = asyncio.Semaphore(concurrency)

    async def _check_and_report(proxy: str) -> None:
        hash_hint = health_tracker._hash(proxy)
        async with semaphore:
            healthy, reason = await _check_single_proxy_health(proxy, timeout=timeout)
        if healthy:
            logger.info(
                "validate_proxy_pool_on_startup: proxy %s — REACHABLE",
                hash_hint,
            )
        elif reason in ("connect_timeout", "read_timeout"):
            # Residential proxies route through real devices and can have 10–20 s
            # initial latency.  A timeout here does not mean the proxy is dead —
            # it may just be slow to respond to the httpx check.  Log a warning
            # but don't penalize the health score so actual scrapes get a fair try.
            logger.warning(
                "validate_proxy_pool_on_startup: proxy %s — TIMEOUT (%s) "
                "— score unchanged; proxy will be evaluated during real scrapes",
                hash_hint,
                reason,
            )
        else:
            # Genuine proxy error (bad credentials, server rejection, etc.).
            health_tracker.record_failure(proxy, error_code=None)
            logger.warning(
                "validate_proxy_pool_on_startup: proxy %s — UNREACHABLE (%s) "
                "— health score penalised; proxy remains in pool as fallback",
                hash_hint,
                reason,
            )

    await asyncio.gather(*(_check_and_report(p) for p in proxies))
    logger.info("validate_proxy_pool_on_startup: completed for %d proxy(ies)", len(proxies))
