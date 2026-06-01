from __future__ import annotations

import os
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env() -> None:
    env_path = repo_root() / ".env.local"
    if not env_path.exists():
        print(f"Missing {env_path}; set FIREBASE_* env vars manually.", file=sys.stderr)
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line or line.startswith("export "):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def contract_version_from_scan(scan: dict | None) -> int:
    if not scan or not isinstance(scan, dict):
        return 1
    if scan.get("model_id") and scan.get("model_version"):
        return 2
    return 1


def main() -> None:
    load_env()
    cred_path = os.environ.get("FIREBASE_ADMIN_CREDENTIALS")
    project_id = os.environ.get("FIREBASE_PROJECT_ID")
    if not cred_path or not project_id:
        print("FIREBASE_ADMIN_CREDENTIALS and FIREBASE_PROJECT_ID are required.", file=sys.stderr)
        sys.exit(1)

    cred = credentials.Certificate(cred_path)
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred, {"projectId": project_id})

    db = firestore.client()
    updates = 0
    for doc in db.collection("donations").stream():
        data = doc.to_dict() or {}
        desired = contract_version_from_scan(data.get("scan"))
        current = data.get("scan_contract_version")
        if current == desired:
            continue
        doc.reference.set({"scan_contract_version": desired}, merge=True)
        updates += 1
        print(f"{doc.id}: scan_contract_version -> {desired}")

    print(f"Done. Updated {updates} donation documents.")


if __name__ == "__main__":
    main()
