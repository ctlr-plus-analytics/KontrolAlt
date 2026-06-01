"""Standalone Substack leaderboard scraper.

Fetches all profiles from the Substack business leaderboard pages
(paid + rising) and upserts them into the channels table.

Duplicate-safe: existing rows get their discovery evidence refreshed;
only net-new handles are inserted with discovery_status="new".

Usage:
    cd scraper
    python scrape_leaderboard.py              # live run
    python scrape_leaderboard.py --dry-run    # print URLs without writing to DB
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from postgrest.exceptions import APIError

from core.browser import (
    BrowserTelemetry,
    guarded_goto,
    is_cold_session,
    launch_browser,
    pre_warm_homepage,
    wait_for_content,
)
from core.supabase import get_supabase_client
from utils.channel_urls import canonicalize_channel_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("scrape_leaderboard")

_SUBSTACK_BASE = "https://substack.com"
_NAV_TIMEOUT_MS = 45_000
_CONTENT_WAIT_S = 30.0

# Maps Substack leaderboard URL slugs to the internal taxonomy category names
# used by discover_channels.py and the niche_tags keyword matcher.
_SLUG_TO_TAXONOMY: dict[str, str] = {
    "business":       "Financial / Macro",
    "finance":        "Financial / Macro",
    "crypto":         "Crypto / Alternative Assets",
    "health":         "Health / Wellness",
    "health-politics":"Health / Wellness",
    "faith":          "Religious / Values-Based",
    "news":           "News / Commentary",
    "us-politics":    "Conservative Politics",
    "world-politics": "News / Commentary",
}


def _board(category: str, kind: str) -> dict:
    slug = category.replace("-", "_")
    return {
        "label": f"{category}/{kind}",
        "url": f"{_SUBSTACK_BASE}/leaderboard/{category}/{kind}",
        "category": _SLUG_TO_TAXONOMY.get(category, category),
        "source": f"leaderboard_{slug}_{kind}",
    }


_LEADERBOARDS = [
    _board("business", "paid"),
    _board("business", "rising"),
    _board("us-politics", "paid"),
    _board("us-politics", "rising"),
    _board("finance", "paid"),
    _board("finance", "rising"),
    _board("world-politics", "paid"),
    _board("world-politics", "rising"),
    _board("faith", "paid"),
    _board("faith", "rising"),
    _board("news", "paid"),
    _board("news", "rising"),
    _board("crypto", "paid"),
    _board("crypto", "rising"),
    _board("health", "paid"),
    _board("health", "rising"),
    _board("health-politics", "paid"),
    _board("health-politics", "rising"),
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _handle_from_pub(pub: dict) -> str | None:
    """Prefer the handle field; fall back to subdomain."""
    for key in ("handle", "subdomain"):
        value = str(pub.get(key) or "").strip()
        if value:
            return value
    return None


def _channel_url(handle: str) -> str:
    return f"{_SUBSTACK_BASE}/@{handle}"


# ── DB writes ─────────────────────────────────────────────────────────────────

def _existing_channel(client, channel_url: str) -> dict | None:
    try:
        result = (
            client.table("channels")
            .select("id,channel_url,has_been_scraped,discovery_evidence_count,discovery_confidence")
            .eq("channel_url", channel_url)
            .maybe_single()
            .execute()
        )
        data = getattr(result, "data", None)
        return data if isinstance(data, dict) else None
    except APIError as exc:
        logger.warning("DB lookup failed for %s: %s", channel_url, exc)
        return None


def upsert_channel(
    client,
    *,
    handle: str,
    name: str,
    category: str,
    source: str,
    confidence: float = 0.95,
) -> str:
    """Insert or refresh a leaderboard channel. Returns 'inserted'|'refreshed'|'error'."""
    url = _channel_url(handle)
    now = _utc_now()
    existing = _existing_channel(client, url)

    if existing is not None:
        evidence_count = int(existing.get("discovery_evidence_count") or 0) + 1
        best_confidence = max(float(existing.get("discovery_confidence") or 0.0), confidence)
        try:
            client.table("channels").update({
                "discovery_confidence": best_confidence,
                "discovery_evidence_count": evidence_count,
                "discovery_last_seen_at": now,
                "last_discovery_source": source,
                "updated_at": now,
            }).eq("channel_url", url).execute()
            return "refreshed"
        except APIError as exc:
            logger.warning("Failed to refresh %s: %s", url, exc)
            return "error"

    try:
        client.table("channels").insert({
            "platform": "substack",
            "channel_url": url,
            "name": name or handle,
            "description": "",
            "is_active": True,
            "has_been_scraped": False,
            "discovery_source": source,
            "last_discovery_source": source,
            "discovery_category": category,
            "discovery_status": "new",
            "discovery_confidence": confidence,
            "discovery_evidence_count": 1,
            "discovery_last_seen_at": now,
            "discovered_at": now,
            "updated_at": now,
        }).execute()
        return "inserted"
    except APIError as exc:
        logger.warning("Failed to insert %s: %s", url, exc)
        return "error"


# ── browser fetcher ───────────────────────────────────────────────────────────

_COUNT_PUB_LINKS_JS = """
() => new Set(
    Array.from(document.querySelectorAll('a[href]'))
        .map(a => a.href.split('?')[0].split('#')[0])
        .filter(h => h.includes('.substack.com') || h.includes('substack.com/@'))
).size
"""

_EXTRACT_LINKS_JS = """
() => {
    const results = [];
    const seen = new Set();
    const SKIP_TEXT = /^(subscribe|follow|read more|see more|learn more|get started)$/i;
    document.querySelectorAll('a[href]').forEach(a => {
        const href = (a.href || '').split('?')[0].split('#')[0].trim();
        if (!href || seen.has(href)) return;
        if (!href.includes('.substack.com') && !href.includes('substack.com/@')) return;
        seen.add(href);

        // Look for the publication name only INSIDE the anchor, never in ancestors
        // (ancestors contain the shared section heading)
        let name = '';
        const inner = a.querySelector(
            '[class*="name"],[class*="title"],[class*="publication"],h3,h4,strong'
        );
        if (inner) {
            name = inner.textContent.trim();
        } else {
            const lines = a.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
            name = lines.find(l => l.length > 2 && !SKIP_TEXT.test(l)) || '';
        }
        results.push({ url: href, name: name });
    });
    return results;
}
"""


async def _scroll_until_loaded(
    page,
    target: int = 100,
    max_scrolls: int = 60,
    settle_s: float = 3.0,
    stale_limit: int = 5,
) -> None:
    """Scroll the page until `target` publication links are in the DOM or
    scrolling stops adding new ones.

    Uses instant (non-animated) scrollTo so the position is committed before
    the next await. On stale iterations alternates between pressing the End
    key and scrolling to the pixel-exact bottom to try different trigger paths
    for Substack's IntersectionObserver sentinel.
    """
    prev_count = 0
    stale = 0

    for i in range(max_scrolls):
        count: int = await page.evaluate(_COUNT_PUB_LINKS_JS)
        logger.debug("Scroll %d: %d publication links in DOM", i + 1, count)

        if count >= target:
            logger.info("Reached target of %d publication links after %d scrolls", count, i + 1)
            return

        if count == prev_count:
            stale += 1
            if stale >= stale_limit:
                logger.info(
                    "No new links after %d consecutive scrolls — stopping at %d", stale, count
                )
                return
            # On stale scrolls alternate between End key and direct scrollTo
            if stale % 2 == 0:
                await page.keyboard.press("End")
            else:
                await page.evaluate(
                    "window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })"
                )
        else:
            stale = 0
            await page.evaluate(
                "window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' })"
            )

        prev_count = count
        await asyncio.sleep(settle_s)

    final: int = await page.evaluate(_COUNT_PUB_LINKS_JS)
    logger.info("Scroll loop ended after %d scrolls with %d links in DOM", max_scrolls, final)


async def _fetch_leaderboard_publications(page, board: dict) -> list[dict]:
    """Navigate to the leaderboard page, scroll to load all 100 entries,
    then extract every Substack publication link from the DOM.

    The /api/v1/publication/leaderboard endpoint requires a logged-in session
    so we DOM-scrape instead. Substack loads cards lazily as you scroll, so
    _scroll_until_loaded() keeps scrolling until the count stabilises at 100.
    """
    await guarded_goto(
        page,
        board["url"],
        session_key=board["label"],
        wait_until="domcontentloaded",
        timeout=_NAV_TIMEOUT_MS,
    )
    await wait_for_content(page, timeout_s=_CONTENT_WAIT_S)

    # Wait for the first batch of cards to render before scrolling
    try:
        await page.wait_for_selector(
            'a[href*=".substack.com"], a[href*="substack.com/@"]',
            timeout=20_000,
        )
    except Exception:
        logger.warning("Timed out waiting for first publication links on %s", board["url"])

    await _scroll_until_loaded(page, target=100)

    dom_items: list[dict] = await page.evaluate(_EXTRACT_LINKS_JS)

    publications: list[dict] = []
    seen_handles: set[str] = set()
    for item in dom_items:
        raw_url = (item.get("url") or "").strip()
        candidate = canonicalize_channel_url(raw_url)
        if candidate is None or candidate.platform != "substack":
            continue
        handle = candidate.channel_url.split("/@")[-1] if "/@" in candidate.channel_url else ""
        if not handle or handle in seen_handles:
            continue
        seen_handles.add(handle)
        publications.append({
            "handle": handle,
            "name": (item.get("name") or "").strip() or handle,
        })

    logger.info(
        "Extracted %d publications from DOM for %s", len(publications), board["label"]
    )
    return publications


# ── orchestrator ──────────────────────────────────────────────────────────────

async def scrape_leaderboards(*, dry_run: bool = False) -> dict:
    client = None if dry_run else get_supabase_client()

    # Collect all unique handles across both leaderboards before any DB work.
    # Last-write wins for name/category/source if a handle appears in both.
    all_handles: dict[str, dict] = {}

    session_key = "leaderboard_session"
    telemetry = BrowserTelemetry()
    async with launch_browser(session_key=session_key, telemetry=telemetry) as context:
        page = await context.new_page()

        if await is_cold_session(context):
            await pre_warm_homepage(
                page, _SUBSTACK_BASE + "/", session_key=session_key
            )

        for board in _LEADERBOARDS:
            logger.info("Fetching leaderboard: %s", board["label"])
            publications = await _fetch_leaderboard_publications(page, board)

            for pub in publications:
                if not isinstance(pub, dict):
                    continue
                handle = _handle_from_pub(pub)
                if not handle:
                    continue
                name = str(pub.get("name") or "").strip() or handle
                all_handles[handle] = {
                    "name": name,
                    "category": board["category"],
                    "source": board["source"],
                }

    logger.info("Unique handles found: %d", len(all_handles))

    if not all_handles:
        logger.warning(
            "No handles extracted — leaderboard pages may need more settle time "
            "or the API response shape has changed."
        )

    stats: dict[str, int] = {"inserted": 0, "refreshed": 0, "errors": 0}

    for handle, meta in all_handles.items():
        url = _channel_url(handle)
        if dry_run:
            line = f"[dry-run] {url}  {meta['name']}"
            print(line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace"))
            continue
        status = upsert_channel(
            client,
            handle=handle,
            name=meta["name"],
            category=meta["category"],
            source=meta["source"],
        )
        stats[status] = stats.get(status, 0) + 1
        if status == "inserted":
            logger.info("Inserted  %s  (%s)", url, meta["name"])
        elif status == "refreshed":
            logger.debug("Refreshed %s", url)

    logger.info(
        "Complete — inserted=%d  refreshed=%d  errors=%d  dry_run=%s",
        stats["inserted"],
        stats["refreshed"],
        stats["errors"],
        dry_run,
    )
    return {**stats, "total": len(all_handles), "dry_run": dry_run}


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Substack business leaderboards into the channels table."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print discovered channel URLs without writing to the database.",
    )
    args = parser.parse_args()

    result = asyncio.run(scrape_leaderboards(dry_run=args.dry_run))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
