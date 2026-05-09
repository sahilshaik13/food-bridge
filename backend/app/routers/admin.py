from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.models import UserProfile, UserVerifyUpdate
from app.services.demo_store import store
from app.services.log_service import rotate_expired_logs

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/cloud-config")
def cloud_config() -> dict:
    settings = get_settings()
    return {
        "firebase_project_id": settings.firebase_project_id,
        "google_cloud_project": settings.google_cloud_project,
        "gcp_location": settings.gcp_location,
        "firebase_storage_bucket": settings.firebase_storage_bucket,
    }


@router.get("/users", response_model=list[UserProfile])
def list_users(status: str | None = None) -> list[UserProfile]:
    users = list(store.users.values())
    if status:
        users = [user for user in users if user.status == status]
    return sorted(users, key=lambda user: user.created_at, reverse=True)


@router.patch("/users/{user_id}/verify", response_model=UserProfile)
def verify_user(user_id: str, payload: UserVerifyUpdate) -> UserProfile:
    if user_id not in store.users:
        raise HTTPException(status_code=404, detail="User not found")
    return store.verify_user(user_id, payload)


@router.post("/logs/rotate")
def rotate_logs() -> dict:
    """
    Moves app logs older than 7 days into archive and
    permanently purges archive logs older than 30 days.
    """
    return rotate_expired_logs()
