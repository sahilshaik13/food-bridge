from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Dict, Any

from app.models import Donation, DonationCreate, DonationStatus, DonationStatusUpdate, UserProfile, VolunteerTaskStatus
from app.services.demo_store import coerce_legacy_donation_payload, store
from app.services.auth_service import verify_firebase_token, get_current_user_role, require_role
from app.services.escalation_service import escalation_service
from app.core.cloud_clients import get_firestore_client
from app.core.config import get_settings

router = APIRouter(prefix="/donations", tags=["donations"])


async def _donation_payload_and_image(request: Request) -> tuple[DonationCreate, bytes | None]:
    """
    Multipart: form field `payload` = JSON string (DonationCreate), optional/required `photo` file.
    JSON body: only allowed when REQUIRE_DONATION_PHOTO_FOR_HTTP=false (text-only Gemini path).
    """
    settings = get_settings()
    ct = request.headers.get("content-type") or ""
    if "multipart/form-data" in ct.lower():
        form = await request.form()
        raw = form.get("payload")
        if raw is None or not isinstance(raw, str):
            raise HTTPException(
                status_code=422,
                detail="Multipart body must include form field 'payload' (JSON string of DonationCreate fields).",
            )
        payload = DonationCreate.model_validate_json(raw)
        photo = form.get("photo")
        image_bytes: bytes | None = None
        if photo is not None and hasattr(photo, "read"):
            image_bytes = await photo.read()
        if settings.require_donation_photo_for_http:
            if not image_bytes or len(image_bytes) < 64:
                raise HTTPException(
                    status_code=422,
                    detail="Food photo is required: include a non-empty form field 'photo' (JPEG/PNG/WebP).",
                )
        return payload, image_bytes

    body = await request.json()
    payload = DonationCreate(**body)
    if settings.require_donation_photo_for_http:
        raise HTTPException(
            status_code=400,
            detail=(
                "Submit donations as multipart/form-data with 'payload' (JSON) and 'photo' (food image) "
                "so Gemini Vision can scan the meal. For JSON-only dev/testing, set REQUIRE_DONATION_PHOTO_FOR_HTTP=false."
            ),
        )
    return payload, None


def _has_completion_signal(item: Donation) -> bool:
    task_status = item.volunteer_task_status.value if item.volunteer_task_status else None
    return bool(
        item.completed_at
        or item.delivery_confirmed_at
        or task_status == "delivered_confirmed"
    )


def _normalize_effective_status(item: Donation) -> None:
    if item.status.value != "completed" and _has_completion_signal(item):
        item.status = item.status.__class__("completed")


@router.get(
    "",
    response_model=list[Donation],
    summary="List donations",
    description=(
        "Returns donations visible to the caller. Each item includes **Phase 2** `scan` metadata "
        "(`model_id`, `model_version`, `generated_at`, `fallback_used`), optional `accuracy`, and "
        "`scan_contract_version` (1 = legacy lineage, 2 = full model lineage on scan)."
    ),
)
def list_donations(decoded_token: dict = Depends(verify_firebase_token)) -> list[Donation]:
    escalation_service.process_due_escalations()
    uid = decoded_token.get("uid")
    role = get_current_user_role(decoded_token)
    user = store.users.get(uid)
    if uid and (not user or not user.entity_id):
        try:
            db = get_firestore_client()
            doc = db.collection("users").document(uid).get()
            if doc.exists:
                data = doc.to_dict() or {}
                data.setdefault("id", uid)
                user = UserProfile(**data)
                store.users[uid] = user
        except Exception:
            pass
    entity_id = user.entity_id if (user and user.entity_id) else uid

    donations = list(store.donations.values())
    for item in donations:
        _normalize_effective_status(item)
    if role is not None and role.value == "donor":
        donations = [item for item in donations if item.donor_id == entity_id]
    elif role is not None and role.value == "ngo_coordinator":
        # If account has not yet been linked to an NGO entity id,
        # do not leak unassigned/global donations.
        if not user or not user.entity_id:
            return []
        donations = [
            item
            for item in donations
            if entity_id in item.notified_ngo_ids or (item.assigned_ngo_id is not None and item.assigned_ngo_id == entity_id)
        ]
    elif role is not None and role.value == "ngo_volunteer":
        if not user or not user.entity_id:
            return []
        pickups_statuses = {"accepted", "assigned", "completed"}
        donations = [
            item
            for item in donations
            if (
                ((item.assigned_ngo_id is not None and item.assigned_ngo_id == entity_id) or entity_id in item.notified_ngo_ids)
                and (item.status.value in pickups_statuses or _has_completion_signal(item))
            )
        ]

    return sorted(donations, key=lambda item: item.created_at, reverse=True)


@router.post(
    "",
    response_model=Donation,
    summary="Create donation",
    description=(
        "Creates a donation; uses Gemini Vision when multipart includes `photo`. "
        "Send **multipart/form-data**: field `payload` = JSON string (`DonationCreate`), field `photo` = image bytes. "
        "When `REQUIRE_DONATION_PHOTO_FOR_HTTP` is false, accepts legacy JSON body without image (text-only scan)."
    ),
)
async def create_donation(request: Request, decoded_token: dict = Depends(verify_firebase_token)) -> Donation:
    payload, image_bytes = await _donation_payload_and_image(request)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    donor_id = payload.donor_id
    if user and user.entity_id:
        donor_id = user.entity_id

    payload = DonationCreate(**{**payload.model_dump(), "donor_id": donor_id})
    if payload.donor_id not in store.donors:
        raise HTTPException(status_code=404, detail="Unknown donor")
    return store.create_donation(payload, image_bytes=image_bytes)


@router.patch(
    "/{donation_id}/retry-scan",
    response_model=Donation,
    summary="Retry Gemini scan",
    description=(
        "Donor-only: second attempt after `pending_scan_retry`. "
        "Same multipart rules as POST /donations (payload + photo when photo requirement is enabled)."
    ),
)
async def retry_donation_scan_endpoint(
    donation_id: str,
    request: Request,
    decoded_token: dict = Depends(verify_firebase_token),
) -> Donation:
    payload, image_bytes = await _donation_payload_and_image(request)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    donor_id = payload.donor_id
    if user and user.entity_id:
        donor_id = user.entity_id
    payload = DonationCreate(**{**payload.model_dump(), "donor_id": donor_id})
    role = get_current_user_role(decoded_token)
    if role is None or role.value != "donor":
        raise HTTPException(status_code=403, detail="Only donors can retry scan")
    if donation_id not in store.donations:
        raise HTTPException(status_code=404, detail="Donation not found")
    if store.donations[donation_id].donor_id != donor_id:
        raise HTTPException(status_code=403, detail="Donor can only retry own donations")
    try:
        return store.retry_donation_scan(donation_id, payload, image_bytes=image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{donation_id}/admin/approve",
    response_model=Donation,
    summary="Super Admin: approve reviewed donation",
)
def admin_approve_reviewed_donation(
    donation_id: str,
    _claims: dict = Depends(require_role("super_admin")),
) -> Donation:
    try:
        return store.admin_resolve_scan_review(donation_id, approved=True)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{donation_id}/admin/reject",
    response_model=Donation,
    summary="Super Admin: reject reviewed donation",
)
def admin_reject_reviewed_donation(
    donation_id: str,
    _claims: dict = Depends(require_role("super_admin")),
) -> Donation:
    try:
        return store.admin_resolve_scan_review(donation_id, approved=False)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/{donation_id}",
    response_model=Donation,
    summary="Get donation by id",
    description="Full donation record including `scan`, optional `accuracy`, and `scan_contract_version`.",
)
def get_donation(donation_id: str) -> Donation:
    escalation_service.process_due_escalations()
    if donation_id not in store.donations:
        raise HTTPException(status_code=404, detail="Donation not found")
    donation = store.donations[donation_id]
    _normalize_effective_status(donation)
    return donation


@router.patch(
    "/{donation_id}/status",
    response_model=Donation,
    summary="Update donation status",
    description="Workflow transitions; returned `Donation` retains Phase 2 `scan` / `accuracy` / `scan_contract_version` fields.",
)
def update_status(
    donation_id: str,
    payload: DonationStatusUpdate,
    decoded_token: dict = Depends(verify_firebase_token),
) -> Donation:
    try:
        db = get_firestore_client()
        doc = db.collection("donations").document(donation_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            if data:
                from app.models import MatchScore
                if not data.get("id"):
                    data["id"] = donation_id
                data = coerce_legacy_donation_payload(data)
                data["ngo_queue"] = [MatchScore(**q) for q in data.get("ngo_queue", [])]
                latest = Donation(**data)
                store.donations[donation_id] = latest
    except Exception:
        pass
    if donation_id not in store.donations:
        raise HTTPException(status_code=404, detail="Donation not found")
    uid = decoded_token.get("uid")
    role = get_current_user_role(decoded_token)
    user = store.users.get(uid)
    donation = store.donations[donation_id]

    if role is not None and role.value == "donor":
        donor_entity = user.entity_id if user and user.entity_id else uid
        if donation.donor_id != donor_entity:
            raise HTTPException(status_code=403, detail="Donor can only update own donations")
        if payload.status != DonationStatus.declined:
            raise HTTPException(status_code=403, detail="Donor can only cancel accepted/assigned pickups")
        if donation.status not in {DonationStatus.accepted, DonationStatus.assigned}:
            raise HTTPException(status_code=409, detail="Donation is not cancelable in current state")

    if role is not None and role.value == "ngo_coordinator":
        ngo_entity = user.entity_id if user and user.entity_id else None
        if payload.status in {DonationStatus.declined, DonationStatus.completed}:
            if not ngo_entity or donation.assigned_ngo_id != ngo_entity:
                raise HTTPException(status_code=403, detail="Only assigned NGO coordinator can perform this action")
        if payload.status == DonationStatus.accepted and payload.ngo_id and payload.ngo_id != ngo_entity:
            raise HTTPException(status_code=403, detail="Cannot accept for another NGO")
        if payload.status == DonationStatus.accepted:
            effective_ngo = payload.ngo_id or ngo_entity
            if not effective_ngo:
                raise HTTPException(status_code=403, detail="Missing NGO profile mapping")
            if effective_ngo not in donation.notified_ngo_ids:
                raise HTTPException(status_code=403, detail="NGO can accept only if notified for this donation")
        if payload.status == DonationStatus.completed and payload.volunteer_task_status != VolunteerTaskStatus.delivered_confirmed:
            raise HTTPException(status_code=409, detail="NGO can complete only after delivered confirmation")
    if role is not None and role.value == "ngo_coordinator" and payload.volunteer_task_status:
        allowed = {"delivered_confirmed"}
        if payload.volunteer_task_status.value not in allowed:
            raise HTTPException(status_code=403, detail="Only volunteer can set this task state")
        if not user or user.entity_id != donation.assigned_ngo_id:
            raise HTTPException(status_code=403, detail="Only assigned NGO coordinator can confirm delivery")

    if role is not None and role.value == "ngo_volunteer" and payload.volunteer_task_status:
        if not user or not user.entity_id:
            raise HTTPException(status_code=403, detail="Volunteer profile not linked")
        if donation.assigned_ngo_id != user.entity_id:
            raise HTTPException(status_code=403, detail="Volunteer can only update assigned NGO pickups")
        volunteer_allowed = {
            "heading_to_pickup",
            "pickup_rejected",
            "reached_pickup",
            "pickup_successful",
            "enroute_to_ngo",
            "delivered_pending_confirmation",
        }
        if payload.volunteer_task_status.value not in volunteer_allowed:
            raise HTTPException(status_code=403, detail="Volunteer transition not allowed")
        current = donation.volunteer_task_status.value if donation.volunteer_task_status else "assigned"
        expected_prev = {
            "heading_to_pickup": {"assigned"},
            "pickup_rejected": {"assigned", "heading_to_pickup"},
            "reached_pickup": {"heading_to_pickup"},
            "pickup_successful": {"reached_pickup"},
            "enroute_to_ngo": {"pickup_successful"},
            "delivered_pending_confirmation": {"enroute_to_ngo"},
        }
        if current not in expected_prev.get(payload.volunteer_task_status.value, {current}):
            raise HTTPException(
                status_code=409,
                detail=f"Invalid transition: {current} -> {payload.volunteer_task_status.value}",
            )

    if role is not None and role.value == "ngo_volunteer":
        if payload.status not in {DonationStatus.accepted, DonationStatus.assigned, DonationStatus.declined}:
            raise HTTPException(status_code=403, detail="Volunteer cannot directly set this donation status")
        payload = DonationStatusUpdate(
            **{
                **payload.model_dump(),
                "volunteer_uid": payload.volunteer_uid or uid,
            }
        )
    return store.update_donation_status(donation_id, payload)


@router.get("/{donation_id}/broadcasted-ngos")
def get_broadcasted_ngos(donation_id: str) -> List[Dict[str, Any]]:
    if donation_id not in store.donations:
        raise HTTPException(status_code=404, detail="Donation not found")
    
    donation = store.donations[donation_id]
    broadcasted = []
    
    for ngo_id in donation.notified_ngo_ids:
        ngo = store.ngos.get(ngo_id)
        if ngo:
            dimmed = donation.assigned_ngo_id is not None and donation.assigned_ngo_id != ngo.id
            broadcasted.append({
                "id": ngo.id,
                "name": ngo.name,
                "area": ngo.area,
                "location": ngo.location,
                "notified": True,
                "dimmed": dimmed,
                "wave": donation.broadcast_wave or donation.escalation_level,
            })
    
    return broadcasted
