import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(ROOT / "backend"))

from app.core.cloud_clients import initialize_firebase_app, get_firestore_client


def load_env() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_env()
    initialize_firebase_app()
    db = get_firestore_client()

    volunteers_by_ngo: dict[str, str] = {}
    for doc in db.collection("users").where("role", "==", "ngo_volunteer").stream():
        data = doc.to_dict() or {}
        ngo_id = data.get("entity_id")
        uid = data.get("id") or doc.id
        if ngo_id and uid and ngo_id not in volunteers_by_ngo:
            volunteers_by_ngo[ngo_id] = uid

    if not volunteers_by_ngo:
        print("No volunteer users found. Nothing to seed.")
        return

    donations_ref = db.collection("donations")
    completed_docs = donations_ref.where("status", "==", "completed").stream()
    batch = db.batch()
    touched = 0

    for doc in completed_docs:
        data = doc.to_dict() or {}
        ngo_id = data.get("assigned_ngo_id")
        if not ngo_id:
            notified = data.get("notified_ngo_ids") or []
            if isinstance(notified, list) and notified:
                ngo_id = notified[0]
        if not ngo_id:
            queue = data.get("ngo_queue") or []
            if isinstance(queue, list) and queue:
                top = queue[0] or {}
                ngo_id = top.get("ngo_id")
        volunteer_uid = data.get("volunteer_uid")
        if not ngo_id or volunteer_uid:
            continue
        uid = volunteers_by_ngo.get(ngo_id)
        if not uid:
            continue

        def parse_dt(value):
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        created_at = parse_dt(data.get("created_at"))
        accepted_at = parse_dt(data.get("accepted_at")) or parse_dt(data.get("updated_at"))
        completed_at = parse_dt(data.get("completed_at")) or parse_dt(data.get("updated_at"))

        patch = {
            "volunteer_uid": uid,
            "seeded_volunteer_uid_at": datetime.now(timezone.utc),
        }
        if accepted_at and created_at and not data.get("acceptance_seconds"):
            patch["acceptance_seconds"] = int((accepted_at - created_at).total_seconds())
            patch["accepted_at"] = accepted_at
        if completed_at and accepted_at and not data.get("delivery_seconds"):
            patch["delivery_seconds"] = int((completed_at - accepted_at).total_seconds())
            patch["completed_at"] = completed_at

        batch.set(doc.reference, patch, merge=True)
        touched += 1
        if touched % 400 == 0:
            batch.commit()
            batch = db.batch()

    if touched % 400 != 0:
        batch.commit()

    print(f"Seed complete. Updated {touched} completed donations.")


if __name__ == "__main__":
    main()
