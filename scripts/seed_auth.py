import os
import sys

# Setup environment to import FastAPI app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from firebase_admin import auth
from app.core.cloud_clients import initialize_firebase_app

# Initialize firebase app
initialize_firebase_app()

users_to_seed = [
    # Admins
    {"email": "superadmin@foodbridge.dev", "password": "Password123", "role": "super_admin", "name": "Super Admin"},
    {"email": "municipal@foodbridge.dev", "password": "Password123", "role": "municipal_admin", "name": "Municipal Admin"},
    
    # Donors (Explicit mapping)
    {"email": "barbeque_nation@foodbridge.dev", "password": "Password123", "role": "donor", "name": "M/S. BARBEQUE NATION HOSPITALITY LTD", "entity_id": "donor_barbeque_nation"},
    {"email": "shah_ghouse@foodbridge.dev", "password": "Password123", "role": "donor", "name": "M/S. SHAH GHOUSE HOTEL AND RESTAURANT", "entity_id": "donor_shah_ghouse"},
    {"email": "royal_bawarchi@foodbridge.dev", "password": "Password123", "role": "donor", "name": "M/S ROYAL BAWARCHI", "entity_id": "donor_royal_bawarchi"},
    {"email": "southern_spice@foodbridge.dev", "password": "Password123", "role": "donor", "name": "SOUTHERN SPICE (MUNNAUNITED HOSPITALITY)", "entity_id": "donor_southern_spice"},
    {"email": "vibrant_living@foodbridge.dev", "password": "Password123", "role": "donor", "name": "VIBRANT LIVING PRIVATE LIMITED", "entity_id": "donor_vibrant_living"},
    {"email": "peshawar@foodbridge.dev", "password": "Password123", "role": "donor", "name": "M/s. PESHAWAR RESTAURANT", "entity_id": "donor_peshawar"},
    {"email": "bamboo_tree@foodbridge.dev", "password": "Password123", "role": "donor", "name": "M/s. MANDILIOUS (BAMBOO TREE HOTELS)", "entity_id": "donor_bamboo_tree"},
    {"email": "lebanese_bites@foodbridge.dev", "password": "Password123", "role": "donor", "name": "MIR QUTUB ALI M/S. LEBANESE BITES", "entity_id": "donor_lebanese_bites"},
    {"email": "mehfil@foodbridge.dev", "password": "Password123", "role": "donor", "name": "MOHAMMED MUBEEN PASHA M/S. MEHFIL RESTAURANT", "entity_id": "donor_mehfil"},
    {"email": "udupi_grand@foodbridge.dev", "password": "Password123", "role": "donor", "name": "SRI UDUPI GRAND PURE-VEG FAMILY RESTAURANT", "entity_id": "donor_udupi_grand"},
    {"email": "tri_fusion@foodbridge.dev", "password": "Password123", "role": "donor", "name": "Tri Fusion", "entity_id": "donor_tri_fusion"},
    {"email": "lake_view_cafe@foodbridge.dev", "password": "Password123", "role": "donor", "name": "M/S Lake View Cafe", "entity_id": "donor_lake_view_cafe"},
    
    # NGOs (Explicit mapping)
    {"email": "robin_hood@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "Robin Hood Army Hyderabad", "entity_id": "ngo_robin_hood"},
    {"email": "akshaya_patra@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "Akshaya Patra Foundation", "entity_id": "ngo_akshaya_patra"},
    {"email": "ramakrishna_math@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "Ramakrishna Math Hyderabad", "entity_id": "ngo_ramakrishna_math"},
    {"email": "smile_foundation@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "Smile Foundation Telangana", "entity_id": "ngo_smile_foundation"},
    {"email": "safa_baitul_maal@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "Safa Baitul Maal Trust", "entity_id": "ngo_safa_baitul_maal"},
    {"email": "terminate_hunger@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "Terminate Hunger Welfare Org", "entity_id": "ngo_terminate_hunger"},
    {"email": "helpage_india@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "HelpAge India Hyderabad", "entity_id": "ngo_helpage_india"},
    {"email": "cry@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "CRY Hyderabad", "entity_id": "ngo_cry"},
    {"email": "no_food_waste@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "No Food Waste Hyderabad", "entity_id": "ngo_no_food_waste"},
    {"email": "aasra@foodbridge.dev", "password": "Password123", "role": "ngo_coordinator", "name": "Aasra Foundation", "entity_id": "ngo_aasra"},
]

print(f"Seeding {len(users_to_seed)} users...")

for user_data in users_to_seed:
    email = user_data["email"]
    password = user_data["password"]
    role = user_data["role"]
    
    try:
        user = auth.get_user_by_email(email)
        print(f"User {email} already exists. Updating...")
        auth.update_user(user.uid, password=password, display_name=user_data["name"])
        uid = user.uid
    except auth.UserNotFoundError:
        print(f"Creating user {email}...")
        user = auth.create_user(
            email=email,
            password=password,
            display_name=user_data["name"]
        )
        uid = user.uid

    # Set custom claim
    auth.set_custom_user_claims(uid, {"role": role, "entity_id": user_data.get("entity_id")})
    print(f"Set claims for {email} ({uid})")

print("Seeding complete.")
