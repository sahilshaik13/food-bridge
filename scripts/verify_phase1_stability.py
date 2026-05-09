from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.models import (
    DonationCreate,
    DonationStatus,
    DonationStatusUpdate,
    Role,
    UserProfile,
    VolunteerTaskStatus,
)
from app.routers.donations import verify_firebase_token
from app.services.demo_store import store


def _fake_token(uid: str, role: str) -> dict:
    return {"uid": uid, "role": role, "email": f"{uid}@foodbridge.dev"}


def _set_override(token: dict) -> None:
    app.dependency_overrides[verify_firebase_token] = lambda: token


def _clear_override() -> None:
    app.dependency_overrides.pop(verify_firebase_token, None)


def main() -> None:
    donor = next(iter(store.donors.values()))
    ngo = next(iter(store.ngos.values()))
    ngo.verification_status = "verified"
    store.ngos[ngo.id] = ngo

    donor_uid = "phase1_donor_uid"
    ngo_uid = "phase1_ngo_uid"
    volunteer_uid = "phase1_vol_uid"

    store.users[donor_uid] = UserProfile(
        id=donor_uid,
        role=Role.donor,
        display_name=donor.name,
        status="verified",
        entity_id=donor.id,
        email=f"{donor_uid}@foodbridge.dev",
    )
    store.users[ngo_uid] = UserProfile(
        id=ngo_uid,
        role=Role.ngo_coordinator,
        display_name=ngo.name,
        status="verified",
        entity_id=ngo.id,
        email=f"{ngo_uid}@foodbridge.dev",
    )
    store.users[volunteer_uid] = UserProfile(
        id=volunteer_uid,
        role=Role.ngo_volunteer,
        display_name="Phase Volunteer",
        status="active",
        entity_id=ngo.id,
        email=f"{volunteer_uid}@foodbridge.dev",
    )

    donation = store.create_donation(
        DonationCreate(
            donor_id=donor.id,
            food_type="phase1_test_food",
            quantity_kg=5,
            meal_count=25,
        )
    )
    store.update_donation_status(
        donation.id,
        DonationStatusUpdate(status=DonationStatus.accepted, ngo_id=ngo.id),
    )

    client = TestClient(app)

    _set_override(_fake_token(donor_uid, "donor"))
    donor_blocked = client.patch(
        f"/donations/{donation.id}/status",
        json={"status": "completed"},
    )
    assert donor_blocked.status_code == 403, donor_blocked.text

    _set_override(_fake_token(ngo_uid, "ngo_coordinator"))
    ngo_early_complete = client.patch(
        f"/donations/{donation.id}/status",
        json={"status": "completed", "volunteer_task_status": "delivered_pending_confirmation"},
    )
    assert ngo_early_complete.status_code in {409, 403}, ngo_early_complete.text

    _set_override(_fake_token(volunteer_uid, "ngo_volunteer"))
    volunteer_complete_blocked = client.patch(
        f"/donations/{donation.id}/status",
        json={"status": "completed", "volunteer_task_status": "delivered_pending_confirmation"},
    )
    assert volunteer_complete_blocked.status_code in {403, 409}, volunteer_complete_blocked.text

    volunteer_progress = client.patch(
        f"/donations/{donation.id}/status",
        json={"status": "accepted", "volunteer_task_status": "heading_to_pickup"},
    )
    assert volunteer_progress.status_code == 200, volunteer_progress.text

    _set_override(_fake_token(ngo_uid, "ngo_coordinator"))
    ngo_confirm = client.patch(
        f"/donations/{donation.id}/status",
        json={"status": "completed", "volunteer_task_status": "delivered_confirmed", "ngo_id": ngo.id},
    )
    assert ngo_confirm.status_code == 200, ngo_confirm.text

    _clear_override()
    print("[ok] Phase 1 stability guards validated")


if __name__ == "__main__":
    main()
