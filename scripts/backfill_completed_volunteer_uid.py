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
        if not line or line.startswith("#") or "=" not in line or line.startswith("export "):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_env()
    cred = credentials.Certificate(os.environ["FIREBASE_ADMIN_CREDENTIALS"])
    try:
        firebase_admin.get_app()
    except Exception:
        firebase_admin.initialize_app(cred, {"projectId": os.environ["FIREBASE_PROJECT_ID"]})

    db = firestore.client()
    volunteer_users = {}
    for doc in db.collection("users").stream():
        data = doc.to_dict() or {}
        if data.get("role") == "ngo_volunteer" and data.get("entity_id"):
            volunteer_users[data["entity_id"]] = {
                "uid": data.get("id") or doc.id,
                "display_name": data.get("display_name"),
            }

    updates = 0
    for doc in db.collection("donations").stream():
        data = doc.to_dict() or {}
        if data.get("status") != "completed" and not data.get("completed_at"):
            continue
        ngo_id = data.get("assigned_ngo_id")
        if not ngo_id or ngo_id not in volunteer_users:
            continue
        mapped = volunteer_users[ngo_id]
        if data.get("volunteer_uid") == mapped["uid"]:
            continue
        patch = {
            "volunteer_uid": mapped["uid"],
            "volunteer_name": mapped["display_name"] or data.get("volunteer_name"),
            "updated_at": datetime.now(timezone.utc),
        }
        doc.reference.set(patch, merge=True)
        updates += 1
        print(f"patched {doc.id}: volunteer_uid -> {mapped['uid']}")

    print(f"done. updated {updates} completed donation docs")


if __name__ == "__main__":
    main()
