import os
import sys

# Setup environment to import FastAPI app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from firebase_admin import auth
from app.core.cloud_clients import initialize_firebase_app

# Initialize firebase app
initialize_firebase_app()

def cleanup():
    # Cleanup donor1-12
    for i in range(1, 13):
        email = f"donor{i}@foodbridge.dev"
        try:
            user = auth.get_user_by_email(email)
            auth.delete_user(user.uid)
            print(f"Deleted {email}")
        except Exception:
            pass
            
    # Cleanup ngo1-10
    for i in range(1, 11):
        email = f"ngo{i}@foodbridge.dev"
        try:
            user = auth.get_user_by_email(email)
            auth.delete_user(user.uid)
            print(f"Deleted {email}")
        except Exception:
            pass

if __name__ == "__main__":
    cleanup()
