"""Quick sanity check: donors, ngos, donations, heatmap_zones counts + one sample doc."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import firebase_admin
from firebase_admin import firestore

from app.core.config import get_settings

settings = get_settings()
if not firebase_admin._apps:
    cred = firebase_admin.credentials.Certificate(str(settings.firebase_admin_credentials))
    firebase_admin.initialize_app(cred)

db = firestore.client()


def main() -> None:
    donors = list(db.collection("donors").limit(500).stream())
    ngos = list(db.collection("ngos").limit(500).stream())
    donations = list(db.collection("donations").limit(500).stream())
    zones = list(db.collection("heatmap_zones").limit(50).stream())

    print("Counts (first 500 docs per collection):")
    print(f"  donors:        {len(donors)}")
    print(f"  ngos:          {len(ngos)}")
    print(f"  donations:     {len(donations)}")
    print(f"  heatmap_zones: {len(zones)}")

    sample_gen = [d for d in donations if d.id.startswith("sgen_")]
    print(f"  sgen_* donations (from generate_data sample mode): {len(sample_gen)}")

    if donations:
        one = donations[0].to_dict() or {}
        print("\nSample donation fields:", sorted(one.keys()))
        print("Sample donation id:", donations[0].id)
        for k in ("donor_id", "donor_name", "status", "assigned_ngo_id", "food_type"):
            print(f"  {k}: {one.get(k)!r}")

    if zones:
        z = zones[0].to_dict() or {}
        print("\nSample heatmap_zones fields:", sorted(z.keys()))


if __name__ == "__main__":
    main()
