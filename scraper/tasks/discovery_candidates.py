"""Shared helpers for staged discovery candidate processing."""

from __future__ import annotations

from datetime import datetime, timezone

def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def stage_candidate(
    *,
    client,
    candidate_url: str,
    platform: str,
    source: str,
    source_ref: str | None,
    title: str | None,
    category: str | None,
    confidence: float,
) -> tuple[bool, bool]:
    """Insert/update a candidate row and return (staged, already_present)."""
    existing = (
        client.table("discovery_candidates")
        .select("id,evidence_count,confidence,status")
        .eq("candidate_url", candidate_url)
        .limit(1)
        .execute()
    )
    now = utc_now_iso()

    if existing.data:
        row = existing.data[0]
        new_evidence = int(row.get("evidence_count") or 0) + 1
        new_confidence = max(float(row.get("confidence") or 0.0), confidence)
        payload = {
            "evidence_count": new_evidence,
            "confidence": new_confidence,
            "last_seen_at": now,
            "updated_at": now,
        }
        if title:
            payload["title"] = title
        if category:
            payload["category"] = category
        if source_ref:
            payload["source_ref"] = source_ref
        client.table("discovery_candidates").update(payload).eq("id", row["id"]).execute()
        return True, True

    payload = {
        "candidate_url": candidate_url,
        "platform": platform,
        "source": source,
        "source_ref": source_ref,
        "title": title,
        "category": category,
        "confidence": confidence,
        "evidence_count": 1,
        "status": "pending",
        "first_seen_at": now,
        "last_seen_at": now,
        "discovered_at": now,
        "updated_at": now,
    }
    client.table("discovery_candidates").insert(payload).execute()
    return True, False


def promote_candidate_to_channel(
    *,
    client,
    candidate: dict[str, object],
) -> bool:
    """Promote one verified candidate to channels and mark promoted on success."""
    now = utc_now_iso()
    payload = {
        "platform": str(candidate["platform"]),
        "channel_url": str(candidate["candidate_url"]),
        "name": str(candidate.get("title") or str(candidate["candidate_url"]).rstrip("/").split("/")[-1]),
        "description": "",
        "is_active": True,
        "discovery_source": f"auto_{candidate.get('source') or 'discovery'}",
        "discovery_confidence": float(candidate.get("confidence") or 0.0),
        "discovered_at": now,
        "updated_at": now,
    }
    if candidate.get("source") == "seed" and candidate.get("source_ref"):
        payload["discovered_from_channel_id"] = str(candidate["source_ref"])

    result = client.table("channels").upsert(payload, on_conflict="channel_url").execute()
    if not result.data:
        return False

    client.table("discovery_candidates").update(
        {
            "status": "promoted",
            "rejection_reason": None,
            "updated_at": now,
        }
    ).eq("id", candidate["id"]).execute()
    return True


def safe_reject_candidate(*, client, candidate_id: str, reason: str) -> None:
    """Mark candidate as rejected with a reason."""
    client.table("discovery_candidates").update(
        {
            "status": "rejected",
            "rejection_reason": reason,
            "updated_at": utc_now_iso(),
        }
    ).eq("id", candidate_id).execute()


def safe_verify_candidate(*, client, candidate_id: str) -> None:
    """Mark candidate as verified."""
    client.table("discovery_candidates").update(
        {
            "status": "verified",
            "rejection_reason": None,
            "updated_at": utc_now_iso(),
        }
    ).eq("id", candidate_id).execute()
