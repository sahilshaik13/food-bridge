import os
import sys

# Setup environment to import FastAPI app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from firebase_admin import auth
from app.core.cloud_clients import initialize_firebase_app

# Initialize firebase app
initialize_firebase_app()

def cleanup_all():
    # This will delete ALL users except admins
    users = auth.list_users().iterate_all()
    for user in users:
        if user.email and not (user.email.startswith("superadmin") or user.email.startswith("municipal")):
            try:
                auth.delete_user(user.uid)
                print(f"Deleted {user.email}")
            except Exception as e:
                print(f"Failed to delete {user.email}: {e}")

if __name__ == "__main__":
    cleanup_all()
