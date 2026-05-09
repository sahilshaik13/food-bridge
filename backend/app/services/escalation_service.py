from datetime import datetime, timedelta, timezone
from app.core.config import get_settings
from app.core.cloud_clients import get_cloud_tasks_client
from app.models import Donation, DonationStatus, MatchScore, Notification, Role, CommunicationMessageCreate
from app.services.time_scale import scaled_timedelta_minutes


ESCALATION_RADIUS_LEVELS = {
    1: 5.0,
    2: 12.0,
    3: 100.0,  # practical citywide bucket
}

ESCALATION_TIMERS_MINUTES = {
    1: 30,
    2: 20,
    3: 10,
}

TASK_QUEUE_NAME = "foodbridge-escalation"


class EscalationService:
    def __init__(self):
        self.settings = get_settings()
        self.tasks_client = get_cloud_tasks_client()

    def schedule_escalation(self, donation: Donation) -> bool:
        if donation.status in {DonationStatus.accepted, DonationStatus.completed, DonationStatus.wasted, DonationStatus.expired}:
            return False

        current_level = donation.escalation_level
        timer_minutes = ESCALATION_TIMERS_MINUTES.get(current_level, 40)
        donation.wave_started_at = donation.wave_started_at or datetime.now(timezone.utc)
        donation.wave_expires_at = datetime.now(timezone.utc) + scaled_timedelta_minutes(timer_minutes)
        from app.services.demo_store import store
        store._write_doc("donations", donation.id, donation)

        if timer_minutes <= 0:
            self._execute_escalation(donation)
            return True

        if self.tasks_client:
            return self._schedule_cloud_task(donation, timer_minutes)
        else:
            print(f"[ESCALATION] No Cloud Tasks client; relying on local due-check for {donation.id}")
            return True

    def _schedule_cloud_task(self, donation: Donation, delay_minutes: int) -> bool:
        try:
            parent = self.tasks_client.queue_path(
                self.settings.google_cloud_project,
                self.settings.gcp_location,
                TASK_QUEUE_NAME,
            )

            task_name = f"projects/{self.settings.google_cloud_project}/locations/{self.settings.gcp_location}/queues/{TASK_QUEUE_NAME}/tasks/escalate-{donation.id}-level{donation.escalation_level}"

            task = {
                "name": task_name,
                "http_request": {
                    "http_method": "POST",
                    "url": f"https://{self.settings.google_cloud_project}.run.app/tasks/escalate",
                    "oidc_token": {
                        "service_account_email": f"{self.settings.google_cloud_project}@appspot.gserviceaccount.com",
                    },
                    "headers": {
                        "Content-Type": "application/json",
                    },
                    "body": donation.id.encode(),
                },
                "schedule_time": datetime.now(timezone.utc) + scaled_timedelta_minutes(delay_minutes),
            }

            self.tasks_client.create_task(parent=parent, task=task)
            print(f"[ESCALATION] Scheduled Cloud Task for donation {donation.id} at level {donation.escalation_level}, delay={delay_minutes}min")
            return True

        except Exception as e:
            print(f"[ESCALATION] Failed to schedule Cloud Task: {e}")
            return False

    def expand_radius(self, donation_id: str) -> dict:
        from app.services.demo_store import store

        donation = store.donations.get(donation_id)
        if not donation:
            return {"error": "Donation not found", "donation_id": donation_id}

        if donation.status in {DonationStatus.accepted, DonationStatus.completed, DonationStatus.wasted, DonationStatus.expired}:
            return {"error": "Donation already resolved", "status": donation.status, "donation_id": donation_id}

        return self._execute_escalation(donation)

    def process_due_escalations(self) -> int:
        from app.services.demo_store import store

        now = datetime.now(timezone.utc)
        active_states = {
            DonationStatus.pending_match,
            DonationStatus.notified,
            DonationStatus.needs_review,
            DonationStatus.escalated_radius_2,
            DonationStatus.escalated_radius_3,
        }
        processed = 0
        for donation in list(store.donations.values()):
            if donation.status not in active_states:
                continue
            if donation.wave_expires_at is None:
                if donation.status in {DonationStatus.escalated_radius_2, DonationStatus.escalated_radius_3}:
                    self._execute_escalation(donation)
                    processed += 1
                continue
            if donation.wave_expires_at <= now:
                self._execute_escalation(donation)
                processed += 1
        return processed

    def _execute_escalation(self, donation: Donation) -> dict:
        from app.services.demo_store import store

        current_level = donation.escalation_level
        current_radius = ESCALATION_RADIUS_LEVELS.get(current_level, 0.0)

        if current_level >= 3:
            donation.status = DonationStatus.wasted
            donation.updated_at = datetime.now(timezone.utc)
            donation.wave_expires_at = None
            store._write_doc("donations", donation.id, donation)
            store._sync_active_feed(donation)
            store._publish_event(
                "foodbridge-donations",
                {
                    "event": "donation_status_updated",
                    "donation_id": donation.id,
                    "status": donation.status.value,
                    "volunteer_task_status": donation.volunteer_task_status.value if donation.volunteer_task_status else None,
                    "updated_at": donation.updated_at.isoformat(),
                },
            )
            store.create_notification(
                Notification(
                    donation_id=donation.id,
                    recipient_role=Role.donor,
                    recipient_id=donation.donor_id,
                    title="Donation Wasted",
                    body=f"Your {donation.food_type} donation could not be delivered and was marked as wasted.",
                )
            )
            return {
                "donation_id": donation.id,
                "action": "marked_wasted",
                "reason": "No NGO accepted within expanded radius",
            }

        next_level = current_level + 1
        next_radius = ESCALATION_RADIUS_LEVELS.get(next_level, 15.0)

        expanded_queue = self._get_ngos_in_radius(donation, next_radius)
        expanded_queue = [ngo_id for ngo_id in expanded_queue if ngo_id not in donation.notified_ngo_ids]

        if not expanded_queue:
            donation.status = DonationStatus.wasted
            donation.updated_at = datetime.now(timezone.utc)
            donation.wave_expires_at = None
            store._write_doc("donations", donation.id, donation)
            store._sync_active_feed(donation)
            store._publish_event(
                "foodbridge-donations",
                {
                    "event": "donation_status_updated",
                    "donation_id": donation.id,
                    "status": donation.status.value,
                    "volunteer_task_status": donation.volunteer_task_status.value if donation.volunteer_task_status else None,
                    "updated_at": donation.updated_at.isoformat(),
                },
            )
            return {
                "donation_id": donation.id,
                "action": "marked_wasted",
                "reason": "No NGOs available in expanded radius",
            }

        newly_notified = [ngo_id for ngo_id in expanded_queue if ngo_id not in donation.notified_ngo_ids]

        donation.escalation_level = next_level
        donation.broadcast_wave = next_level
        donation.current_radius_km = next_radius
        donation.notified_ngo_ids.extend(newly_notified)
        donation.excluded_ngo_ids = list(set(donation.excluded_ngo_ids + donation.notified_ngo_ids))
        donation.last_escalation_at = datetime.now(timezone.utc)
        donation.wave_started_at = datetime.now(timezone.utc)
        donation.wave_expires_at = datetime.now(timezone.utc) + scaled_timedelta_minutes(
            ESCALATION_TIMERS_MINUTES.get(next_level, 10)
        )
        if next_level >= 3:
            donation.citywide_broadcasted = True

        if next_level == 2:
            donation.status = DonationStatus.escalated_radius_2
        elif next_level == 3:
            donation.status = DonationStatus.escalated_radius_3

        donation.updated_at = datetime.now(timezone.utc)
        store._write_doc("donations", donation.id, donation)
        store._sync_active_feed(donation)
        store._publish_event(
            "foodbridge-donations",
            {
                "event": "donation_status_updated",
                "donation_id": donation.id,
                "status": donation.status.value,
                "volunteer_task_status": donation.volunteer_task_status.value if donation.volunteer_task_status else None,
                "updated_at": donation.updated_at.isoformat(),
            },
        )

        self._notify_expanded_ngos(donation, expanded_queue)
        self._notify_admin_escalation(donation, next_radius, len(newly_notified))

        self.schedule_escalation(donation)

        return {
            "donation_id": donation.id,
            "action": "radius_expanded",
            "from_level": current_level,
            "to_level": next_level,
            "radius_km": next_radius,
            "new_notifications": len(newly_notified),
        }

    def _get_ngos_in_radius(self, donation: Donation, radius_km: float) -> list[str]:
        from app.services.demo_store import store
        from math import asin, cos, radians, sin, sqrt

        def calc_distance(lat1, lng1, lat2, lng2):
            R = 6371
            dlat = radians(lat2 - lat1)
            dlng = radians(lng2 - lng1)
            a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng/2)**2
            return 2 * R * asin(sqrt(a))

        ngo_ids = []
        for ngo in store.ngos.values():
            if ngo.verification_status != "verified":
                continue
            if donation.assigned_ngo_id and ngo.id == donation.assigned_ngo_id:
                continue
            distance = calc_distance(donation.location.lat, donation.location.lng, ngo.location.lat, ngo.location.lng)
            if distance <= radius_km:
                ngo_ids.append(ngo.id)
        return ngo_ids

    def _notify_expanded_ngos(self, donation: Donation, ngo_ids: list[str]):
        from app.services.demo_store import store

        for ngo_id in ngo_ids:
            if ngo_id not in donation.notified_ngo_ids[:-len(ngo_ids)] if len(donation.notified_ngo_ids) > len(ngo_ids) else True:
                ngo = store.ngos.get(ngo_id)
                if ngo:
                    store.create_notification(
                        Notification(
                            donation_id=donation.id,
                            recipient_role=Role.ngo_coordinator,
                            recipient_id=ngo_id,
                            title="Expanded surplus donation nearby",
                            body=f"{donation.donor_name} posted {donation.quantity_kg:g} kg {donation.food_type}. Previous NGO did not respond - now expanded to your area.",
                            channel="fcm",
                        )
                    )

    def _notify_admin_escalation(self, donation: Donation, new_radius: float, new_ngo_count: int):
        from app.services.demo_store import store

        store.create_notification(
            Notification(
                donation_id=donation.id,
                recipient_role=Role.super_admin,
                recipient_id="super_admin",
                title="Donation Escalated",
                body=f"Donation {donation.food_type} from {donation.donor_name} escalated to radius {new_radius}km. {new_ngo_count} new NGOs notified.",
            )
        )

    def handle_ngo_decline(self, donation_id: str, ngo_id: str) -> dict:
        from app.services.demo_store import store

        donation = store.donations.get(donation_id)
        if not donation:
            return {"error": "Donation not found"}

        if donation.status == DonationStatus.accepted:
            return {"error": "Donation already accepted", "status": donation.status}

        return self._execute_escalation(donation)

    def handle_ngo_accept(self, donation_id: str, ngo_id: str) -> dict:
        from app.services.demo_store import store

        donation = store.donations.get(donation_id)
        if not donation:
            return {"error": "Donation not found"}

        if donation.status in {DonationStatus.completed, DonationStatus.wasted, DonationStatus.expired}:
            return {"error": "Donation already resolved", "status": donation.status}

        ngo = store.ngos.get(ngo_id)
        if not ngo:
            return {"error": "NGO not found"}

        donation.assigned_ngo_id = ngo_id
        donation.assigned_ngo_name = ngo.name
        donation.status = DonationStatus.accepted
        donation.updated_at = datetime.now(timezone.utc)
        store._write_doc("donations", donation.id, donation)
        store._sync_active_feed(donation)
        store._publish_event(
            "foodbridge-donations",
            {
                "event": "donation_status_updated",
                "donation_id": donation.id,
                "status": donation.status.value,
                "volunteer_task_status": donation.volunteer_task_status.value if donation.volunteer_task_status else None,
                "updated_at": donation.updated_at.isoformat(),
            },
        )

        store.create_message(
            CommunicationMessageCreate(
                donation_id=donation.id,
                sender_role=Role.ngo_coordinator,
                sender_id=ngo_id,
                recipient_role=Role.donor,
                recipient_id=donation.donor_id,
                body=f"{ngo.name} accepted the pickup. Please keep {donation.food_type} sealed and ready.",
            )
        )

        store.create_notification(
            Notification(
                donation_id=donation.id,
                recipient_role=Role.donor,
                recipient_id=donation.donor_id,
                title="NGO Accepted Pickup",
                body=f"{ngo.name} accepted {donation.food_type}. NGO volunteer will arrive for pickup.",
            )
        )

        return {
            "donation_id": donation.id,
            "action": "accepted",
            "ngo_id": ngo_id,
            "ngo_name": ngo.name,
        }


escalation_service = EscalationService()
