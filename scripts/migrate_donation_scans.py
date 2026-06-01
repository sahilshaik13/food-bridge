"""
One-time backfill: copy embedded `donation.scan` into Firestore collection `donation_scans`.

Run from repo root (loads `.env.local` like other scripts):

  python scripts/migrate_donation_scans.py

Idempotent: skips documents whose id `migr_<donation_id>` already exists.
"""

from __future__ import annotations

import os
import sys
import warnings

# Importing `app` pulls google-cloud libs that emit noisy Python EOL FutureWarnings.
warnings.filterwarnings("ignore", category=FutureWarning)
from datetime import datetime, timezone
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


def main() -> None:
    load_env()
    sys.path.insert(0, str(repo_root() / "backend"))

    from app.models import DonationScanRecord, GeminiScan
    from app.services.demo_store import coerce_legacy_donation_payload

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
    inserted = 0
    skipped = 0
    errors = 0

    for doc in db.collection("donations").stream():
        migr_id = f"migr_{doc.id}"
        if db.collection("donation_scans").document(migr_id).get().exists:
            skipped += 1
            continue
        raw = doc.to_dict() or {}
        if not raw.get("id"):
            raw["id"] = doc.id
        try:
            fixed = coerce_legacy_donation_payload(dict(raw))
            scan_dict = fixed.get("scan")
            if not scan_dict:
                skipped += 1
                continue
            try:
                scan = GeminiScan.model_validate(scan_dict)
            except Exception:
                nd = dict(scan_dict)
                nd.pop("generated_at", None)
                scan = GeminiScan.model_validate(nd)

            donor_id = fixed.get("donor_id") or raw.get("donor_id") or "unknown"
            ca = fixed.get("created_at") or raw.get("created_at")
            if isinstance(ca, datetime):
                created_at = ca if ca.tzinfo is not None else ca.replace(tzinfo=timezone.utc)
            else:
                created_at = datetime.now(timezone.utc)

            rec = DonationScanRecord(
                id=migr_id,
                donation_id=fixed.get("id") or doc.id,
                donor_id=str(donor_id),
                kind="migrated_from_donation",
                scan=scan,
                created_at=created_at,
            )
            db.collection("donation_scans").document(migr_id).set(rec.model_dump(mode="json"))
            inserted += 1
            print(f"{migr_id}: donation {doc.id}")
        except Exception as exc:
            errors += 1
            print(f"Error on {doc.id}: {exc}", file=sys.stderr)

    print(f"Done. Inserted {inserted}, skipped (already present or no scan) {skipped}, errors {errors}.")


if __name__ == "__main__":
    main()
