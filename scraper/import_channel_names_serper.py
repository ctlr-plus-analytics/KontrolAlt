"""Resolve channel names to precise Rumble/Substack channel URLs.

This script is intended for manual channel-name lists like the
``DO NOT CONTACT_CURRENT PARTNERS.csv`` file.

Workflow:
- Read unique non-empty channel names from CSV columns.
- Search Serper for likely Rumble/Substack channel pages.
- Canonicalize and strictly validate candidate URLs.
- Optionally verify candidates by fetching the page title/canonical URL.
- Default to dry-run and write a JSON report.
- Optional ``--write`` updates or inserts rows in ``channels``.

The main goal is precision. When the candidate is ambiguous, the script keeps
it out of the database and leaves it in the review report instead.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from postgrest.exceptions import APIError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import scraper_settings
from core.supabase import get_supabase_client
from utils.channel_urls import (
    ChannelUrlCandidate,
    canonicalize_channel_url,
    extract_supported_channel_urls,
)

SERPER_URL = "https://google.serper.dev/search"
SERPER_RETRY_CODES = {408, 425, 429, 500, 502, 503, 504}
SERPER_MAX_ATTEMPTS = 3
SERPER_RETRY_DELAY_SECONDS = 1.5

SUPPORTED_PLATFORMS = {"rumble", "substack"}
DEFAULT_OUTPUT_PATH = "scraper/output/channel_name_resolution_report.json"
DEFAULT_MIN_CONFIDENCE = 0.86
DEFAULT_SEARCH_LIMIT = 10


@dataclass(frozen=True)
class SeedRecord:
    """A unique channel-name seed extracted from the CSV."""

    raw_name: str
    normalized_name: str
    sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateRecord:
    """A candidate channel URL plus its evidence."""

    channel_url: str
    platform: str
    confidence: float
    display_name: str | None
    source: str
    query: str
    evidence: list[str] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().split())


def _normalize_seed(text: str) -> str:
    text = _normalize(text)
    text = text.strip("\"'")
    text = re.sub(r"\s+", " ", text)
    return text


def _strip_parenthetical(text: str) -> str:
    return _normalize(re.sub(r"\s*\([^)]*\)\s*", " ", text))


def _split_seed_aliases(raw_name: str) -> list[str]:
    """Generate query aliases from a raw CSV cell.

    The list is ordered from most specific to least specific. Only separators
    with a strong chance of denoting multiple names are split aggressively.
    """

    base = _normalize_seed(raw_name)
    if not base:
        return []

    aliases: list[str] = []

    def add(value: str) -> None:
        cleaned = _normalize_seed(value)
        if cleaned and cleaned not in aliases:
            aliases.append(cleaned)

    add(base)
    add(_strip_parenthetical(base))
    add(base.replace("_", " "))

    if ";" in base or "|" in base:
        for part in re.split(r"[;|]", base):
            add(part)

    if " / " in base:
        for part in base.split(" / "):
            add(part)

    if " - " in base:
        parts = [part.strip() for part in base.split(" - ") if part.strip()]
        for part in parts:
            add(part)
        if len(parts) >= 2 and len(parts[-1].split()) <= 4:
            add(parts[-1])

    if "," in base and len(base.split(",")) <= 3:
        parts = [part.strip() for part in base.split(",") if part.strip()]
        for part in parts:
            add(part)

    return aliases[:5]


def _read_seed_records(csv_path: Path) -> list[SeedRecord]:
    """Read unique non-empty values from all CSV columns."""

    seeds: dict[str, SeedRecord] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader, start=2):
            for column_name, value in row.items():
                normalized = _normalize_seed(value or "")
                if not normalized:
                    continue
                key = normalized.lower()
                source_label = f"row {row_index} / {column_name}"
                existing = seeds.get(key)
                if existing is None:
                    seeds[key] = SeedRecord(
                        raw_name=normalized,
                        normalized_name=normalized,
                        sources=[source_label],
                    )
                else:
                    existing.sources.append(source_label)
    return list(seeds.values())


def _search_serper(query: str, num: int = DEFAULT_SEARCH_LIMIT) -> list[dict[str, object]]:
    last_exc: Exception | None = None
    for attempt in range(1, SERPER_MAX_ATTEMPTS + 1):
        try:
            with httpx.Client(timeout=25.0) as client:
                response = client.post(
                    SERPER_URL,
                    headers={
                        "X-API-KEY": scraper_settings.serp_api_key,
                        "Content-Type": "application/json",
                    },
                    json={"q": query, "num": num},
                )
                if response.status_code in SERPER_RETRY_CODES:
                    response.raise_for_status()
                response.raise_for_status()
                payload = response.json()
                organic = payload.get("organic", []) if isinstance(payload, dict) else []
                return organic if isinstance(organic, list) else []
        except (httpx.HTTPError, ValueError) as exc:
            last_exc = exc
            if attempt >= SERPER_MAX_ATTEMPTS:
                break
            time.sleep(SERPER_RETRY_DELAY_SECONDS * attempt)
    if last_exc is not None:
        raise last_exc
    return []


def _strict_channel_candidate(url: str) -> ChannelUrlCandidate | None:
    candidate = canonicalize_channel_url(url)
    if candidate is None or candidate.platform not in SUPPORTED_PLATFORMS:
        return None

    parsed = urlsplit(candidate.channel_url)
    path_parts = [part for part in parsed.path.split("/") if part]

    if candidate.platform == "rumble":
        if len(path_parts) != 2 or path_parts[0] not in {"c", "user"}:
            return None
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,127}", path_parts[1] or ""):
            return None
    elif candidate.platform == "substack":
        if len(path_parts) != 1 or not path_parts[0].startswith("@"):
            return None
        handle = path_parts[0][1:]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", handle):
            return None
    return candidate


def _extract_candidates_from_result(item: dict[str, object]) -> list[ChannelUrlCandidate]:
    values: list[str] = []
    for key in ("link", "title", "snippet", "displayedLink"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    blob = " ".join(values)
    candidates: dict[str, ChannelUrlCandidate] = {}
    for value in values:
        candidate = _strict_channel_candidate(value)
        if candidate is not None:
            candidates[candidate.channel_url] = candidate
    for candidate in extract_supported_channel_urls(blob):
        strict_candidate = _strict_channel_candidate(candidate.channel_url)
        if strict_candidate is not None:
            candidates[strict_candidate.channel_url] = strict_candidate
    return list(candidates.values())


def _normalize_for_match(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _score_candidate(
    candidate: ChannelUrlCandidate,
    seed_name: str,
    query: str,
    item: dict[str, object],
    verified_name: str | None = None,
) -> float:
    score = 0.45
    seed_norm = _normalize_for_match(seed_name)
    title = _normalize_for_match(str(item.get("title") or ""))
    snippet = _normalize_for_match(str(item.get("snippet") or ""))
    link = str(item.get("link") or "").lower()
    candidate_url = candidate.channel_url.lower()
    path = urlsplit(candidate.channel_url).path
    path_norm = _normalize_for_match(path)

    if seed_norm and seed_norm == path_norm:
        score += 0.30
    elif seed_norm and seed_norm in path_norm:
        score += 0.22

    if seed_norm and seed_norm in title:
        score += 0.18
    elif seed_norm and seed_norm in snippet:
        score += 0.10

    if candidate_url in link:
        score += 0.10

    if candidate.platform == "rumble" and "site:rumble.com" in query:
        score += 0.05
    if candidate.platform == "substack" and "site:substack.com" in query:
        score += 0.05

    if verified_name:
        verified_norm = _normalize_for_match(verified_name)
        if seed_norm and seed_norm == verified_norm:
            score += 0.18
        elif seed_norm and seed_norm in verified_norm:
            score += 0.12

    return round(min(score, 0.99), 2)


def _candidate_queries(seed_name: str) -> list[str]:
    return [
        f'site:rumble.com "{seed_name}"',
        f'site:substack.com "{seed_name}"',
    ]


def _resolve_candidates_for_seed(seed_name: str) -> list[CandidateRecord]:
    seen: set[str] = set()
    results: list[CandidateRecord] = []
    aliases = _split_seed_aliases(seed_name)
    queries = [query for alias in aliases for query in _candidate_queries(alias)]

    for query in queries:
        try:
            serper_results = _search_serper(query=query)
        except Exception:
            continue

        for item in serper_results:
            if not isinstance(item, dict):
                continue
            for candidate in _extract_candidates_from_result(item):
                if candidate.channel_url in seen:
                    continue
                seen.add(candidate.channel_url)
                results.append(
                    CandidateRecord(
                        channel_url=candidate.channel_url,
                        platform=candidate.platform,
                        confidence=_score_candidate(candidate, seed_name, query, item),
                        display_name=_clean_display_name(
                            str(item.get("title") or "").strip() or None, candidate.platform
                        ),
                        source="serper",
                        query=query,
                        evidence=[
                            f"title={str(item.get('title') or '').strip()}",
                            f"link={str(item.get('link') or '').strip()}",
                        ],
                    )
                )

    return sorted(results, key=lambda record: record.confidence, reverse=True)


def _extract_html_title_and_canonical(html: str) -> tuple[str | None, str | None]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = None
    if title_match:
        title = _normalize(re.sub(r"\s+", " ", title_match.group(1)))

    canonical_match = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if canonical_match:
        return title, canonical_match.group(1).strip()

    og_url_match = re.search(
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if og_url_match:
        return title, og_url_match.group(1).strip()

    return title, None


def _clean_display_name(name: str | None, platform: str | None = None) -> str | None:
    if not name:
        return None
    cleaned = _normalize(name)
    cleaned = re.sub(r"\s*[-|]\s*Rumble$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-|]\s*Substack$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-|]\s*Newsletter$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*[-|]\s*Official$", "", cleaned, flags=re.IGNORECASE)
    if platform == "rumble":
        cleaned = re.sub(r"\s*[-|]\s*Rumble\s*$", "", cleaned, flags=re.IGNORECASE)
    elif platform == "substack":
        cleaned = re.sub(r"\s*[-|]\s*Substack\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = _normalize(cleaned)
    return cleaned or None


def _verify_candidate(candidate_url: str) -> tuple[str | None, str | None]:
    """Fetch a candidate page and return ``(title, canonical_url)`` if possible."""

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(candidate_url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            return _extract_html_title_and_canonical(response.text)
    except httpx.HTTPError:
        return None, None


def _display_name_from_candidate(candidate: CandidateRecord, verified_title: str | None) -> str:
    cleaned_verified = _clean_display_name(verified_title, candidate.platform)
    if cleaned_verified:
        return cleaned_verified
    cleaned_candidate = _clean_display_name(candidate.display_name, candidate.platform)
    if cleaned_candidate:
        return cleaned_candidate
    return candidate.channel_url.rstrip("/").split("/")[-1]


def _existing_by_url(client, channel_url: str) -> dict[str, object] | None:
    try:
        result = (
            client.table("channels")
            .select("id,name,channel_url,discovery_evidence_count,discovery_confidence")
            .eq("channel_url", channel_url)
            .maybe_single()
            .execute()
        )
        data = getattr(result, "data", None)
        return data if isinstance(data, dict) else None
    except APIError:
        return None


def _looks_like_fallback_name(name: str, channel_url: str) -> bool:
    fallback = channel_url.rstrip("/").split("/")[-1]
    normalized = _normalize_for_match(name)
    return normalized in {"", _normalize_for_match(fallback), _normalize_for_match(channel_url)}


def _upsert_channel(client, candidate: CandidateRecord, verified_title: str | None) -> str:
    now = _utc_now()
    existing = _existing_by_url(client, candidate.channel_url)
    display_name = _display_name_from_candidate(candidate, verified_title)

    if existing is not None:
        payload: dict[str, object] = {
            "discovery_source": "csv_name_serper_resolver",
            "last_discovery_source": "csv_name_serper_resolver",
            "discovery_confidence": max(
                float(existing.get("discovery_confidence") or 0.0), candidate.confidence
            ),
            "discovery_evidence_count": int(existing.get("discovery_evidence_count") or 0) + 1,
            "discovery_last_seen_at": now,
            "updated_at": now,
        }
        if _looks_like_fallback_name(str(existing.get("name") or ""), candidate.channel_url):
            payload["name"] = display_name
        client.table("channels").update(payload).eq("channel_url", candidate.channel_url).execute()
        return "updated"

    payload = {
        "platform": candidate.platform,
        "channel_url": candidate.channel_url,
        "name": display_name,
        "description": "",
        "contact_info": [],
        "niche_tags": [],
        "is_active": True,
        "has_been_scraped": False,
        "discovery_source": "csv_name_serper_resolver",
        "last_discovery_source": "csv_name_serper_resolver",
        "discovery_status": "new",
        "discovery_confidence": candidate.confidence,
        "discovery_evidence_count": 1,
        "discovery_last_seen_at": now,
        "discovered_at": now,
        "updated_at": now,
    }
    client.table("channels").insert(payload).execute()
    return "inserted"


def _best_candidate(candidates: list[CandidateRecord]) -> CandidateRecord | None:
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)
    top = ordered[0]
    if len(ordered) > 1 and (top.confidence - ordered[1].confidence) < 0.08:
        return None
    if top.confidence < DEFAULT_MIN_CONFIDENCE:
        return None
    return top


def _resolve_seed(seed: SeedRecord) -> dict[str, object]:
    candidates = _resolve_candidates_for_seed(seed.normalized_name)
    verified_title: str | None = None
    verified_url: str | None = None

    if candidates:
        top = candidates[0]
        verified_title, verified_url = _verify_candidate(top.channel_url)
        verified_title = _clean_display_name(verified_title, top.platform)
        if verified_url:
            strict_verified = _strict_channel_candidate(verified_url)
            if strict_verified is not None:
                top = CandidateRecord(
                    channel_url=strict_verified.channel_url,
                    platform=strict_verified.platform,
                    confidence=_score_candidate(
                        strict_verified,
                        seed.normalized_name,
                        top.query,
                        {"title": verified_title or "", "snippet": "", "link": verified_url},
                        verified_name=verified_title,
                    ),
                    display_name=verified_title or top.display_name,
                    source="serper+verified",
                    query=top.query,
                    evidence=top.evidence + [f"verified_url={verified_url}"],
                )
                candidates = [top] + [candidate for candidate in candidates[1:] if candidate.channel_url != top.channel_url]

    best = _best_candidate(candidates)
    return {
        "seed": {
            "raw_name": seed.raw_name,
            "normalized_name": seed.normalized_name,
            "sources": seed.sources,
        },
        "aliases": _split_seed_aliases(seed.normalized_name),
        "candidates": [
            {
                "channel_url": candidate.channel_url,
                "platform": candidate.platform,
                "confidence": candidate.confidence,
                "display_name": candidate.display_name,
                "source": candidate.source,
                "query": candidate.query,
                "evidence": candidate.evidence,
            }
            for candidate in candidates[:5]
        ],
        "best_candidate": None
        if best is None
        else {
            "channel_url": best.channel_url,
            "platform": best.platform,
            "confidence": best.confidence,
            "display_name": best.display_name,
            "source": best.source,
        },
        "verified_title": verified_title,
        "verified_url": verified_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve channel names to Rumble/Substack URLs and optionally write them to channels."
    )
    parser.add_argument(
        "--csv",
        default="scraper/DO NOT CONTACT_CURRENT PARTNERS.csv",
        help="CSV file containing channel names",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help="JSON report path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on the number of unique names processed",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE,
        help="Minimum confidence required to write a channel",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Insert or update matched channels in Supabase",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    seeds = _read_seed_records(csv_path)
    if args.limit > 0:
        seeds = seeds[: args.limit]

    client = get_supabase_client() if args.write else None

    report_rows: list[dict[str, object]] = []
    summary = {
        "mode": "write" if args.write else "dry_run",
        "csv": str(csv_path),
        "total_seeds": len(seeds),
        "inserted": 0,
        "updated": 0,
        "duplicates": 0,
        "unresolved": 0,
        "ambiguous": 0,
        "below_threshold": 0,
        "candidate_urls": 0,
        "generated_at": _utc_now(),
    }

    for index, seed in enumerate(seeds, start=1):
        print(f"[{index}/{len(seeds)}] Resolving: {seed.normalized_name}", flush=True)
        row = _resolve_seed(seed)
        best = row["best_candidate"]
        candidates = row["candidates"]
        summary["candidate_urls"] += len(candidates)

        status = "unresolved"
        action = None
        if isinstance(best, dict):
            if best["confidence"] >= args.min_confidence:
                status = "ready"
                if args.write and client is not None:
                    result = _upsert_channel(
                        client,
                        CandidateRecord(
                            channel_url=str(best["channel_url"]),
                            platform=str(best["platform"]),
                            confidence=float(best["confidence"]),
                            display_name=str(best.get("display_name") or "") or None,
                            source=str(best.get("source") or "serper"),
                            query="",
                        ),
                        row.get("verified_title") if isinstance(row.get("verified_title"), str) else None,
                    )
                    action = result
                    summary[result] += 1
                    if result == "updated":
                        summary["duplicates"] += 1
                else:
                    action = "candidate"
            else:
                status = "below_threshold"
                summary["below_threshold"] += 1
        else:
            summary["unresolved"] += 1

        if status == "ready" and action is None:
            summary["duplicates"] += 0

        if status == "unresolved" and len(candidates) > 1:
            summary["ambiguous"] += 1

        report_rows.append(
            {
                **row,
                "status": status,
                "action": action,
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary,
        "rows": report_rows,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Report written: {output_path}")


if __name__ == "__main__":
    main()
