"""
Remove Auth + Firestore rows created by the legacy generate_data.py demo emails.

Deletes Firebase Auth users for donor1..10@foodbridge.dev and ngo1..3@foodbridge.dev,
their users/{uid}, donors/* / ngos/*, slave_bots for donors, matching donations,
fixed IDs don_000–don_014, and seeded heatmap_zones docs.

Does NOT touch superadmin@ / municipal@ or other accounts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import firebase_admin
from firebase_admin import auth, firestore

from app.core.config import get_settings

settings = get_settings()
cred_path = settings.firebase_admin_credentials
if not firebase_admin._apps:
    cred = firebase_admin.credentials.Certificate(str(cred_path))
    firebase_admin.initialize_app(cred)

db = firestore.client()

SEEDED_AUTH_EMAILS = [f"donor{i}@foodbridge.dev" for i in range(1, 11)] + [
    f"ngo{i}@foodbridge.dev" for i in range(1, 4)
]

SEEDED_DONATION_IDS = [f"don_{i:03d}" for i in range(15)]

SEEDED_HEATMAP_DOC_IDS = [
    z.lower().replace(" ", "_")
    for z in ["Kukatpally", "Gachibowli", "Madhapur", "Begumpet", "Khairatabad", "Shaikpet", "Yousufguda", "Old City"]
]


def main() -> None:
    deleted_auth = 0
    skipped = 0

    # Fixed donation IDs from legacy seed
    for did in SEEDED_DONATION_IDS:
        ref = db.collection("donations").document(did)
        snap = ref.get()
        if snap.exists:
            ref.delete()
            print(f"Deleted donation doc {did}")

    for hid in SEEDED_HEATMAP_DOC_IDS:
        ref = db.collection("heatmap_zones").document(hid)
        snap = ref.get()
        if snap.exists:
            ref.delete()
            print(f"Deleted heatmap_zones/{hid}")

    for email in SEEDED_AUTH_EMAILS:
        try:
            user_record = auth.get_user_by_email(email)
        except auth.UserNotFoundError:
            print(f"Skip (not found): {email}")
            skipped += 1
            continue

        uid = user_record.uid
        user_snap = db.collection("users").document(uid).get()
        data = user_snap.to_dict() or {}
        entity_id = data.get("entity_id")
        role = data.get("role")

        if entity_id:
            if role == "donor":
                for doc in db.collection("donations").where("donor_id", "==", entity_id).limit(500).stream():
                    doc.reference.delete()
                    print(f"  Removed donation {doc.id} (donor {entity_id})")
                sb = db.collection("slave_bots").document(entity_id).get()
                if sb.exists:
                    db.collection("slave_bots").document(entity_id).delete()
                    print(f"  Removed slave_bots/{entity_id}")
                dr = db.collection("donors").document(entity_id).get()
                if dr.exists:
                    db.collection("donors").document(entity_id).delete()
                    print(f"  Removed donors/{entity_id}")
            elif role == "ngo_coordinator":
                nr = db.collection("ngos").document(entity_id).get()
                if nr.exists:
                    db.collection("ngos").document(entity_id).delete()
                    print(f"  Removed ngos/{entity_id}")

        if user_snap.exists:
            db.collection("users").document(uid).delete()
            print(f"  Removed users/{uid}")

        auth.delete_user(uid)
        print(f"Deleted Auth user {email} ({uid})")
        deleted_auth += 1

    print("")
    print(f"Done. Removed {deleted_auth} Auth accounts; {skipped} emails not found.")


if __name__ == "__main__":
    main()
