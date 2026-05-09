from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any

from app.models import Donation, DonationCreate, DonationStatus, DonationStatusUpdate, UserProfile, VolunteerTaskStatus
from app.services.demo_store import store
from app.services.auth_service import verify_firebase_token, get_current_user_role
from app.services.escalation_service import escalation_service
from app.core.cloud_clients import get_firestore_client

router = APIRouter(prefix="/donations", tags=["donations"])


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


@router.get("", response_model=list[Donation])
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


@router.post("", response_model=Donation)
def create_donation(payload: DonationCreate, decoded_token: dict = Depends(verify_firebase_token)) -> Donation:
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    donor_id = payload.donor_id
    if user and user.entity_id:
        donor_id = user.entity_id

    payload = DonationCreate(**{**payload.model_dump(), "donor_id": donor_id})
    if payload.donor_id not in store.donors:
        raise HTTPException(status_code=404, detail="Unknown donor")
    return store.create_donation(payload)


@router.get("/{donation_id}", response_model=Donation)
def get_donation(donation_id: str) -> Donation:
    escalation_service.process_due_escalations()
    if donation_id not in store.donations:
        raise HTTPException(status_code=404, detail="Donation not found")
    donation = store.donations[donation_id]
    _normalize_effective_status(donation)
    return donation


@router.patch("/{donation_id}/status", response_model=Donation)
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
