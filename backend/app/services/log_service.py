from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.cloud_clients import get_firestore_client

ACTIVE_LOG_COLLECTION = "app_logs"
ARCHIVE_LOG_COLLECTION = "app_logs_archive"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log_event(
    event_type: str,
    actor_id: str | None = None,
    donation_id: str | None = None,
    status: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Write a structured app event log into Firestore."""
    db = get_firestore_client()
    created_at = _now()
    db.collection(ACTIVE_LOG_COLLECTION).document(f"log_{uuid4().hex[:16]}").set(
        {
            "event_type": event_type,
            "actor_id": actor_id,
            "donation_id": donation_id,
            "status": status,
            "payload": payload or {},
            "created_at": created_at,
            "expire_at": created_at + timedelta(days=7),
        }
    )


def rotate_expired_logs() -> dict[str, int]:
    """
    Move 7-day old active logs to archive (retained 30 more days),
    then delete 30-day old archived logs permanently.
    """
    db = get_firestore_client()
    now = _now()
    moved = 0
    purged = 0

    # Move expired active logs -> archive.
    active_query = db.collection(ACTIVE_LOG_COLLECTION).where("expire_at", "<=", now).stream()
    for doc in active_query:
        data = doc.to_dict() or {}
        archive_payload = {
            **data,
            "archived_at": now,
            "archive_expire_at": now + timedelta(days=30),
        }
        db.collection(ARCHIVE_LOG_COLLECTION).document(doc.id).set(archive_payload)
        doc.reference.delete()
        moved += 1

    # Purge expired archive logs.
    archive_query = db.collection(ARCHIVE_LOG_COLLECTION).where("archive_expire_at", "<=", now).stream()
    for doc in archive_query:
        doc.reference.delete()
        purged += 1

    return {"moved_to_archive": moved, "purged_permanently": purged}
