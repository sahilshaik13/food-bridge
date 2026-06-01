"""
Sample Firestore data for FoodBridge.

Default: create completed donation documents using **existing** `donors` and `ngos` in
Firestore (names, locations, IDs from your database). Does **not** create Auth users.

Optional: `legacy-auth-and-seed` recreates the old static demo (donor1@… / ngo1@…) — avoid
in production; use `delete_seed_demo_accounts.py` to remove that cohort.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import random
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import firebase_admin
from firebase_admin import auth, firestore

from app.core.config import get_settings
from app.models import Role

settings = get_settings()
cred_path = settings.firebase_admin_credentials
if not firebase_admin._apps:
    cred = firebase_admin.credentials.Certificate(str(cred_path))
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --------------------------------------------------------------------------- legacy (optional)
DONORS_DATA = [
    {"name": "Barbeque Nation", "company": "M/S. BARBEQUE NATION HOSPITALITY LTD", "license": "13618013000425", "area": "Kukatpally", "lat": 17.493600, "lng": 78.399800, "email": "donor1@foodbridge.dev"},
    {"name": "Shah Ghouse", "company": "M/S. SHAH GHOUSE HOTEL AND RESTAURANT", "license": "13618013000000", "area": "Gachibowli", "lat": 17.426700, "lng": 78.346900, "email": "donor2@foodbridge.dev"},
    {"name": "Royal Bawarchi", "company": "M/S ROYAL BAWARCHI", "license": "13623013000591", "area": "Hafeezpet", "lat": 17.483300, "lng": 78.361400, "email": "donor3@foodbridge.dev"},
    {"name": "Southern Spice", "company": "SOUTHERN SPICE", "license": "13625013000760", "area": "Madhapur", "lat": 17.448500, "lng": 78.390800, "email": "donor4@foodbridge.dev"},
    {"name": "Vibrant Living", "company": "VIBRANT LIVING PRIVATE LIMITED", "license": "13621999000076", "area": "Raidurg", "lat": 17.423000, "lng": 78.334500, "email": "donor5@foodbridge.dev"},
    {"name": "Peshawar Restaurant", "company": "M/s. PESHAWAR RESTAURANT", "license": "13625014000164", "area": "Begumpet", "lat": 17.443800, "lng": 78.463400, "email": "donor6@foodbridge.dev"},
    {"name": "Bamboo Tree Hotels", "company": "M/s. MANDILIOUS", "license": "13623013000334", "area": "KPHB", "lat": 17.494700, "lng": 78.388000, "email": "donor7@foodbridge.dev"},
    {"name": "Lebanese Bites", "company": "LEBANESE BITES", "license": "13623011001097", "area": "Khairatabad", "lat": 17.412700, "lng": 78.454500, "email": "donor8@foodbridge.dev"},
    {"name": "Mehfil Restaurant", "company": "MEHFIL RESTAURANT", "license": "13620013000550", "area": "Shaikpet", "lat": 17.401200, "lng": 78.415600, "email": "donor9@foodbridge.dev"},
    {"name": "Sri Udupi Grand", "company": "SRI UDUPI GRAND", "license": "13621011000901", "area": "Yousufguda", "lat": 17.437600, "lng": 78.425800, "email": "donor10@foodbridge.dev"},
]

ADMINS_DATA = [
    {"email": "superadmin@foodbridge.dev", "role": Role.super_admin, "name": "Super Admin"},
    {"email": "municipal@foodbridge.dev", "role": Role.municipal_admin, "name": "Municipal Admin"},
]

NGOS_DATA = [
    {"name": "Robin Hood Army", "area": "Banjara Hills", "lat": 17.423900, "lng": 78.448300, "email": "ngo1@foodbridge.dev", "darpan": "TS/2020/001"},
    {"name": "Hyderabad Food Bank", "area": "Mehdipatnam", "lat": 17.361700, "lng": 78.474700, "email": "ngo2@foodbridge.dev", "darpan": "TS/2018/002"},
    {"name": "Akshaya Patra", "area": "Uppal", "lat": 17.395800, "lng": 78.540600, "email": "ngo3@foodbridge.dev", "darpan": "TS/2021/003"},
]


def _donor_from_doc(doc) -> dict:
    d = doc.to_dict() or {}
    loc = d.get("location") or {}
    return {
        "id": doc.id,
        "name": d.get("name") or "Donor",
        "lat": float(loc.get("lat") or d.get("lat") or 17.385),
        "lng": float(loc.get("lng") or d.get("lng") or 78.4867),
        "area": str(loc.get("area") or d.get("area") or "Hyderabad"),
        "address": str(loc.get("address") or d.get("address") or ""),
    }


def seed_sample_donations_from_firestore(count: int, include_heatmap_zones: bool) -> None:
    donor_docs = list(db.collection("donors").stream())
    ngo_docs = list(db.collection("ngos").stream())
    if not donor_docs:
        print("ERROR: No documents in `donors`. Add donors (onboarding or import) first.")
        sys.exit(1)
    if not ngo_docs:
        print("ERROR: No documents in `ngos`. Add NGOs first.")
        sys.exit(1)

    donors = [_donor_from_doc(x) for x in donor_docs]
    ngo_ids = [x.id for x in ngo_docs]

    batch = db.batch()
    created = 0
    for _ in range(count):
        donor = random.choice(donors)
        don_id = f"sgen_{uuid4().hex[:16]}"
        don_ref = db.collection("donations").document(don_id)
        area = donor["area"]
        created_at = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 90))
        pickup_hours = random.randint(2, 48)
        completed_at = created_at + timedelta(hours=pickup_hours)
        meals = random.randint(50, 200)
        batch.set(
            don_ref,
            {
                "id": don_id,
                "donor_id": donor["id"],
                "donor_name": donor["name"],
                "food_type": random.choice(["biryani", "rice and dal", "veg meals", "bread"]),
                "quantity_kg": round(random.uniform(10.0, 50.0), 2),
                "meal_count": meals,
                "status": "completed",
                "location": {
                    "lat": donor["lat"],
                    "lng": donor["lng"],
                    "area": area,
                    "address": donor["address"] or f"{area}, Hyderabad",
                },
                "assigned_ngo_id": random.choice(ngo_ids),
                "created_at": created_at,
                "updated_at": completed_at,
                "completed_at": completed_at,
                "completed_meals_served": random.randint(max(1, meals // 2), meals),
            },
        )
        created += 1

    if include_heatmap_zones:
        heatmap_zones = ["Kukatpally", "Gachibowli", "Madhapur", "Begumpet", "Khairatabad", "Shaikpet", "Yousufguda", "Old City"]
        for zone in heatmap_zones:
            zone_ref = db.collection("heatmap_zones").document(zone.lower().replace(" ", "_"))
            batch.set(
                zone_ref,
                {
                    "zone_name": zone,
                    "surplus_kg": random.randint(100, 1000) if zone != "Old City" else 20,
                    "demand_kg": random.randint(500, 2000),
                    "gap": "high" if zone == "Old City" else "low",
                    "updated_at": datetime.now(timezone.utc),
                },
            )

    batch.commit()
    print(f"Seeded {created} completed donations from {len(donors)} donors × {len(ngo_ids)} NGOs.")
    if include_heatmap_zones:
        print("Updated heatmap_zones for 8 Hyderabad zones.")


def seed_legacy_auth():
    print("Seeding Auth (legacy demo emails)...")
    for d in DONORS_DATA:
        try:
            user = auth.create_user(email=d["email"], password="Password123")
            auth.set_custom_user_claims(user.uid, {"role": Role.donor})
            d["uid"] = user.uid
            print(f"Created Donor: {d['email']} ({user.uid})")
        except Exception as e:
            print(f"Error creating {d['email']}: {e}")
            user = auth.get_user_by_email(d["email"])
            auth.set_custom_user_claims(user.uid, {"role": Role.donor})
            d["uid"] = user.uid

    for a in ADMINS_DATA:
        try:
            user = auth.create_user(email=a["email"], password="Password123")
            auth.set_custom_user_claims(user.uid, {"role": a["role"]})
            a["uid"] = user.uid
            print(f"Created Admin: {a['email']} ({user.uid})")
        except Exception as e:
            print(f"Error creating {a['email']}: {e}")
            user = auth.get_user_by_email(a["email"])
            auth.set_custom_user_claims(user.uid, {"role": a["role"]})
            a["uid"] = user.uid

    for n in NGOS_DATA:
        try:
            user = auth.create_user(email=n["email"], password="Password123")
            auth.set_custom_user_claims(user.uid, {"role": Role.ngo_coordinator})
            n["uid"] = user.uid
            print(f"Created NGO: {n['email']} ({user.uid})")
        except Exception as e:
            print(f"Error creating {n['email']}: {e}")
            user = auth.get_user_by_email(n["email"])
            auth.set_custom_user_claims(user.uid, {"role": Role.ngo_coordinator})
            n["uid"] = user.uid


def seed_legacy_firestore():
    print("Seeding Firestore (legacy static demo rows)...")
    batch = db.batch()

    for d in DONORS_DATA:
        uid = d.get("uid") or auth.get_user_by_email(d["email"]).uid
        user_ref = db.collection("users").document(uid)
        batch.set(
            user_ref,
            {
                "id": uid,
                "role": "donor",
                "display_name": d["name"],
                "email": d["email"],
                "status": "active",
                "entity_id": f"donor_{uid[:8]}",
                "created_at": datetime.now(timezone.utc),
            },
        )

        donor_ref = db.collection("donors").document(f"donor_{uid[:8]}")
        batch.set(
            donor_ref,
            {
                "id": f"donor_{uid[:8]}",
                "name": d["name"],
                "company_name": d["company"],
                "area": d["area"],
                "fssai_license": d["license"],
                "location": {"lat": d["lat"], "lng": d["lng"], "area": d["area"], "address": f"{d['area']}, Hyderabad"},
                "avg_surplus_kg": "20-40 kg/day",
                "monthly_meals": random.randint(5000, 15000),
                "verification_status": "verified",
                "created_at": datetime.now(timezone.utc),
            },
        )

    for a in ADMINS_DATA:
        uid = a.get("uid") or auth.get_user_by_email(a["email"]).uid
        user_ref = db.collection("users").document(uid)
        batch.set(
            user_ref,
            {
                "id": uid,
                "role": a["role"],
                "display_name": a["name"],
                "email": a["email"],
                "status": "active",
                "created_at": datetime.now(timezone.utc),
            },
        )

    for n in NGOS_DATA:
        uid = n.get("uid") or auth.get_user_by_email(n["email"]).uid
        user_ref = db.collection("users").document(uid)
        batch.set(
            user_ref,
            {
                "id": uid,
                "role": "ngo_coordinator",
                "display_name": n["name"],
                "email": n["email"],
                "status": "verified",
                "entity_id": f"ngo_{uid[:8]}",
                "created_at": datetime.now(timezone.utc),
            },
        )

        ngo_ref = db.collection("ngos").document(f"ngo_{uid[:8]}")
        batch.set(
            ngo_ref,
            {
                "id": f"ngo_{uid[:8]}",
                "name": n["name"],
                "area": n["area"],
                "focus": "Food distribution",
                "ngo_darpan_id": n["darpan"],
                "beneficiary_count": random.randint(200, 500),
                "food_preferences": ["rice", "dal", "biryani"],
                "location": {"lat": n["lat"], "lng": n["lng"], "area": n["area"], "address": f"{n['area']}, Hyderabad"},
                "verification_status": "verified",
                "coordinator_uid": uid,
            },
        )

    print("Seeding Donations (legacy)...")
    ngo_ids = [f"ngo_{auth.get_user_by_email(n['email']).uid[:8]}" for n in NGOS_DATA]
    for i in range(15):
        donor_info = random.choice(DONORS_DATA)
        uid = auth.get_user_by_email(donor_info["email"]).uid
        donor_id = f"donor_{uid[:8]}"
        don_id = f"don_{i:03d}"
        don_ref = db.collection("donations").document(don_id)
        batch.set(
            don_ref,
            {
                "id": don_id,
                "donor_id": donor_id,
                "donor_name": donor_info["name"],
                "food_type": random.choice(["biryani", "rice and dal", "veg meals", "bread"]),
                "quantity_kg": random.uniform(10.0, 50.0),
                "meal_count": random.randint(50, 200),
                "status": "completed",
                "location": {
                    "lat": donor_info["lat"],
                    "lng": donor_info["lng"],
                    "area": donor_info["area"],
                    "address": donor_info["area"],
                },
                "assigned_ngo_id": random.choice(ngo_ids),
                "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30)),
                "completed_meals_served": random.randint(50, 200),
            },
        )

    heatmap_zones = ["Kukatpally", "Gachibowli", "Madhapur", "Begumpet", "Khairatabad", "Shaikpet", "Yousufguda", "Old City"]
    for zone in heatmap_zones:
        zone_ref = db.collection("heatmap_zones").document(zone.lower().replace(" ", "_"))
        batch.set(
            zone_ref,
            {
                "zone_name": zone,
                "surplus_kg": random.randint(100, 1000) if zone != "Old City" else 20,
                "demand_kg": random.randint(500, 2000),
                "gap": "high" if zone == "Old City" else "low",
                "updated_at": datetime.now(timezone.utc),
            },
        )

    batch.commit()
    print("Legacy Firestore seed complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate sample donation rows from existing Firestore entities.")
    parser.add_argument(
        "--mode",
        choices=["sample", "legacy-full"],
        default="sample",
        help="sample = donations from existing donors/ngos only (default). legacy-full = old demo Auth+Firestore (avoid).",
    )
    parser.add_argument("--count", type=int, default=15, help="Number of completed donations to add (sample mode).")
    parser.add_argument(
        "--heatmap",
        action="store_true",
        help="In sample mode, also upsert heatmap_zones documents.",
    )
    args = parser.parse_args()

    if args.mode == "legacy-full":
        seed_legacy_auth()
        seed_legacy_firestore()
    else:
        seed_sample_donations_from_firestore(count=args.count, include_heatmap_zones=args.heatmap)
