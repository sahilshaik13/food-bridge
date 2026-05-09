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


DONORS = [
    {
        "id": "donor_barbeque_nation",
        "email": "barbeque_nation@foodbridge.dev",
        "name": "Barbeque Nation - Forum Sujana Mall",
        "fssai_license": "13618013000425",
        "phone": "+91 98490 11001",
        "contact_name": "Rajesh Menon",
        "area": "Kukatpally, KPHB",
        "avg_surplus_kg": "55 kg/day",
        "address": "THE FORUM SUJANA MALL, Restaurant No.2, Sy No.1009, 4th Floor, Kukatpally, KPHB VI, Hyderabad, Telangana 500072",
        "lat": 17.493600,
        "lng": 78.399800,
    },
    # Shah Ghouse is intentionally excluded from Firestore seeding (pre-plant).
    {
        "id": "donor_royal_bawarchi",
        "email": "royal_bawarchi@foodbridge.dev",
        "name": "Royal Bawarchi",
        "fssai_license": "13623013000591",
        "phone": "+91 98490 11003",
        "contact_name": "Mohammed Farooq",
        "area": "Hafeezpet, New Hafeezpet",
        "avg_surplus_kg": "42 kg/day",
        "address": "307/A, Marthanda Nagar, New Hafeezpet, Serlingampally, Hyderabad, Telangana 500049",
        "lat": 17.483300,
        "lng": 78.361400,
    },
    {
        "id": "donor_southern_spice",
        "email": "southern_spice@foodbridge.dev",
        "name": "Southern Spice",
        "fssai_license": "13625013000760",
        "phone": "+91 98490 11004",
        "contact_name": "Prasad Venkataraman",
        "area": "Madhapur, Serilingampally",
        "avg_surplus_kg": "38 kg/day",
        "address": "HNO 1-98/5/431A & 1-98/5/431, Ground, First and Second Floors, Plot No.31 & 32, Sy No.77, Madhapur, Serilingampally, Hyderabad, Telangana 500081",
        "lat": 17.448500,
        "lng": 78.390800,
    },
    {
        "id": "donor_vibrant_living",
        "email": "vibrant_living@foodbridge.dev",
        "name": "Vibrant Living Private Limited",
        "fssai_license": "13621999000076",
        "phone": "+91 98490 11005",
        "contact_name": "Anand Krishnamurthy",
        "area": "Raidurg, Prashanth Hills",
        "avg_surplus_kg": "65 kg/day",
        "address": "Plot No.107, Prashanth Hills, Raidurg Nav Khalsa, Hyderabad, Serlingampally, Telangana 500104",
        "lat": 17.423000,
        "lng": 78.334500,
    },
    {
        "id": "donor_peshawar",
        "email": "peshawar@foodbridge.dev",
        "name": "Peshawar Restaurant",
        "fssai_license": "13625014000164",
        "phone": "+91 98490 11006",
        "contact_name": "Imtiaz Khan",
        "area": "Begumpet, SP Road",
        "avg_surplus_kg": "28 kg/day",
        "address": "1-8-303/3.2, SP Road, Secunderabad, Begumpet Circle No.30, Hyderabad, Telangana 500003",
        "lat": 17.443800,
        "lng": 78.463400,
    },
    {
        "id": "donor_bamboo_tree",
        "email": "bamboo_tree@foodbridge.dev",
        "name": "Mandilious - Bamboo Tree Hotels",
        "fssai_license": "13623013000334",
        "phone": "+91 98490 11007",
        "contact_name": "Suresh Reddy",
        "area": "KPHB Colony, Kukatpally",
        "avg_surplus_kg": "35 kg/day",
        "address": "15-31-DL-46, Dharmareddy Colony, KPHB, Hyderabad, Kukatpally Circle No.24, Telangana 500085",
        "lat": 17.494700,
        "lng": 78.388000,
    },
    {
        "id": "donor_lebanese_bites",
        "email": "lebanese_bites@foodbridge.dev",
        "name": "Lebanese Bites",
        "fssai_license": "13623011001097",
        "phone": "+91 98490 11008",
        "contact_name": "Mir Qutub Ali",
        "area": "Lakadikapool, Khairatabad",
        "avg_surplus_kg": "18 kg/day",
        "address": "H No. 11-4-649/C, A.C. Guard, Lakadikapool, Hyderabad, Khairatabad Circle No.17, Telangana 500004",
        "lat": 17.412700,
        "lng": 78.454500,
    },
    {
        "id": "donor_mehfil",
        "email": "mehfil@foodbridge.dev",
        "name": "Mehfil Restaurant",
        "fssai_license": "13620013000550",
        "phone": "+91 98490 11009",
        "contact_name": "Mohammed Mubeen Pasha",
        "area": "Shaikpet, H.S. Darga",
        "avg_surplus_kg": "25 kg/day",
        "address": "5-123/1/A, H.S. Darga, Shaikpet, Serlingampally Circle No.20, Hyderabad, Telangana 500081",
        "lat": 17.401200,
        "lng": 78.415600,
    },
    {
        "id": "donor_udupi_grand",
        "email": "udupi_grand@foodbridge.dev",
        "name": "Sri Udupi Grand Pure-Veg Family Restaurant",
        "fssai_license": "13621011000901",
        "phone": "+91 98490 11010",
        "contact_name": "Venkat Subramaniam",
        "area": "Srinagar Colony, Yousufguda",
        "avg_surplus_kg": "16 kg/day",
        "address": "H.NO. 8-3-1027/A/1, Srinagar Colony, Hyderabad, Yousufguda Circle No.19, Telangana 500073",
        "lat": 17.437600,
        "lng": 78.425800,
    },
]

NGOS = [
    {
        "id": "ngo_robin_hood",
        "email": "robin_hood@foodbridge.dev",
        "name": "Robin Hood Army - Hyderabad Chapter",
        "ngo_darpan_id": "TS/2014/0081234",
        "beneficiary_count": 180,
        "coordinator_name": "Arjun Reddy",
        "coordinator_phone": "+91 98490 21001",
        "focus": "General food rescue - surplus redistribution to homeless and daily wage workers",
        "area": "Kondapur / Madhapur",
        "address": "Plot No. 45, Jayabheri Silicon County, Kondapur, Hyderabad, Telangana 500084",
        "lat": 17.4647,
        "lng": 78.3753,
    },
    {
        "id": "ngo_akshaya_patra",
        "email": "akshaya_patra@foodbridge.dev",
        "name": "Akshaya Patra Foundation - Hyderabad",
        "ngo_darpan_id": "TS/2005/0014567",
        "beneficiary_count": 800,
        "coordinator_name": "Deepa Narayan",
        "coordinator_phone": "+91 98490 21002",
        "focus": "Children midday meals, school nutrition programmes, destitute feeding",
        "area": "Kokapet / Narsingi",
        "address": "Survey No. 212, Narsingi, Kokapet Road, Hyderabad, Telangana 500075",
        "lat": 17.3988,
        "lng": 78.3409,
    },
    {
        "id": "ngo_ramakrishna_math",
        "email": "ramakrishna_math@foodbridge.dev",
        "name": "Ramakrishna Math - Hyderabad",
        "ngo_darpan_id": "TS/1962/0003891",
        "beneficiary_count": 130,
        "coordinator_name": "Swami Prakashananda",
        "coordinator_phone": "+91 98490 21003",
        "focus": "Homeless shelter feeding, destitute care, daily anna daan programme",
        "area": "Domalguda / Himayatnagar",
        "address": "Ramakrishna Math Road, Domalguda, Himayatnagar, Hyderabad, Telangana 500029",
        "lat": 17.4117,
        "lng": 78.4815,
    },
    {
        "id": "ngo_smile_foundation",
        "email": "smile_foundation@foodbridge.dev",
        "name": "Smile Foundation - Telangana Chapter",
        "ngo_darpan_id": "TS/2002/0027654",
        "beneficiary_count": 95,
        "coordinator_name": "Kavitha Sharma",
        "coordinator_phone": "+91 98490 21004",
        "focus": "Child welfare, street children nutrition, education nutrition support",
        "area": "Tarnaka / Secunderabad",
        "address": "H.No. 4-5-678, Tarnaka, Secunderabad, Hyderabad, Telangana 500017",
        "lat": 17.4310,
        "lng": 78.5368,
    },
    {
        "id": "ngo_safa_baitul_maal",
        "email": "safa_baitul_maal@foodbridge.dev",
        "name": "Safa Baitul Maal Trust",
        "ngo_darpan_id": "TS/2009/0056123",
        "beneficiary_count": 250,
        "coordinator_name": "Mohammed Rashid",
        "coordinator_phone": "+91 98490 21005",
        "focus": "Community welfare, iftar food distribution, old city destitute feeding",
        "area": "Old Malakpet",
        "address": "H.No. 7-2-167, Old Malakpet, Hyderabad, Telangana 500036",
        "lat": 17.3844,
        "lng": 78.5049,
    },
    {
        "id": "ngo_terminate_hunger",
        "email": "terminate_hunger@foodbridge.dev",
        "name": "Terminate Hunger Welfare Organisation",
        "ngo_darpan_id": "TS/2016/0094321",
        "beneficiary_count": 140,
        "coordinator_name": "Priya Bhaskar",
        "coordinator_phone": "+91 98490 21006",
        "focus": "Urban poor feeding, daily meal drives, construction worker communities",
        "area": "Old Malakpet",
        "address": "H.No. 6-3-234/1, Malakpet Colony, Old Malakpet, Hyderabad, Telangana 500036",
        "lat": 17.3833,
        "lng": 78.5027,
    },
    {
        "id": "ngo_helpage_india",
        "email": "helpage_india@foodbridge.dev",
        "name": "HelpAge India - Hyderabad Regional Office",
        "ngo_darpan_id": "TS/1978/0008765",
        "beneficiary_count": 70,
        "coordinator_name": "Sunitha Rao",
        "coordinator_phone": "+91 98490 21007",
        "focus": "Elderly care, old age home nutrition support, homebound senior feeding",
        "area": "Begumpet",
        "address": "6-3-347/21, Dwarakapuri Colony, Punjagutta, Begumpet, Hyderabad, Telangana 500082",
        "lat": 17.4399,
        "lng": 78.4628,
    },
    {
        "id": "ngo_cry",
        "email": "cry@foodbridge.dev",
        "name": "Child Rights and You - Hyderabad Chapter",
        "ngo_darpan_id": "TS/1979/0009012",
        "beneficiary_count": 90,
        "coordinator_name": "Lakshmi Narasimha",
        "coordinator_phone": "+91 98490 21008",
        "focus": "Children rights, nutrition for at-risk children, school dropout communities",
        "area": "Banjara Hills, Road No. 10",
        "address": "Plot No. 34, Road No. 10, Banjara Hills, Hyderabad, Telangana 500034",
        "lat": 17.4156,
        "lng": 78.4397,
    },
    {
        "id": "ngo_no_food_waste",
        "email": "no_food_waste@foodbridge.dev",
        "name": "No Food Waste Foundation - Hyderabad",
        "ngo_darpan_id": "TS/2013/0071890",
        "beneficiary_count": 155,
        "coordinator_name": "Harish Babu",
        "coordinator_phone": "+91 98490 21009",
        "focus": "Food rescue, event surplus collection, redistribution to slum communities",
        "area": "Jubilee Hills",
        "address": "H.No. 8-2-120/5, Road No. 2, Jubilee Hills, Hyderabad, Telangana 500033",
        "lat": 17.4325,
        "lng": 78.4072,
    },
    {
        "id": "ngo_aasra",
        "email": "aasra@foodbridge.dev",
        "name": "Aasra Foundation Hyderabad",
        "ngo_darpan_id": "TS/2011/0063457",
        "beneficiary_count": 175,
        "coordinator_name": "Dr. Vijaya Lakshmi",
        "coordinator_phone": "+91 98490 21010",
        "focus": "Mental health crisis support, shelter home feeding, rehabilitation centre nutrition",
        "area": "Secunderabad",
        "address": "H.No. 15-8-468, East Marredpally, Secunderabad, Hyderabad, Telangana 500026",
        "lat": 17.4399,
        "lng": 78.5011,
    },
]

ADMINS = [
    {"email": "superadmin@foodbridge.dev", "role": "super_admin", "display_name": "Super Admin"},
    {"email": "municipal@foodbridge.dev", "role": "municipal_admin", "display_name": "Municipal Admin"},
]


def get_uid_by_email(email: str) -> str:
    user = auth.get_user_by_email(email)
    return user.uid


def upsert_user_doc(db, uid: str, role: str, display_name: str, email: str, entity_id: str | None = None, status: str = "verified"):
    payload = {
        "id": uid,
        "role": role,
        "display_name": display_name,
        "email": email,
        "status": status,
        "created_at": now_utc(),
    }
    if entity_id:
        payload["entity_id"] = entity_id
    db.collection("users").document(uid).set(payload, merge=True)


def main():
    # Use repo root env file for credential paths.
    env_path = ROOT / ".env.local"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    initialize_firebase_app()
    db = get_firestore_client()

    print("Linking admin users...")
    for item in ADMINS:
        uid = get_uid_by_email(item["email"])
        upsert_user_doc(db, uid, item["role"], item["display_name"], item["email"], None, "active")
        auth.set_custom_user_claims(uid, {"role": item["role"]})
        print(f"  linked admin: {item['email']} -> {uid}")

    print("Linking donor users and profiles...")
    for item in DONORS:
        uid = get_uid_by_email(item["email"])
        donor_payload = {
            "id": item["id"],
            "name": item["name"],
            "area": item["area"],
            "type": "Restaurant",
            "fssai_license": item["fssai_license"],
            "contact_name": item["contact_name"],
            "phone": item["phone"],
            "email": item["email"],
            "avg_surplus_kg": item["avg_surplus_kg"],
            "monthly_meals": 0,
            "verification_status": "verified",
            "location": {
                "area": item["area"],
                "address": item["address"],
                "lat": item["lat"],
                "lng": item["lng"],
            },
            "created_at": now_utc(),
        }
        db.collection("donors").document(item["id"]).set(donor_payload, merge=True)
        upsert_user_doc(db, uid, "donor", item["name"], item["email"], item["id"], "verified")
        auth.set_custom_user_claims(uid, {"role": "donor", "entity_id": item["id"]})
        print(f"  linked donor: {item['email']} -> {uid} -> {item['id']}")

    # Keep Shah Ghouse pre-plant account in Auth but unlinked in Firestore.
    try:
        preplant_uid = get_uid_by_email("shah_ghouse@foodbridge.dev")
        auth.set_custom_user_claims(preplant_uid, {"role": "donor"})
        print(f"  pre-plant donor kept unlinked: shah_ghouse@foodbridge.dev -> {preplant_uid}")
    except Exception as exc:
        print(f"  pre-plant donor not found in auth, skipped: {exc}")

    print("Linking NGO users and profiles...")
    for item in NGOS:
        uid = get_uid_by_email(item["email"])
        ngo_payload = {
            "id": item["id"],
            "name": item["name"],
            "area": item["area"],
            "focus": item["focus"],
            "ngo_darpan_id": item["ngo_darpan_id"],
            "beneficiary_count": item["beneficiary_count"],
            "food_preferences": ["rice", "dal", "biryani", "veg meals"],
            "dietary_restrictions": [],
            "location": {
                "area": item["area"],
                "address": item["address"],
                "lat": item["lat"],
                "lng": item["lng"],
            },
            "verification_status": "verified",
            "meal_time_schedule": "Breakfast, Lunch, Dinner",
            "coordinator_name": item["coordinator_name"],
            "coordinator_phone": item["coordinator_phone"],
        }
        db.collection("ngos").document(item["id"]).set(ngo_payload, merge=True)
        upsert_user_doc(db, uid, "ngo_coordinator", item["name"], item["email"], item["id"], "verified")
        auth.set_custom_user_claims(uid, {"role": "ngo_coordinator", "entity_id": item["id"]})
        print(f"  linked ngo: {item['email']} -> {uid} -> {item['id']}")

    print("Done. Firebase Auth identities are now linked with Firestore profiles.")


if __name__ == "__main__":
    main()
