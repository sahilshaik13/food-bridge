from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import DonationStatus, DonationStatusUpdate, EmergencyResolveRequest, VolunteerTaskStatus
from app.services.demo_store import store
from app.services.escalation_service import escalation_service


def verify_escalation_windows() -> None:
    donation = next(iter(store.donations.values()), None)
    if not donation:
        print("[skip] no donations found")
        return
    escalation_service.schedule_escalation(donation)
    print(
        "[ok] escalation scheduled",
        donation.id,
        "wave",
        donation.broadcast_wave,
        "wave_expires_at",
        donation.wave_expires_at,
    )


def verify_volunteer_lifecycle() -> None:
    donation = next(iter(store.donations.values()), None)
    if not donation:
        print("[skip] no donations found")
        return
    store.update_donation_status(
        donation.id,
        DonationStatusUpdate(
            status=DonationStatus.assigned,
            volunteer_task_status=VolunteerTaskStatus.heading_to_pickup,
            volunteer_uid="vol_test",
            volunteer_name="Test Volunteer",
        ),
    )
    store.update_donation_status(
        donation.id,
        DonationStatusUpdate(
            status=DonationStatus.assigned,
            volunteer_task_status=VolunteerTaskStatus.delivered_pending_confirmation,
            volunteer_uid="vol_test",
            volunteer_name="Test Volunteer",
        ),
    )
    refreshed = store.donations[donation.id]
    print(
        "[ok] volunteer flow",
        refreshed.volunteer_task_status,
        "seconds",
        refreshed.volunteer_total_seconds,
    )


def verify_emergency_popup() -> None:
    req = next(iter(store.emergency_requests.values()), None)
    if not req:
        print("[skip] no emergency request found")
        return
    countdown = int((req.deadline_at - datetime.now(timezone.utc)).total_seconds())
    print(
        "[ok] emergency popup flags",
        req.popup_active,
        "targets",
        len(req.donor_targets),
        "countdown_s",
        max(0, countdown),
    )


def verify_emergency_resolution() -> None:
    req = next(iter(store.emergency_requests.values()), None)
    if not req:
        print("[skip] no emergency request found")
        return
    if req.pledged_kg <= 0:
        req.pledged_kg = min(req.quantity_goal_kg, 5)
    resolved = store.resolve_emergency_request(
        req.id,
        actor_id=req.ngo_id,
        payload=EmergencyResolveRequest(action="accept_partial", reason="verification script"),
    )
    print(
        "[ok] emergency resolved",
        resolved.id,
        "status",
        resolved.status,
        "pool_open",
        resolved.pool_open,
    )


if __name__ == "__main__":
    verify_escalation_windows()
    verify_volunteer_lifecycle()
    verify_emergency_popup()
    verify_emergency_resolution()
