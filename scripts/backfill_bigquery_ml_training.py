"""
Backfill BigQuery ML training table from Firestore `donations` (Phase 6).

Requires: GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_CLOUD_PROJECT, FIREBASE_* for Firestore.
Target table must already exist (run API once with ML_EXPORT_TO_BIGQUERY=true, or create manually).

Uses event_type `backfill_snapshot` per donation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import bigquery


def load_env() -> None:
    env_path = ROOT / ".env.local"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line or line.startswith("export "):
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_TERMINAL = frozenset({"completed", "wasted", "expired", "declined"})


def main() -> None:
    load_env()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        print("GOOGLE_CLOUD_PROJECT required", file=sys.stderr)
        sys.exit(1)

    cred_path = os.environ.get("FIREBASE_ADMIN_CREDENTIALS")
    pid = os.environ.get("FIREBASE_PROJECT_ID")
    if not cred_path or not pid:
        print("FIREBASE_ADMIN_CREDENTIALS and FIREBASE_PROJECT_ID required", file=sys.stderr)
        sys.exit(1)

    cred = credentials.Certificate(cred_path)
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred, {"projectId": pid})

    from app.models import Donation, MatchScore
    from app.services.ml_training_export_service import donation_event_to_row

    db_fs = firestore.client()
    bq_dataset = os.environ.get("BIGQUERY_ML_DATASET", "foodbridge_ml")
    bq_table = os.environ.get("BIGQUERY_ML_TABLE", "donation_training_events")
    table_ref = f"{project}.{bq_dataset}.{bq_table}"

    bq = bigquery.Client(project=project)
    try:
        bq.get_table(table_ref)
    except Exception as exc:
        print(f"Table {table_ref} missing: {exc}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for doc in db_fs.collection("donations").stream():
        data = doc.to_dict() or {}
        if not data.get("id"):
            data["id"] = doc.id
        try:
            data["ngo_queue"] = [MatchScore(**q) for q in data.get("ngo_queue", [])]
            d = Donation(**data)
            tl = d.status.value if d.status.value in _TERMINAL else None
            rows.append(donation_event_to_row(d, "backfill_snapshot", terminal_label=tl))
        except Exception as e:
            print(f"skip {doc.id}: {e}", file=sys.stderr)

    batch = 500
    total = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i : i + batch]
        errors = bq.insert_rows_json(table_ref, chunk)
        if errors:
            print(f"BigQuery errors batch {i}: {errors}", file=sys.stderr)
        total += len(chunk)
        print(f"inserted {total} / {len(rows)}")

    print(f"done. {len(rows)} rows attempted.")


if __name__ == "__main__":
    main()
