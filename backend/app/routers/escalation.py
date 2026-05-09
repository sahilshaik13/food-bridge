from fastapi import APIRouter, HTTPException

from app.services.escalation_service import escalation_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/escalate")
def handle_escalation_task(donation_id: str) -> dict:
    """Cloud Tasks calls this endpoint when an escalation timer fires."""
    result = escalation_service.expand_radius(donation_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/donations/{donation_id}/escalation-status")
def get_escalation_status(donation_id: str) -> dict:
    """Get the current escalation status of a donation."""
    from app.services.demo_store import store

    donation = store.donations.get(donation_id)
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found")

    from app.services.escalation_service import ESCALATION_RADIUS_LEVELS, ESCALATION_TIMERS_MINUTES

    return {
        "donation_id": donation_id,
        "current_status": donation.status,
        "escalation_level": donation.escalation_level,
        "current_radius_km": donation.current_radius_km,
        "notified_ngo_count": len(donation.notified_ngo_ids),
        "radius_levels": ESCALATION_RADIUS_LEVELS,
        "timer_minutes": ESCALATION_TIMERS_MINUTES.get(donation.escalation_level, 0),
        "next_escalation_at": (
            donation.last_escalation_at.isoformat()
            if donation.last_escalation_at
            else None
        ),
    }


@router.post("/donations/{donation_id}/trigger-escalation")
def trigger_escalation(donation_id: str) -> dict:
    """Manually trigger escalation for a donation (for testing/admin)."""
    result = escalation_service.expand_radius(donation_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
