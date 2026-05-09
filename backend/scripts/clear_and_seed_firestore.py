import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.core.config import get_settings
from app.core.cloud_clients import get_firestore_client
from app.data.seed import DONORS, NGOS
from app.services.demo_store import DemoStore


def clear_and_seed_firestore():
    settings = get_settings()
    print(f"Using Firebase project: {settings.firebase_project_id}")
    
    db = get_firestore_client()
    if not db:
        print("Could not get Firestore client")
        return

    print("Clearing existing data...")
    
    collections_to_clear = [
        "donors",
        "ngos",
        "users",
        "donations",
        "notifications",
        "messages",
        "emergency_requests",
        "emergency_pools_v2",
    ]
    for collection_name in collections_to_clear:
        print(f"  Clearing {collection_name}...")
        docs = db.collection(collection_name).stream()
        for doc in docs:
            doc.reference.delete()
    
    print("\nSeeding initial data...")
    
    store = DemoStore()
    
    print(f"Seeded {len(store.donors)} donors")
    print(f"Seeded {len(store.ngos)} NGOs")
    print(f"Seeded {len(store.users)} users")
    
    print("\nDone! Firestore has fresh seed data.")


if __name__ == "__main__":
    clear_and_seed_firestore()
