import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from firebase_admin import auth
from app.core.cloud_clients import initialize_firebase_app, get_firestore_client


def now_utc():
    return datetime.now(timezone.utc)


VOLUNTEERS = [
    {
        "email": "robin_hoodvt@foodbridge.dev",
        "display_name": "Robin Hood Volunteer",
        "ngo_id": "ngo_robin_hood",
        "ngo_name": "Robin Hood Army - Hyderabad Chapter",
    },
    {
        "email": "akshaya_patravt@foodbridge.dev",
        "display_name": "Akshaya Patra Volunteer",
        "ngo_id": "ngo_akshaya_patra",
        "ngo_name": "Akshaya Patra Foundation - Hyderabad",
    },
    {
        "email": "ramakrishna_mathvt@foodbridge.dev",
        "display_name": "Ramakrishna Math Volunteer",
        "ngo_id": "ngo_ramakrishna_math",
        "ngo_name": "Ramakrishna Math - Hyderabad",
    },
    {
        "email": "smile_foundationvt@foodbridge.dev",
        "display_name": "Smile Foundation Volunteer",
        "ngo_id": "ngo_smile_foundation",
        "ngo_name": "Smile Foundation - Telangana Chapter",
    },
    {
        "email": "safa_baitul_maalvt@foodbridge.dev",
        "display_name": "Safa Baitul Maal Volunteer",
        "ngo_id": "ngo_safa_baitul_maal",
        "ngo_name": "Safa Baitul Maal Trust",
    },
    {
        "email": "terminate_hungervt@foodbridge.dev",
        "display_name": "Terminate Hunger Volunteer",
        "ngo_id": "ngo_terminate_hunger",
        "ngo_name": "Terminate Hunger Welfare Organisation",
    },
    {
        "email": "helpage_indiavt@foodbridge.dev",
        "display_name": "HelpAge Volunteer",
        "ngo_id": "ngo_helpage_india",
        "ngo_name": "HelpAge India - Hyderabad Regional Office",
    },
    {
        "email": "cryvt@foodbridge.dev",
        "display_name": "CRY Volunteer",
        "ngo_id": "ngo_cry",
        "ngo_name": "Child Rights and You - Hyderabad Chapter",
    },
    {
        "email": "no_food_wastevt@foodbridge.dev",
        "display_name": "No Food Waste Volunteer",
        "ngo_id": "ngo_no_food_waste",
        "ngo_name": "No Food Waste Foundation - Hyderabad",
    },
    {
        "email": "aasravt@foodbridge.dev",
        "display_name": "Aasra Volunteer",
        "ngo_id": "ngo_aasra",
        "ngo_name": "Aasra Foundation Hyderabad",
    },
]

PASSWORD = "Password123"


def main():
    env_path = ROOT / ".env.local"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    initialize_firebase_app()
    db = get_firestore_client()

    print("Seeding NGO volunteers...")
    for item in VOLUNTEERS:
        email = item["email"]
        try:
            user = auth.get_user_by_email(email)
            uid = user.uid
            auth.update_user(uid, password=PASSWORD, display_name=item["display_name"])
            print(f"  updated auth user: {email}")
        except auth.UserNotFoundError:
            user = auth.create_user(email=email, password=PASSWORD, display_name=item["display_name"])
            uid = user.uid
            print(f"  created auth user: {email}")

        auth.set_custom_user_claims(uid, {"role": "ngo_volunteer", "entity_id": item["ngo_id"], "ngo_id": item["ngo_id"]})

        db.collection("users").document(uid).set(
            {
                "id": uid,
                "role": "ngo_volunteer",
                "display_name": item["display_name"],
                "email": email,
                "status": "active",
                "entity_id": item["ngo_id"],
                "created_at": now_utc(),
            },
            merge=True,
        )

        db.collection("volunteers").document(uid).set(
            {
                "id": uid,
                "ngo_id": item["ngo_id"],
                "name": item["display_name"],
                "email": email,
                "phone": None,
                "role": "ngo_volunteer",
                "status": "active",
                "invite_link": f"http://localhost:3000/volunteer?uid={uid}",
                "created_at": now_utc(),
                "ngo_name": item["ngo_name"],
            },
            merge=True,
        )
    print("Volunteer seed complete.")


if __name__ == "__main__":
    main()
