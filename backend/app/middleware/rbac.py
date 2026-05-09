from fastapi import Depends, HTTPException, Request
from app.services.auth_service import verify_firebase_token, get_current_user_role
from app.models import Role

ALLOWED_ROUTES = {
    "/health": None,
    "/docs": None,
    "/openapi.json": None,
    "/auth/verify": None,
    "/telegram/webhook": None,
    "/telegram/link-donor": None,
}

ADMIN_ROUTES = {"/admin", "/admin/users"}
NGO_ROUTES = {"/ngo", "/ngo/emergency", "/ngo/profile", "/volunteer"}
DONOR_ROUTES = {"/donor", "/donor/donate", "/donor/reports"}
MUNICIPAL_ROUTES = {"/municipal"}


def route_allowed_for_role(route: str, role: Role | None) -> bool:
    if role is None:
        return False

    if route.startswith("/admin"):
        return role == Role.super_admin
    if route.startswith("/donor"):
        return role == Role.donor
    if route.startswith("/ngo") or route == "/volunteer":
        return role in {Role.ngo_coordinator, Role.ngo_volunteer}
    if route == "/municipal":
        return role in {Role.municipal_admin, Role.super_admin}

    return True


async def check_rbac(request: Request) -> dict | None:
    path = request.url.path

    if path in ALLOWED_ROUTES:
        return None

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    try:
        token = auth_header[7:]
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
        from fastapi import Depends
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        decoded = verify_firebase_token(credentials)
        role = get_current_user_role(decoded)

        if not route_allowed_for_role(path, role):
            raise HTTPException(
                status_code=403,
                detail=f"Role {role.value if role else 'none'} not allowed on {path}",
            )

        return decoded
    except HTTPException:
        raise
    except Exception:
        return None
