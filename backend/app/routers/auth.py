from fastapi import APIRouter, Depends, Security, HTTPException, Body
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
import requests

from app.models import AuthVerifyResponse, Role, DonorCreate, NgoCreate, UserProfile
from app.services.demo_store import store
from app.core.config import get_settings
from app.core.cloud_clients import get_firestore_client
from app.services.auth_service import (
    verify_firebase_token,
    get_current_user_role,
    set_custom_role_claim,
)

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer()

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
def login(body: LoginRequest):
    """Authenticate via Firebase REST API on the backend."""
    settings = get_settings()
    api_key = settings.firebase_api_key
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    
    payload = {
        "email": body.email,
        "password": body.password,
        "returnSecureToken": True
    }
    
    resp = requests.post(url, json=payload)
    if not resp.ok:
        error_data = resp.json()
        error_message = error_data.get("error", {}).get("message", "Authentication failed")
        raise HTTPException(status_code=401, detail=error_message)
    
    data = resp.json()
    id_token = data.get("idToken")
    
    # Now verify the token we just got to get the profile and redirect path
    # (We can just reuse the verify_auth logic here or call it internally)
    from app.services.auth_service import verify_firebase_token_string
    decoded_token = verify_firebase_token_string(id_token)
    
    # Get the verification response
    verify_resp = verify_auth_internal(decoded_token)
    
    return {
        "idToken": id_token,
        "refreshToken": data.get("refreshToken"),
        "expiresIn": data.get("expiresIn"),
        "role": verify_resp.role,
        "profile": verify_resp.profile,
        "redirect_to": verify_resp.redirect_to
    }

def verify_auth_internal(decoded_token: dict) -> AuthVerifyResponse:
    uid = decoded_token.get("uid")
    email = (decoded_token.get("email") or "").lower()
    role = get_current_user_role(decoded_token)
    user = None

    if uid:
        try:
            db = get_firestore_client()
            user_doc = db.collection("users").document(uid).get()
            if user_doc.exists:
                data = user_doc.to_dict() or {}
                data.setdefault("id", uid)
                user = UserProfile(**data)
                store.users[uid] = user
        except Exception:
            pass

    if uid and (not user or not user.entity_id):
        donor = next((item for item in store.donors.values() if email and (item.email or "").lower() == email), None)
        if donor:
            role = Role.donor
            user = UserProfile(id=uid, role=Role.donor, display_name=donor.name, status="verified", entity_id=donor.id, email=email)
            store.users[uid] = user
            store._write_doc("users", uid, user)
            set_custom_role_claim(uid, "donor")
        
        if not user:
            ngo = next((item for item in store.ngos.values() if email and (
                (getattr(item, 'coordinator_email', '') or '').lower() == email or 
                email in (item.name.lower() or "") or
                email in (item.coordinator_name.lower() if item.coordinator_name else "")
            )), None)
            if ngo:
                role = Role.ngo_coordinator
                user = UserProfile(id=uid, role=Role.ngo_coordinator, display_name=ngo.name, status="verified", entity_id=ngo.id, email=email)
                store.users[uid] = user
                store._write_doc("users", uid, user)
                set_custom_role_claim(uid, "ngo_coordinator")

        if not user:
            volunteer = next(
                (
                    item
                    for item in store.volunteers.values()
                    if email and (item.email or "").lower() == email
                ),
                None,
            )
            if volunteer:
                role = Role.ngo_volunteer
                status = "active" if volunteer.status == "active" else "pending"
                user = UserProfile(
                    id=uid,
                    role=Role.ngo_volunteer,
                    display_name=volunteer.name,
                    status=status,
                    entity_id=volunteer.ngo_id,
                    email=email,
                )
                store.users[uid] = user
                store._write_doc("users", uid, user)
                if volunteer.status == "active":
                    set_custom_role_claim(uid, "ngo_volunteer")

    user, profile, redirect_to = store.verify_auth(role, uid)
    if role is None: redirect_to = "/onboarding/donor"
    if role == Role.donor and not (user and user.entity_id): redirect_to = "/onboarding/donor"
    if role == Role.ngo_coordinator and not (user and user.entity_id): redirect_to = "/onboarding/ngo"
    if role == Role.ngo_volunteer and not (user and user.entity_id): redirect_to = "/volunteer/register"

    return AuthVerifyResponse(role=user.role if user else role, profile=user, redirect_to=redirect_to)

@router.post("/verify", response_model=AuthVerifyResponse)
def verify_auth(
    decoded_token: dict = Depends(verify_firebase_token),
) -> AuthVerifyResponse:
    return verify_auth_internal(decoded_token)


class DonorOnboardRequest(BaseModel):
    name: str
    area: str
    address: str
    lat: float = 17.3850
    lng: float = 78.4867
    type: str = "restaurant"
    fssai_license: str
    contact_name: str
    phone: str
    email: str
    avg_surplus_kg: float = 10.0
    gst_number: str | None = None


@router.post("/onboarding/donor")
def onboard_donor(
    body: DonorOnboardRequest,
    decoded_token: dict = Depends(verify_firebase_token),
):
    """Complete donor onboarding: create profile + set Firebase custom claim."""
    uid = decoded_token.get("uid")
    try:
        payload = DonorCreate(
            name=body.name,
            area=body.area,
            address=body.address,
            lat=body.lat,
            lng=body.lng,
            type=body.type,
            fssai_license=body.fssai_license,
            contact_name=body.contact_name,
            phone=body.phone,
            email=body.email,
            avg_surplus_kg=body.avg_surplus_kg,
        )
        donor = store.create_donor(payload)

        if uid and uid in store.users:
            store.users[uid].entity_id = donor.id
        elif uid:
            from app.models import UserProfile
            store.users[uid] = UserProfile(
                id=uid,
                role=Role.donor,
                display_name=donor.name,
                status="verified",
                entity_id=donor.id,
            )

        set_custom_role_claim(uid, "donor")

        return {"success": True, "donor_id": donor.id, "redirect_to": "/donor"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class NgoOnboardRequest(BaseModel):
    name: str
    area: str
    address: str
    lat: float = 17.3850
    lng: float = 78.4867
    focus: str = "hunger relief"
    ngo_darpan_id: str
    beneficiary_count: int
    food_preferences: list[str] = []
    dietary_restrictions: list[str] = []
    meal_time_schedule: str = "lunch"
    coordinator_name: str
    coordinator_phone: str
    aadhaar_document_url: str | None = None


@router.post("/onboarding/ngo")
def onboard_ngo(
    body: NgoOnboardRequest,
    decoded_token: dict = Depends(verify_firebase_token),
):
    """Complete NGO onboarding: create pending profile (no claim set until Admin approves)."""
    uid = decoded_token.get("uid")
    try:
        payload = NgoCreate(
            name=body.name,
            area=body.area,
            address=body.address,
            lat=body.lat,
            lng=body.lng,
            focus=body.focus,
            ngo_darpan_id=body.ngo_darpan_id,
            beneficiary_count=body.beneficiary_count,
            food_preferences=body.food_preferences,
            dietary_restrictions=body.dietary_restrictions,
            meal_time_schedule=body.meal_time_schedule,
            coordinator_name=body.coordinator_name,
            coordinator_phone=body.coordinator_phone,
            aadhaar_document_url=body.aadhaar_document_url,
        )
        ngo = store.create_ngo(payload)

        if uid:
            from app.models import UserProfile
            store.users[uid] = UserProfile(
                id=uid,
                role=Role.ngo_coordinator,
                display_name=ngo.name,
                status="pending",
                entity_id=ngo.id,
            )
            store._write_doc("users", uid, store.users[uid])

        return {
            "success": True,
            "ngo_id": ngo.id,
            "status": "pending",
            "message": "Application submitted. Under review — 24hr SLA.",
            "redirect_to": "/",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
