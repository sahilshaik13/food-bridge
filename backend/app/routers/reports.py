from fastapi import APIRouter, HTTPException, Depends, Query

from app.services.demo_store import store
from app.services.auth_service import verify_firebase_token, get_current_user_role
from app.services.certificate_service import (
    ensure_fssai_certificate,
    generate_fssai_certificate_preview,
    list_donor_fssai_certificates,
    verify_certificate,
)
from app.services.csr_report_service import (
    generate_csr_report_for_donor,
    generate_csr_report_preview_for_donor,
    list_donor_csr_reports,
    verify_csr_report,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/fssai/{donation_id}")
def generate_fssai_report(
    donation_id: str,
    force: bool = Query(default=False),
    preview: bool = Query(default=False),
    certificate_uid: str | None = Query(default=None),
    decoded_token: dict = Depends(verify_firebase_token),
) -> dict:
    if donation_id not in store.donations:
        raise HTTPException(status_code=404, detail="Donation not found")
    donation = store.donations[donation_id]
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    donor_entity = user.entity_id if user and user.entity_id else uid
    if role is None or role.value not in {"donor", "super_admin"}:
        raise HTTPException(status_code=403, detail="Not authorized to generate this certificate")
    if role.value == "donor" and donation.donor_id != donor_entity:
        raise HTTPException(status_code=403, detail="Donor can generate certificate only for own donation")
    try:
        if preview:
            return generate_fssai_certificate_preview(
                donation_id=donation_id,
                requested_by=uid or "unknown",
                requested_via="web_preview",
                uid_override=certificate_uid,
            )
        return ensure_fssai_certificate(
            donation_id=donation_id,
            requested_by=uid or "unknown",
            requested_via="web",
            force=force,
            uid_override=certificate_uid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/fssai/list")
def list_fssai_reports(decoded_token: dict = Depends(verify_firebase_token)) -> dict:
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    donor_entity = user.entity_id if user and user.entity_id else uid
    if role is None or role.value not in {"donor", "super_admin"}:
        raise HTTPException(status_code=403, detail="Not authorized to view this report list")
    if role.value == "super_admin":
        generated = []
        for donor in store.donors.values():
            generated.extend(list_donor_fssai_certificates(donor.id))
        generated.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
        return {"generated": generated, "pending": []}

    generated = list_donor_fssai_certificates(donor_entity or "")
    generated_ids = {item.get("donation_id") for item in generated}
    pending = []
    for donation in store.donations.values():
        if donation.donor_id != donor_entity:
            continue
        is_completed = (
            donation.status.value == "completed"
            or donation.completed_at
            or donation.delivery_confirmed_at
            or (donation.volunteer_task_status and donation.volunteer_task_status.value == "delivered_confirmed")
        )
        if is_completed and donation.id not in generated_ids:
            pending.append(
                {
                    "donation_id": donation.id,
                    "food_type": donation.food_type,
                    "quantity_kg": donation.quantity_kg,
                    "completed_at": (donation.completed_at or donation.delivery_confirmed_at or donation.updated_at).isoformat(),
                }
            )
    pending.sort(key=lambda x: x.get("completed_at", ""), reverse=True)
    return {"generated": generated, "pending": pending}


@router.post("/csr/{donor_id}")
def generate_csr_report(
    donor_id: str,
    force: bool = Query(default=False),
    preview: bool = Query(default=False),
    report_id: str | None = Query(default=None),
    decoded_token: dict = Depends(verify_firebase_token),
) -> dict:
    if donor_id not in store.donors:
        raise HTTPException(status_code=404, detail="Donor not found")
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    donor_entity = user.entity_id if user and user.entity_id else uid
    if role is None or role.value not in {"donor", "super_admin"}:
        raise HTTPException(status_code=403, detail="Not authorized to generate CSR report")
    if role.value == "donor" and donor_id != donor_entity:
        raise HTTPException(status_code=403, detail="Donor can generate CSR only for own account")
    try:
        if preview:
            return generate_csr_report_preview_for_donor(
                donor_id=donor_id,
                requested_by=uid or "unknown",
                requested_via="web_preview",
                report_id_override=report_id,
            )
        return generate_csr_report_for_donor(
            donor_id=donor_id,
            requested_by=uid or "unknown",
            requested_via="web",
            force=force,
            report_id_override=report_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/csr/list")
def list_csr_reports(decoded_token: dict = Depends(verify_firebase_token)) -> dict:
    role = get_current_user_role(decoded_token)
    uid = decoded_token.get("uid")
    user = store.users.get(uid)
    donor_entity = user.entity_id if user and user.entity_id else uid
    if role is None or role.value not in {"donor", "super_admin"}:
        raise HTTPException(status_code=403, detail="Not authorized to view CSR reports")
    if role.value == "super_admin":
        generated = []
        for donor in store.donors.values():
            generated.extend(list_donor_csr_reports(donor.id))
        generated.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
        return {"generated": generated}
    return {"generated": list_donor_csr_reports(donor_entity or "")}


@router.get("/verify/{certificate_uid}")
def verify_fssai_certificate(certificate_uid: str, sig: str | None = None) -> dict:
    if not sig:
        raise HTTPException(status_code=400, detail="Missing signature")
    result = verify_certificate(certificate_uid, sig)
    if not result.get("valid"):
        raise HTTPException(status_code=401, detail=result)
    return result


@router.get("/csr/verify/{report_id}")
def verify_csr(report_id: str, sig: str | None = None) -> dict:
    if not sig:
        raise HTTPException(status_code=400, detail="Missing signature")
    result = verify_csr_report(report_id, sig)
    if not result.get("valid"):
        raise HTTPException(status_code=401, detail=result)
    return result
