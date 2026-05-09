from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from app.models import (
    EmergencyContributionCreate,
    EmergencyRequest,
    EmergencyRequestCreate,
    EmergencyResolveRequest,
    ImpactStats,
    Prediction,
)
from app.services.demo_store import store
from app.services.auth_service import verify_firebase_token, get_current_user_role
from app.services.time_scale import logical_minutes_from_timedelta

router = APIRouter(tags=["intelligence"])


@router.get("/impact", response_model=ImpactStats)
def get_impact() -> ImpactStats:
    return store.impact()


@router.get("/predictions/surplus", response_model=list[Prediction])
def get_predictions() -> list[Prediction]:
    return store.predictions()


@router.post("/emergency-requests", response_model=EmergencyRequest)
def create_emergency_request(
    payload: EmergencyRequestCreate,
    decoded_token: dict = Depends(verify_firebase_token),
) -> EmergencyRequest:
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    if role is None or role.value != "ngo_coordinator":
        raise HTTPException(status_code=403, detail="Only NGO coordinators can create emergency requests")
    if user and user.entity_id and user.entity_id != payload.ngo_id:
        raise HTTPException(status_code=403, detail="Cannot create emergency request for another NGO")
    return store.create_emergency_request(payload)


@router.get("/emergency-requests", response_model=list[EmergencyRequest])
def list_emergency_requests() -> list[EmergencyRequest]:
    store.process_due_emergency_requests()
    return sorted(store.emergency_requests.values(), key=lambda item: item.created_at, reverse=True)


@router.get("/emergency-requests/active-popup")
def list_active_popup_emergencies(decoded_token: dict = Depends(verify_firebase_token)) -> list[dict]:
    store.process_due_emergency_requests()
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    now = datetime.now(timezone.utc)
    items = sorted(store.emergency_requests.values(), key=lambda item: item.created_at, reverse=True)
    result: list[dict] = []
    for item in items:
        if not item.popup_active:
            continue
        if item.popup_expires_at and item.popup_expires_at < now:
            continue
        if role and role.value == "ngo_coordinator" and user and user.entity_id != item.ngo_id:
            continue
        progress_pct = 0 if item.quantity_goal_kg <= 0 else round((item.pledged_kg / item.quantity_goal_kg) * 100, 1)
        countdown_seconds = logical_minutes_from_timedelta((item.deadline_at - now).total_seconds()) * 60
        result.append(
            {
                **item.model_dump(mode="json"),
                "progress_pct": progress_pct,
                "remaining_kg": max(0, round(item.quantity_goal_kg - item.pledged_kg, 2)),
                "countdown_seconds": countdown_seconds,
                "contributors_count": len(item.contributions),
            }
        )
    return result


@router.post("/emergency-requests/{request_id}/contribute", response_model=EmergencyRequest)
def contribute_emergency_request(
    request_id: str,
    payload: EmergencyContributionCreate,
    decoded_token: dict = Depends(verify_firebase_token),
) -> EmergencyRequest:
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    if role is None or role.value != "donor":
        raise HTTPException(status_code=403, detail="Only donors can contribute to emergency pool")
    donor_entity = user.entity_id if user and user.entity_id else uid
    if donor_entity != payload.donor_id:
        raise HTTPException(status_code=403, detail="Donor can contribute only with own donor profile")
    try:
        return store.contribute_emergency_pool(request_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/emergency-requests/{request_id}/resolve", response_model=EmergencyRequest)
def resolve_emergency_request(
    request_id: str,
    payload: EmergencyResolveRequest,
    decoded_token: dict = Depends(verify_firebase_token),
) -> EmergencyRequest:
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    if role is None or role.value != "ngo_coordinator":
        raise HTTPException(status_code=403, detail="Only NGO coordinators can resolve emergency requests")
    request = store.emergency_requests.get(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Emergency request not found")
    ngo_entity = user.entity_id if user and user.entity_id else None
    if ngo_entity != request.ngo_id:
        raise HTTPException(status_code=403, detail="Cannot resolve another NGO emergency request")
    try:
        return store.resolve_emergency_request(request_id, actor_id=uid or request.ngo_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/heatmap/data")
def get_heatmap_data() -> dict:
    surplus_features = [
        {
            "type": "Feature",
            "properties": {"kind": "surplus", "weight": donor.monthly_meals, "name": donor.name},
            "geometry": {"type": "Point", "coordinates": [donor.location.lng, donor.location.lat]},
        }
        for donor in store.donors.values()
    ]
    demand_features = [
        {
            "type": "Feature",
            "properties": {"kind": "demand", "weight": ngo.beneficiary_count, "name": ngo.name},
            "geometry": {"type": "Point", "coordinates": [ngo.location.lng, ngo.location.lat]},
        }
        for ngo in store.ngos.values()
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "surplus": {"type": "FeatureCollection", "features": surplus_features},
        "demand": {"type": "FeatureCollection", "features": demand_features},
        "coverage_gaps": [
            {"area": "Old City", "severity": "high", "reason": "High demand, thin recurring donor density"},
            {"area": "Secunderabad", "severity": "medium", "reason": "Night shelter demand peaks after 9pm"},
        ],
    }
