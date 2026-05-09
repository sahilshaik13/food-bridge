from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore


def load_env() -> None:
    env_path = Path("D:/food-bridge/.env.local")
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_env()
    cred_path = os.environ["FIREBASE_ADMIN_CREDENTIALS"]
    project_id = os.environ["FIREBASE_PROJECT_ID"]
    cred = credentials.Certificate(cred_path)
    try:
        firebase_admin.get_app()
    except Exception:
        firebase_admin.initialize_app(cred, {"projectId": project_id})

    db = firestore.client()
    docs = list(db.collection("donations").stream())
    updates = 0
    for doc in docs:
        data = doc.to_dict() or {}
        status = data.get("status")
        completed_at = data.get("completed_at")
        delivery_confirmed_at = data.get("delivery_confirmed_at")
        volunteer_task_status = data.get("volunteer_task_status")

        # Normalize inconsistent states into completed so history pages can show correctly.
        should_complete = (
            status not in {"completed", "declined", "expired", "wasted"}
            and (
                completed_at is not None
                or delivery_confirmed_at is not None
                or volunteer_task_status in {"delivered_pending_confirmation", "delivered_confirmed"}
            )
        )
        if not should_complete:
            continue

        patch = {
            "status": "completed",
            "updated_at": datetime.now(timezone.utc),
        }
        if completed_at is None:
            patch["completed_at"] = datetime.now(timezone.utc)
        doc.reference.set(patch, merge=True)
        updates += 1
        print(f"normalized {doc.id}: {status} -> completed")

    print(f"done. updated {updates} donation docs")


if __name__ == "__main__":
    main()
