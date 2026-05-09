from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.services.auth_service import verify_firebase_token, get_current_user_role
from app.models import Role

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Dependency that returns the decoded Firebase token."""
    return verify_firebase_token(credentials)


async def get_current_role(
    decoded_token: dict = Depends(get_current_user),
) -> Role:
    """Dependency that returns the user's Role enum."""
    role = get_current_user_role(decoded_token)
    if role is None:
        raise HTTPException(status_code=403, detail="No role assigned to user")
    return role


def require_role(required_role: Role):
    """Dependency factory that enforces a specific role."""
    async def checker(role: Role = Depends(get_current_role)) -> Role:
        if role != required_role:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {required_role.value}",
            )
        return role
    return checker


def require_any_role(*allowed_roles: Role):
    """Dependency that accepts any of the specified roles."""
    async def checker(role: Role = Depends(get_current_role)) -> Role:
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Allowed roles: {[r.value for r in allowed_roles]}",
            )
        return role
    return checker


def require_donor():
    return require_role(Role.donor)


def require_ngo_coordinator():
    return require_role(Role.ngo_coordinator)


def require_ngo_volunteer():
    return require_role(Role.ngo_volunteer)


def require_super_admin():
    return require_role(Role.super_admin)


def require_municipal_admin():
    return require_role(Role.municipal_admin)
