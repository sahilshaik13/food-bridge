from fastapi import APIRouter, HTTPException, Depends
import re

from app.models import Donor, DonorCreate, DonorTelegramUpdate, Ngo, NgoCreate, VolunteerInviteCreate, VolunteerProfile
from app.services.demo_store import store
from app.services.auth_service import verify_firebase_token, get_current_user_role, set_custom_role_claim

router = APIRouter(tags=["entities"])


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def normalize_public_slug(raw: str) -> str:
    """Align URL segments like donor_barbeque_nation with slugify('Barbeque Nation') -> barbeque-nation."""
    s = raw.strip().lower()
    if s.startswith("donor_"):
        s = s[6:]
    return s.replace("_", "-")


def donor_matches_public_slug(donor: Donor, id_or_slug: str) -> bool:
    name_slug = slugify(donor.name)
    path_norm = normalize_public_slug(id_or_slug)
    if donor.id == id_or_slug:
        return True
    if donor.id.lower() == id_or_slug.strip().lower():
        return True
    if name_slug == id_or_slug.strip().lower():
        return True
    if name_slug == path_norm:
        return True
    if donor.id.lower().replace("_", "-") == path_norm:
        return True
    return False


@router.get("/donors", response_model=list[Donor])
def list_donors() -> list[Donor]:
    return list(store.donors.values())


@router.post("/donors", response_model=Donor)
def register_donor(payload: DonorCreate) -> Donor:
    try:
        return store.create_donor(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/donors/{donor_id}/telegram", response_model=Donor)
def update_donor_telegram(donor_id: str, payload: DonorTelegramUpdate) -> Donor:
    if donor_id not in store.donors:
        raise HTTPException(status_code=404, detail="Donor not found")
    return store.update_donor_telegram(donor_id, payload)


@router.get("/ngos", response_model=list[Ngo])
def list_ngos() -> list[Ngo]:
    return list(store.ngos.values())


@router.post("/ngos", response_model=Ngo)
def register_ngo(payload: NgoCreate) -> Ngo:
    try:
        return store.create_ngo(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/volunteers/invite", response_model=VolunteerProfile)
def invite_volunteer(payload: VolunteerInviteCreate, decoded_token: dict = Depends(verify_firebase_token)) -> VolunteerProfile:
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid) if uid else None
    if role is None or role.value != "ngo_coordinator":
        raise HTTPException(status_code=403, detail="Only NGO coordinator can invite volunteers")
    if user and user.entity_id and user.entity_id != payload.ngo_id:
        raise HTTPException(status_code=403, detail="Cannot invite volunteers for another NGO")
    try:
        return store.invite_volunteer(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/volunteers", response_model=list[VolunteerProfile])
def list_volunteers(ngo_id: str | None = None, status: str | None = None) -> list[VolunteerProfile]:
    volunteers = list(store.volunteers.values())
    if ngo_id:
        volunteers = [volunteer for volunteer in volunteers if volunteer.ngo_id == ngo_id]
    if status:
        volunteers = [volunteer for volunteer in volunteers if volunteer.status == status]
    return volunteers


@router.get("/volunteers/invite/{token}")
def get_volunteer_invite(token: str):
    invite = store.get_volunteer_invite(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.used:
        raise HTTPException(status_code=409, detail="Invite already used")
    from datetime import datetime, timezone
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Invite expired")
    return {
        "token": invite.token,
        "ngo_id": invite.ngo_id,
        "ngo_name": invite.ngo_name,
        "volunteer_id": invite.volunteer_id,
        "name": invite.name,
        "email": invite.email,
        "phone": invite.phone,
        "expires_at": invite.expires_at,
    }


@router.post("/volunteers/register")
def register_volunteer_from_invite(
    body: dict,
    decoded_token: dict = Depends(verify_firebase_token),
):
    token = body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Missing invite token")
    uid = decoded_token.get("uid")
    email = (decoded_token.get("email") or "").lower()
    if not uid or not email:
        raise HTTPException(status_code=401, detail="Invalid auth context")
    try:
        volunteer = store.activate_volunteer_from_invite(token, uid, email)
        return {
            "success": True,
            "volunteer_id": volunteer.id,
            "status": volunteer.status,
            "message": "Registration submitted. Await NGO coordinator approval.",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/volunteers/{volunteer_id}/approve")
def approve_volunteer(
    volunteer_id: str,
    decoded_token: dict = Depends(verify_firebase_token),
):
    uid = decoded_token.get("uid")
    role = get_current_user_role(decoded_token)
    user = store.users.get(uid) if uid else None
    if role is None or role.value != "ngo_coordinator":
        raise HTTPException(status_code=403, detail="Only NGO coordinator can approve volunteers")
    if not user or not user.entity_id:
        raise HTTPException(status_code=403, detail="Missing NGO profile mapping")
    try:
        volunteer = store.set_volunteer_approval(volunteer_id, user.entity_id, approved=True)
        if volunteer.registered_uid and volunteer.registered_uid in store.users:
            profile = store.users[volunteer.registered_uid]
            profile.status = "active"
            profile.entity_id = volunteer.ngo_id
            store.users[volunteer.registered_uid] = profile
            store._write_doc("users", volunteer.registered_uid, profile)
            set_custom_role_claim(volunteer.registered_uid, "ngo_volunteer")
        return {"success": True, "volunteer_id": volunteer.id, "status": volunteer.status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/volunteers/{volunteer_id}/reject")
def reject_volunteer(
    volunteer_id: str,
    decoded_token: dict = Depends(verify_firebase_token),
):
    uid = decoded_token.get("uid")
    role = get_current_user_role(decoded_token)
    user = store.users.get(uid) if uid else None
    if role is None or role.value != "ngo_coordinator":
        raise HTTPException(status_code=403, detail="Only NGO coordinator can reject volunteers")
    if not user or not user.entity_id:
        raise HTTPException(status_code=403, detail="Missing NGO profile mapping")
    try:
        volunteer = store.set_volunteer_approval(volunteer_id, user.entity_id, approved=False)
        if volunteer.registered_uid and volunteer.registered_uid in store.users:
            profile = store.users[volunteer.registered_uid]
            profile.status = "rejected"
            store.users[volunteer.registered_uid] = profile
            store._write_doc("users", volunteer.registered_uid, profile)
        return {"success": True, "volunteer_id": volunteer.id, "status": volunteer.status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/volunteers/{volunteer_id}/resend-invite", response_model=VolunteerProfile)
def resend_volunteer_invite(
    volunteer_id: str,
    decoded_token: dict = Depends(verify_firebase_token),
):
    uid = decoded_token.get("uid")
    role = get_current_user_role(decoded_token)
    user = store.users.get(uid) if uid else None
    if role is None or role.value != "ngo_coordinator":
        raise HTTPException(status_code=403, detail="Only NGO coordinator can resend invites")
    if not user or not user.entity_id:
        raise HTTPException(status_code=403, detail="Missing NGO profile mapping")
    try:
        return store.resend_volunteer_invite(volunteer_id, user.entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/volunteers/{volunteer_id}/revoke-invite", response_model=VolunteerProfile)
def revoke_volunteer_invite(
    volunteer_id: str,
    decoded_token: dict = Depends(verify_firebase_token),
):
    uid = decoded_token.get("uid")
    role = get_current_user_role(decoded_token)
    user = store.users.get(uid) if uid else None
    if role is None or role.value != "ngo_coordinator":
        raise HTTPException(status_code=403, detail="Only NGO coordinator can revoke invites")
    if not user or not user.entity_id:
        raise HTTPException(status_code=403, detail="Missing NGO profile mapping")
    try:
        return store.revoke_volunteer_invite(volunteer_id, user.entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/donors/{id_or_slug}", response_model=Donor)
def get_donor_by_slug_or_id(id_or_slug: str) -> Donor:
    for donor in store.donors.values():
        if donor_matches_public_slug(donor, id_or_slug):
            return donor
    raise HTTPException(status_code=404, detail="Donor not found")


@router.get("/ngos/{id_or_slug}", response_model=Ngo)
def get_ngo_by_slug_or_id(id_or_slug: str) -> Ngo:
    for ngo in store.ngos.values():
        if ngo.id == id_or_slug or slugify(ngo.name) == id_or_slug:
            return ngo
    raise HTTPException(status_code=404, detail="NGO not found")
