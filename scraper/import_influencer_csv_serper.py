"""Resolve influencer names to Rumble/Substack channels via Serper.

Standalone utility:
- Reads a CSV of influencer rows.
- Searches Serper for likely Rumble/Substack channel URLs.
- Canonicalizes URLs using shared channel URL logic.
- Defaults to dry-run (no DB writes).
- Optional --write inserts net-new channels after duplicate checks by channel_url.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from postgrest.exceptions import APIError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import scraper_settings
from core.supabase import get_supabase_client
from utils.channel_urls import ChannelUrlCandidate, canonicalize_channel_url, extract_supported_channel_urls

SERPER_URL = "https://google.serper.dev/search"
SERPER_RETRY_CODES = {408, 425, 429, 500, 502, 503, 504}
SERPER_MAX_ATTEMPTS = 3
SERPER_RETRY_DELAY_SECONDS = 1.5


@dataclass
class InfluencerRow:
    influencer: str
    category: str
    notes: str
    contact: str
    social_urls: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join((text or "").strip().split())


def _read_rows(csv_path: Path) -> list[InfluencerRow]:
    rows: list[InfluencerRow] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            influencer = _norm(str(raw.get("Influencer", "")))
            if not influencer:
                continue
            rows.append(
                InfluencerRow(
                    influencer=influencer,
                    category=_norm(str(raw.get("Category", ""))),
                    notes=_norm(str(raw.get("Notes", ""))),
                    contact=_norm(str(raw.get("Contact email, URL or Phone", ""))),
                    social_urls=_norm(str(raw.get("Social URL's", ""))),
                )
            )
    return rows


def _search_serper(query: str, num: int = 10) -> list[dict[str, object]]:
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


def _extract_candidates_from_result(item: dict[str, object]) -> list[ChannelUrlCandidate]:
    values: list[str] = []
    for key in ("link", "title", "snippet", "displayedLink"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            values.append(v.strip())
    blob = " ".join(values)
    candidates: dict[str, ChannelUrlCandidate] = {}
    for value in values:
        c = canonicalize_channel_url(value)
        if c is not None:
            candidates[c.channel_url] = c
    for c in extract_supported_channel_urls(blob):
        candidates[c.channel_url] = c
    return list(candidates.values())


def _confidence(candidate: ChannelUrlCandidate, influencer: str, query: str, item: dict[str, object]) -> float:
    score = 0.55
    if f"site:{candidate.platform}.com" in query:
        score += 0.1
    link = str(item.get("link") or "").lower()
    title = str(item.get("title") or "").lower()
    snippet = str(item.get("snippet") or "").lower()
    infl = influencer.lower()
    if infl and infl in title:
        score += 0.2
    elif infl and infl in snippet:
        score += 0.1
    if candidate.channel_url.lower() in link:
        score += 0.1
    return round(min(score, 0.99), 2)


def _queries_for(name: str) -> list[str]:
    clean = name.strip()
    return [
        f'site:rumble.com "{clean}" (inurl:/c/ OR inurl:/user/ OR rumble.com/)',
        f'site:substack.com "{clean}" (inurl:/@ OR inurl:.substack.com)',
    ]


def _resolve_influencer(name: str) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    seen: set[str] = set()
    for query in _queries_for(name):
        try:
            results = _search_serper(query=query, num=10)
        except Exception:
            continue
        for item in results:
            if not isinstance(item, dict):
                continue
            for candidate in _extract_candidates_from_result(item):
                if candidate.channel_url in seen:
                    continue
                seen.add(candidate.channel_url)
                matches.append(
                    {
                        "channel_url": candidate.channel_url,
                        "platform": candidate.platform,
                        "confidence": _confidence(candidate, name, query, item),
                        "query": query,
                        "title": str(item.get("title") or ""),
                        "link": str(item.get("link") or ""),
                    }
                )
    return sorted(matches, key=lambda m: float(m["confidence"]), reverse=True)


def _existing_by_url(client, channel_url: str) -> dict[str, object] | None:
    try:
        result = (
            client.table("channels")
            .select("id,channel_url")
            .eq("channel_url", channel_url)
            .maybe_single()
            .execute()
        )
        data = getattr(result, "data", None)
        return data if isinstance(data, dict) else None
    except APIError:
        return None


def _insert_channel(client, row: InfluencerRow, match: dict[str, object]) -> str:
    url = str(match["channel_url"])
    existing = _existing_by_url(client, url)
    if existing is not None:
        return "duplicate"

    payload = {
        "platform": str(match["platform"]),
        "channel_url": url,
        "name": row.influencer,
        "description": row.notes,
        "contact_info": [v for v in [row.contact] if v],
        "niche_tags": [row.category] if row.category else [],
        "is_active": True,
        "has_been_scraped": False,
        "discovery_source": "csv_serper_import",
        "last_discovery_source": "csv_serper_import",
        "discovery_status": "new",
        "discovery_confidence": float(match["confidence"]),
        "discovery_evidence_count": 1,
        "discovery_last_seen_at": _utc_now(),
        "discovered_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    client.table("channels").insert(payload).execute()
    return "inserted"


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve influencer CSV names to channel URLs with Serper.")
    parser.add_argument("--csv", default="Influencer - Influencer search.csv", help="Path to source CSV")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit for testing")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="Only keep matches at/above this score")
    parser.add_argument("--write", action="store_true", help="Insert into DB (default is dry-run)")
    parser.add_argument(
        "--output",
        default="scraper/output/influencer_serper_matches.json",
        help="Output JSON report path",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows = _read_rows(csv_path)
    if args.limit > 0:
        rows = rows[: args.limit]

    report_rows: list[dict[str, object]] = []
    summary = {
        "total_rows": len(rows),
        "matched_rows": 0,
        "unmatched_rows": 0,
        "candidate_urls": 0,
        "would_insert": 0,
        "duplicates": 0,
        "inserted": 0,
        "mode": "write" if args.write else "dry_run",
    }

    client = get_supabase_client() if args.write else None
    for idx, row in enumerate(rows, start=1):
        print(f"[{idx}/{len(rows)}] Resolving: {row.influencer}", flush=True)
        matches = [m for m in _resolve_influencer(row.influencer) if float(m["confidence"]) >= args.min_confidence]
        print(f"[{idx}/{len(rows)}] Matches >= {args.min_confidence}: {len(matches)}", flush=True)
        summary["candidate_urls"] += len(matches)
        if matches:
            summary["matched_rows"] += 1
        else:
            summary["unmatched_rows"] += 1

        actions: list[dict[str, str]] = []
        for match in matches:
            if args.write and client is not None:
                status = _insert_channel(client, row, match)
                if status == "inserted":
                    summary["inserted"] += 1
                elif status == "duplicate":
                    summary["duplicates"] += 1
                actions.append({"channel_url": str(match["channel_url"]), "status": status})
            else:
                summary["would_insert"] += 1
                actions.append({"channel_url": str(match["channel_url"]), "status": "candidate"})

        report_rows.append(
            {
                "row_index": idx,
                "influencer": row.influencer,
                "category": row.category,
                "matches": matches,
                "actions": actions,
            }
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_payload = {"summary": summary, "rows": report_rows}
    output_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Report written: {output_path}")


if __name__ == "__main__":
    main()
