import logging

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.cloud_clients import initialize_firebase_app
from app.models import Role

security = HTTPBearer()
logger = logging.getLogger(__name__)
FIREBASE_CLOCK_SKEW_SECONDS = 10


def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """Verify the Firebase ID token and return the decoded claims."""
    app = initialize_firebase_app()
    if app is None:
        raise HTTPException(status_code=503, detail="Firebase not initialized")

    from firebase_admin import auth
    token = credentials.credentials
    try:
        decoded = auth.verify_id_token(token, clock_skew_seconds=FIREBASE_CLOCK_SKEW_SECONDS)
        return decoded
    except Exception as e:
        logger.exception("Firebase token verification failed")
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def verify_firebase_token_string(token: str) -> dict:
    """Verify a raw Firebase ID token string."""
    app = initialize_firebase_app()
    if app is None:
        raise HTTPException(status_code=503, detail="Firebase not initialized")

    from firebase_admin import auth
    try:
        decoded = auth.verify_id_token(token, clock_skew_seconds=FIREBASE_CLOCK_SKEW_SECONDS)
        return decoded
    except Exception as e:
        logger.exception("Firebase token string verification failed")
        raise HTTPException(status_code=401, detail=f"Invalid token string: {e}")


def get_current_user_role(decoded_token: dict) -> Role | None:
    """Extract the role from Firebase custom claims."""
    role_str = decoded_token.get("role")
    if not role_str:
        return None
    try:
        return Role(role_str)
    except ValueError:
        return None


def set_custom_role_claim(uid: str, role: str) -> None:
    """Set a Firebase custom claim for the given UID.

    This is called immediately after successful onboarding so the user's
    ID token will carry the role claim on next refresh.
    """
    app = initialize_firebase_app()
    if app is None:
        raise HTTPException(status_code=503, detail="Firebase not initialized")

    try:
        from firebase_admin import auth
        user_record = auth.get_user(uid)
        existing = user_record.custom_claims or {}
        auth.set_custom_user_claims(uid, {**existing, "role": role})
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to set role claim for UID {uid}: {e}",
        )


def require_role(required_role: str):
    """FastAPI dependency factory that verifies the user has the required role."""
    def _dependency(decoded_token: dict = Security(verify_firebase_token)) -> dict:
        role = get_current_user_role(decoded_token)
        if role is None or role.value != required_role:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {required_role}, found: {role}",
            )
        return decoded_token
    return _dependency


def require_any_role(*allowed_roles: str):
    """FastAPI dependency that accepts any of the specified roles."""
    def _dependency(decoded_token: dict = Security(verify_firebase_token)) -> dict:
        role = get_current_user_role(decoded_token)
        if role is None or role.value not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Allowed roles: {allowed_roles}",
            )
        return decoded_token
    return _dependency
