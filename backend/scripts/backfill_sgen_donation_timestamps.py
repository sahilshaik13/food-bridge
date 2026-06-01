"""
Backfill created_at/updated_at/completed_at for sample donations (id prefix sgen_).

Run after upgrading generate_data.py so historical sgen_* rows match completed-donation shape.
Idempotent: only sets fields when missing or when --force.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import random

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import firebase_admin
from firebase_admin import firestore

from app.core.config import get_settings

settings = get_settings()
if not firebase_admin._apps:
    cred = firebase_admin.credentials.Certificate(str(settings.firebase_admin_credentials))
    firebase_admin.initialize_app(cred)

db = firestore.client()


def _as_utc_dt(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Overwrite existing completed_at/updated_at")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only")
    args = ap.parse_args()

    updated = 0
    skipped = 0

    for doc in db.collection("donations").limit(2000).stream():
        if not doc.id.startswith("sgen_"):
            continue
        d = doc.to_dict() or {}
        created = _as_utc_dt(d.get("created_at")) or datetime.now(timezone.utc)
        if d.get("completed_at") and d.get("updated_at") and not args.force:
            skipped += 1
            continue

        meal_count = int(d.get("meal_count") or 100)
        rng = random.Random(doc.id)
        hours = rng.randint(2, 48)
        completed = created + timedelta(hours=hours)
        meals_served = d.get("completed_meals_served")
        if meals_served is None or args.force:
            lo = max(1, meal_count // 2)
            meals_served = rng.randint(lo, meal_count)

        payload = {
            "updated_at": completed,
            "completed_at": completed,
        }
        if args.force or d.get("completed_meals_served") is None:
            payload["completed_meals_served"] = meals_served

        if args.dry_run:
            print(f"Would update {doc.id}: {payload}")
            updated += 1
            continue

        doc.reference.update(payload)
        updated += 1

    print(f"Done. Updated {updated} sgen_* donations; skipped {skipped} (already had timestamps, use --force to overwrite).")


if __name__ == "__main__":
    main()
