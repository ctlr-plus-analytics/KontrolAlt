"""Proxy rotation logic."""

import logging
import random
from urllib.parse import urlsplit, urlunsplit

from core.config import scraper_settings

logger = logging.getLogger(__name__)


def _normalize_proxy(proxy: str) -> str:
    """Ensure a proxy string has an http:// scheme so urlsplit can parse it.

    Oxylabs and most residential proxy providers accept URLs in the format:
        http://user:pass@host:port
    If the scheme is missing, urlsplit cannot extract credentials and auth
    is silently dropped, causing the browser to exit via the datacenter IP.

    Args:
        proxy: Raw proxy string from PROXY_LIST env var.

    Returns:
        Proxy string guaranteed to have a scheme prefix.
    """
    if "://" not in proxy:
        proxy = f"http://{proxy}"
    return proxy


class ProxyRotator:
    """Manages a pool of proxy strings for rotation.

    Args:
        proxy_list_str: Comma-separated proxy URLs.
    """

    def __init__(self, proxy_list_str: str) -> None:
        raw = [p.strip() for p in proxy_list_str.split(",") if p.strip()]
        self.proxies: list[str] = [_normalize_proxy(p) for p in raw]
        logger.info("ProxyRotator: loaded %d proxy endpoint(s)", len(self.proxies))

    def get_random(self) -> str:
        """Return a random proxy string."""
        if not self.proxies:
            raise RuntimeError("PROXY_LIST must contain at least one proxy")
        return random.choice(self.proxies)

    def has_proxies(self) -> bool:
        """Return True if at least one proxy is available."""
        return len(self.proxies) > 0


# Module-level singleton instance
proxy_rotator = ProxyRotator(scraper_settings.proxy_list)


def get_random_proxy() -> str:
    """Return a random configured proxy string."""
    return proxy_rotator.get_random()


def build_session_proxy(
    *,
    base_proxy: str,
    session_id: str,
    session_minutes: int | None = None,
    platform_filter: str | None = None,
) -> str:
    """Return proxy URL with Oxylabs-compatible sticky session parameters.

    This keeps channel-flow requests on the same peer while allowing explicit
    session rollover on challenge/failure.
    """
    parsed = urlsplit(_normalize_proxy(base_proxy))
    username = parsed.username or ""
    password = parsed.password or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""

    if not username:
        return base_proxy

    parts = username.split("-")
    filtered_parts: list[str] = []
    skip_next = False
    for idx, part in enumerate(parts):
        if skip_next:
            skip_next = False
            continue
        if part in {"sessid", "sesstime", "os"}:
            skip_next = True
            continue
        filtered_parts.append(part)
    filtered_parts.extend(["sessid", session_id])
    if session_minutes is not None:
        filtered_parts.extend(["sesstime", str(session_minutes)])
    if platform_filter:
        filtered_parts.extend(["os", platform_filter.lower()])

    auth_user = "-".join(filtered_parts)
    auth = auth_user
    if password:
        auth = f"{auth}:{password}"
    netloc = f"{auth}@{host}{port}"
    return urlunsplit((parsed.scheme or "http", netloc, parsed.path, parsed.query, parsed.fragment))
