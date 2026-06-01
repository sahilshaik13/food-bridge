from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from math import asin, cos, radians, sin, sqrt
import os
import re
from uuid import uuid4
from app.services.notification_service import send_fcm_notification

from app.core.cloud_clients import get_firestore_client, get_realtime_database
from app.core.config import get_settings
from app.models import (
    CommunicationMessage,
    CommunicationMessageCreate,
    Donor,
    DonorCreate,
    DonorTelegramUpdate,
    Donation,
    DonationCreate,
    DonationScanRecord,
    DonationItem,
    DonationStatus,
    DonationStatusUpdate,
    EmergencyContribution,
    EmergencyContributionCreate,
    EmergencyRequest,
    EmergencyRequestCreate,
    EmergencyResolveRequest,
    GeminiScan,
    ImpactStats,
    Location,
    MatchScore,
    Ngo,
    NgoCreate,
    Notification,
    Prediction,
    Role,
    TelegramDonationResult,
    TelegramAuthState,
    TelegramLinkingToken,
    TelegramLink,
    TelegramLinkRequest,
    SlaveBot,
    ConversationState,
    ConversationStep,
    UserProfile,
    UserVerifyUpdate,
    VolunteerInviteCreate,
    VolunteerProfile,
    VolunteerInviteToken,
    VolunteerTaskStatus,
    scan_phase2_contract_version,
)
from app.services.log_service import log_event
from app.services.time_scale import scaled_timedelta_minutes
from app.services.accuracy_engine import evaluate_donation_accuracy
from app.services.openweather_service import fetch_weather_at_listing
from app.services.ml_training_export_service import export_donation_ml_event, terminal_statuses
from app.services.donor_scoring import recompute_all_donor_scores


def distance_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    radius = 6371
    d_lat = radians(b_lat - a_lat)
    d_lng = radians(b_lng - a_lng)
    lat1 = radians(a_lat)
    lat2 = radians(b_lat)
    value = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lng / 2) ** 2
    return round(2 * radius * asin(sqrt(value)), 2)


def coerce_legacy_donation_payload(raw: dict) -> dict:
    """
    Firestore rows written before Phase 2 may omit `scan` and `expires_at`.
    Fill defaults so `Donation` validates (e.g. seeded `sgen_*` docs).
    """
    data = dict(raw)
    food_type = (data.get("food_type") or "mixed").strip() or "mixed"

    scan_raw = data.get("scan")
    if not scan_raw:
        data["scan"] = {
            "passed": True,
            "confidence": 0.75,
            "reason": "Legacy Firestore record: scan metadata missing; backfilled at load.",
            "detected_food_type": food_type,
            "freshness_window_minutes": 180,
            "fallback_used": True,
        }
    elif isinstance(scan_raw, dict):
        s = scan_raw
        scan_coerced = {
            "passed": bool(s.get("passed", True)),
            "confidence": float(s["confidence"]) if s.get("confidence") is not None else 0.75,
            "reason": (s.get("reason") or "Legacy scan row incomplete; coerced at load.").strip(),
            "detected_food_type": (s.get("detected_food_type") or food_type).strip() or food_type,
            "freshness_window_minutes": max(1, int(s.get("freshness_window_minutes") or 180)),
            "model_id": s.get("model_id"),
            "model_version": s.get("model_version"),
            "fallback_used": bool(s.get("fallback_used", True)),
        }
        if s.get("generated_at") is not None:
            scan_coerced["generated_at"] = s["generated_at"]
        data["scan"] = scan_coerced
    else:
        data["scan"] = {
            "passed": True,
            "confidence": 0.75,
            "reason": "Legacy Firestore record: scan field had unexpected shape; reset at load.",
            "detected_food_type": food_type,
            "freshness_window_minutes": 180,
            "fallback_used": True,
        }

    sd = data.get("scan")
    fw = max(1, int(sd.get("freshness_window_minutes") or 180)) if isinstance(sd, dict) else 180

    if data.get("expires_at") is None:
        created = data.get("created_at")
        if created is not None:
            ca = created
            if isinstance(ca, datetime) and ca.tzinfo is None:
                ca = ca.replace(tzinfo=timezone.utc)
            data["expires_at"] = ca + scaled_timedelta_minutes(fw)
        else:
            data["expires_at"] = datetime.now(timezone.utc) + scaled_timedelta_minutes(fw)

    return data


from app.services.vertex_ai_service import scan_food_with_vertex_ai

EMERGENCY_REQUESTS_COLLECTION = "emergency_pools_v2"

def scan_food(food_type: str, notes: str | None = None) -> GeminiScan:
    # Local/dev override to avoid external AI dependency.
    if os.environ.get("DISABLE_AI_INTEGRATION", "false").lower() == "true":
        s = get_settings()
        return GeminiScan(
            passed=True,
            confidence=0.95,
            reason="AI integration disabled; trusted manual/demo mode",
            detected_food_type=food_type,
            freshness_window_minutes=180,
            model_id=s.vertex_ai_model_id,
            model_version=s.vertex_ai_model_version,
            fallback_used=True,
        )
    # We could pass image bytes here if available, but for now we use text hints
    return scan_food_with_vertex_ai(b"", food_type_hint=food_type)


def scan_food_multimodal(food_type: str, notes: str | None, image_bytes: bytes | None) -> GeminiScan:
    """PRD: photo-first scan — use image bytes when provided; else text-only path."""
    if os.environ.get("DISABLE_AI_INTEGRATION", "false").lower() == "true":
        s = get_settings()
        return GeminiScan(
            passed=True,
            confidence=0.95,
            reason="AI integration disabled; trusted manual/demo mode",
            detected_food_type=food_type,
            freshness_window_minutes=180,
            model_id=s.vertex_ai_model_id,
            model_version=s.vertex_ai_model_version,
            fallback_used=True,
        )
    if image_bytes:
        return scan_food_with_vertex_ai(image_bytes, food_type_hint=food_type)
    return scan_food(food_type, notes)


class DemoStore:
    def __init__(self) -> None:
        self.donors = {}
        self.ngos = {}
        self.donations: dict[str, Donation] = {}
        self.emergency_requests: dict[str, EmergencyRequest] = {}
        self.notifications: dict[str, Notification] = {}
        self.messages: dict[str, CommunicationMessage] = {}
        self.telegram_links: dict[str, TelegramLink] = {}
        self.users: dict[str, UserProfile] = {}
        self.volunteers: dict[str, VolunteerProfile] = {}
        self.linking_tokens: dict[str, TelegramLinkingToken] = {}
        self.volunteer_invites: dict[str, VolunteerInviteToken] = {}
        self.auth_states: dict[str, TelegramAuthState] = {}
        self.slave_bots: dict[str, SlaveBot] = {}
        self.conversation_states: dict[str, ConversationState] = {}
        self.firestore_enabled = True
        self._bootstrap_firestore()
        self._sync_impact_feed()
        self._sync_entity_directory_feed()

    def upload_image_to_gcp(self, image_bytes: bytes, filename: str) -> str:
        from app.core.cloud_clients import ensure_bucket_exists
        settings = get_settings()
        bucket_name = f"{settings.google_cloud_project}-assets"
        bucket = ensure_bucket_exists(bucket_name)
        blob = bucket.blob(f"donations/{filename}")
        blob.upload_from_string(image_bytes, content_type="image/jpeg")
        # For demo, make it public (or use signed URLs in prod)
        blob.make_public()
        return blob.public_url

    def _seed_users(self) -> None:
        self.users["super_admin"] = UserProfile(
            id="super_admin",
            role=Role.super_admin,
            display_name="FoodBridge Super Admin",
            status="active",
        )
        self.users["municipal_admin"] = UserProfile(
            id="municipal_admin",
            role=Role.municipal_admin,
            display_name="GHMC Municipal Viewer",
            status="active",
        )
        for donor in self.donors.values():
            self.users[donor.id] = UserProfile(
                id=donor.id,
                role=Role.donor,
                display_name=donor.name,
                status="verified" if donor.verification_status == "verified" else "pending",
                entity_id=donor.id,
            )
        for ngo in self.ngos.values():
            self.users[ngo.id] = UserProfile(
                id=ngo.id,
                role=Role.ngo_coordinator,
                display_name=ngo.name,
                status="verified" if ngo.verification_status == "verified" else "pending",
                entity_id=ngo.id,
            )


    def _firestore(self):
        if not self.firestore_enabled or not get_settings().firestore_sync_enabled:
            return None
        try:
            return get_firestore_client()
        except Exception:
            self.firestore_enabled = False
            return None

    def _write_doc(self, collection: str, doc_id: str, data) -> None:
        db = self._firestore()
        if db is None:
            return
        try:
            payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
            db.collection(collection).document(doc_id).set(payload, merge=True, timeout=5)
        except Exception:
            self.firestore_enabled = False

    def _persist_donation_scan_record(
        self,
        *,
        donation_id: str,
        donor_id: str,
        scan: GeminiScan,
        kind: Literal["donation_created", "scan_retry", "migrated_from_donation"],
    ) -> None:
        rec = DonationScanRecord(
            donation_id=donation_id,
            donor_id=donor_id,
            kind=kind,
            scan=scan,
        )
        self._write_doc("donation_scans", rec.id, rec)

    def _publish_event(self, topic_id: str, data: dict) -> None:
        if not get_settings().google_cloud_project:
            return
        try:
            from app.core.cloud_clients import get_pubsub_publisher
            import json
            publisher = get_pubsub_publisher()
            topic_path = publisher.topic_path(get_settings().google_cloud_project, topic_id)
            payload = json.dumps(data, default=str).encode("utf-8")
            publisher.publish(topic_path, payload)
        except Exception as e:
            print(f"PubSub error on {topic_id}: {e}")

    def _sync_active_feed(self, donation: Donation) -> None:
        try:
            root = get_realtime_database()
        except Exception:
            return

        terminal_statuses = {
            DonationStatus.completed.value,
            DonationStatus.declined.value,
            DonationStatus.expired.value,
            DonationStatus.wasted.value,
        }
        delivered_task = {VolunteerTaskStatus.delivered_confirmed.value}
        task_status = donation.volunteer_task_status.value if donation.volunteer_task_status else None
        is_active = donation.status.value not in terminal_statuses and task_status not in delivered_task

        payload = donation.model_dump(mode="json")

        def set_or_delete(path: str):
            node = root.child(path)
            if is_active:
                node.set(payload)
            else:
                node.delete()

        set_or_delete(f"active_feeds/donor/{donation.donor_id}/{donation.id}")
        for ngo_id in donation.notified_ngo_ids:
            set_or_delete(f"active_feeds/ngo/{ngo_id}/{donation.id}")
        if donation.assigned_ngo_id:
            set_or_delete(f"active_feeds/ngo/{donation.assigned_ngo_id}/{donation.id}")

            volunteer_uid = donation.volunteer_uid
            if not volunteer_uid:
                volunteer_user = next(
                    (
                        u
                        for u in self.users.values()
                        if u.role == Role.ngo_volunteer and u.entity_id == donation.assigned_ngo_id
                    ),
                    None,
                )
                volunteer_uid = volunteer_user.id if volunteer_user else None
            if volunteer_uid:
                set_or_delete(f"active_feeds/volunteer/{volunteer_uid}/{donation.id}")
        self._sync_impact_feed(root)

    def _sync_impact_feed(self, root=None) -> None:
        try:
            root = root or get_realtime_database()
        except Exception:
            return
        try:
            payload = self.impact().model_dump(mode="json")
            root.child("metrics/impact/global").set(payload)
        except Exception as exc:
            # Cloud Run ADC often lacks RTDB rules until the GCP SA is granted access in Firebase.
            print(f"Impact feed sync skipped (RTDB): {exc}")

    def _sync_entity_directory_feed(self, root=None) -> None:
        try:
            root = root or get_realtime_database()
        except Exception:
            return

        donors_payload = {
            donor.id: {
                "id": donor.id,
                "name": donor.name,
                "area": donor.area,
                "trust_score": donor.score.trust_score if donor.score else None,
                "trust_tier": donor.score.trust_tier if donor.score else None,
            }
            for donor in self.donors.values()
        }
        ngos_payload = {
            ngo.id: {"id": ngo.id, "name": ngo.name, "area": ngo.area}
            for ngo in self.ngos.values()
        }
        volunteers_payload = {
            volunteer.id: {
                "id": volunteer.id,
                "name": volunteer.name,
                "ngo_id": volunteer.ngo_id,
                "status": volunteer.status,
            }
            for volunteer in self.volunteers.values()
        }

        try:
            root.child("directory/entities/donors").set(donors_payload)
            root.child("directory/entities/ngos").set(ngos_payload)
            root.child("directory/entities/volunteers").set(volunteers_payload)
        except Exception as exc:
            print(f"Entity directory feed sync skipped (RTDB): {exc}")

    def _recompute_all_donor_scores(self) -> None:
        all_donations = list(self.donations.values())
        by_id = recompute_all_donor_scores(list(self.donors.values()), all_donations)
        for donor_id, donor in list(self.donors.items()):
            score = by_id.get(donor_id)
            if score is None:
                continue
            donor.score = score
            self.donors[donor_id] = donor
            self._write_doc("donors", donor.id, donor)

    def _sync_emergency_feed(self, request: EmergencyRequest) -> None:
        try:
            root = get_realtime_database()
        except Exception:
            return

        now = datetime.now(timezone.utc)
        is_visible = (
            request.popup_active
            and request.pool_open
            and request.status not in {"cancelled", "fulfilled"}
            and (request.popup_expires_at is None or request.popup_expires_at >= now)
        )
        is_history = request.status in {"fulfilled", "cancelled"} or not request.pool_open

        payload = request.model_dump(mode="json")

        def set_or_delete(path: str) -> None:
            node = root.child(path)
            if is_visible:
                node.set(payload)
            else:
                node.delete()

        set_or_delete(f"active_feeds/emergency/all/{request.id}")
        set_or_delete(f"active_feeds/emergency/ngo/{request.ngo_id}/{request.id}")
        for donor_id in request.donor_targets:
            set_or_delete(f"active_feeds/emergency/donor/{donor_id}/{request.id}")

        def set_or_delete_history(path: str) -> None:
            node = root.child(path)
            if is_history:
                node.set(payload)
            else:
                node.delete()

        set_or_delete_history(f"history_feeds/emergency/all/{request.id}")
        set_or_delete_history(f"history_feeds/emergency/admin/{request.id}")
        set_or_delete_history(f"history_feeds/emergency/municipal/{request.id}")
        set_or_delete_history(f"history_feeds/emergency/ngo/{request.ngo_id}/{request.id}")
        for donor_id in request.donor_targets:
            set_or_delete_history(f"history_feeds/emergency/donor/{donor_id}/{request.id}")

    def _bootstrap_firestore(self) -> None:
        db = self._firestore()
        if db is None:
            print("Firestore not available - using in-memory store")
            return

        try:
            print("Reading from Firestore...")
            
            donor_docs = db.collection("donors").stream()
            self.donors = {}
            for doc in donor_docs:
                data = doc.to_dict()
                if data:
                    try:
                        self.donors[data["id"]] = Donor(**data)
                    except Exception as e:
                        print(f"Skipping invalid donor {doc.id}: {e}")
            
            ngo_docs = db.collection("ngos").stream()
            self.ngos = {}
            for doc in ngo_docs:
                data = doc.to_dict()
                if data:
                    try:
                        self.ngos[data["id"]] = Ngo(**data)
                    except Exception as e:
                        print(f"Skipping invalid NGO {doc.id}: {e}")
            
            user_docs = db.collection("users").stream()
            self.users = {}
            for doc in user_docs:
                data = doc.to_dict()
                if data:
                    try:
                        self.users[data["id"]] = UserProfile(**data)
                    except Exception as e:
                        print(f"Skipping invalid user {doc.id}: {e}")

            volunteer_docs = db.collection("volunteers").stream()
            self.volunteers = {}
            for doc in volunteer_docs:
                data = doc.to_dict()
                if data:
                    try:
                        self.volunteers[data["id"]] = VolunteerProfile(**data)
                    except Exception as e:
                        print(f"Skipping invalid volunteer {doc.id}: {e}")

            invite_docs = db.collection("volunteer_invites").stream()
            self.volunteer_invites = {}
            for doc in invite_docs:
                data = doc.to_dict()
                if data:
                    try:
                        self.volunteer_invites[data["token"]] = VolunteerInviteToken(**data)
                    except Exception as e:
                        print(f"Skipping invalid volunteer invite {doc.id}: {e}")
            
            if not self.users:
                self._seed_users()
                for user in self.users.values():
                    self._write_doc("users", user.id, user)
            
            donation_docs = db.collection("donations").stream()
            self.donations = {}
            for doc in donation_docs:
                data = doc.to_dict()
                if data:
                    try:
                        from app.models import MatchScore
                        if not data.get("id"):
                            data["id"] = doc.id
                        data = coerce_legacy_donation_payload(data)
                        ngo_queue_data = data.get("ngo_queue", [])
                        data["ngo_queue"] = [MatchScore(**q) for q in ngo_queue_data]
                        self.donations[data["id"]] = Donation(**data)
                    except Exception as e:
                        print(f"Skipping invalid donation {doc.id}: {e}")

            emergency_docs = db.collection(EMERGENCY_REQUESTS_COLLECTION).stream()
            self.emergency_requests = {}
            for doc in emergency_docs:
                data = doc.to_dict()
                if data:
                    try:
                        self.emergency_requests[data["id"]] = EmergencyRequest(**data)
                    except Exception as e:
                        print(f"Skipping invalid emergency request {doc.id}: {e}")

            for request in self.emergency_requests.values():
                self._sync_emergency_feed(request)
            self._recompute_all_donor_scores()
            
            print(f"Loaded from Firestore: {len(self.donors)} donors, {len(self.ngos)} NGOs, {len(self.donations)} donations")
            
        except Exception as e:
            print(f"Error reading from Firestore: {e}")
            print("Falling back to empty in-memory entities")
            self.donors = {}
            self.ngos = {}
            self._recompute_all_donor_scores()
            self._seed_users()

    def _seed_donation(self) -> None:
        payload = DonationCreate(
            donor_id="donor_shah_ghouse",
            food_type="biryani",
            quantity_kg=28,
            meal_count=140,
            notes="Dinner buffet surplus packed in trays",
        )
        donation = self.create_donation(payload)
        self.update_donation_status(
            donation.id,
            DonationStatusUpdate(status=DonationStatus.accepted, ngo_id=donation.ngo_queue[0].ngo_id),
        )

    def _rank_ngos_heuristic(self, payload: DonationCreate) -> list[MatchScore]:
        donor = self.donors[payload.donor_id]
        location = payload.location or donor.location
        primary_food_type = payload.items[0].food_type if payload.items else payload.food_type
        scores: list[MatchScore] = []

        for ngo in self.ngos.values():
            distance = distance_km(location.lat, location.lng, ngo.location.lat, ngo.location.lng)
            proximity = max(0, 100 - int(distance * 8))
            food_score = 96 if primary_food_type.lower() in ngo.food_preferences else 62
            nutrition = min(100, 55 + int(ngo.beneficiary_count / 8))
            total = round((proximity * 0.45) + (food_score * 0.3) + (nutrition * 0.25))
            scores.append(
                MatchScore(
                    ngo_id=ngo.id,
                    ngo_name=ngo.name,
                    distance_km=distance,
                    total_score=total,
                    proximity_score=proximity,
                    food_type_score=food_score,
                    nutrition_score=nutrition,
                    reason=f"{ngo.area} coverage, {ngo.beneficiary_count} beneficiaries, compatible food profile.",
                )
            )

        return sorted(scores, key=lambda item: item.total_score, reverse=True)

    def rank_ngos(self, payload: DonationCreate) -> list[MatchScore]:
        base = self._rank_ngos_heuristic(payload)
        settings = get_settings()
        if os.environ.get("DISABLE_AI_INTEGRATION", "false").lower() == "true":
            return base
        if not settings.matching_vertex_enabled:
            return base
        try:
            from app.services.ngo_matching_vertex import refine_ngo_queue_with_vertex

            donor = self.donors[payload.donor_id]
            primary_food_type = payload.items[0].food_type if payload.items else payload.food_type
            return refine_ngo_queue_with_vertex(
                primary_food_type=primary_food_type,
                quantity_kg=payload.quantity_kg,
                donor_area=donor.area,
                heuristic_scores=base,
            )
        except Exception as exc:
            print(f"rank_ngos: Gemini refinement skipped ({exc})")
            return base

    def _donation_to_create_payload(self, donation: Donation) -> DonationCreate:
        """Rebuild ranking input from a persisted donation (Pub/Sub matching worker)."""
        return DonationCreate(
            donor_id=donation.donor_id,
            food_type=donation.food_type,
            quantity_kg=donation.quantity_kg,
            meal_count=donation.meal_count,
            items=list(donation.items),
            location=donation.location,
            photo_url=donation.photo_url,
            notes=donation.notes,
            food_prepared_at=donation.food_prepared_at,
            storage_ambient_temp_c=donation.storage_ambient_temp_c,
            held_in_refrigeration=donation.held_in_refrigeration,
            operational_metrics_notes=donation.operational_metrics_notes,
        )

    def run_matching_for_donation(self, donation_id: str) -> None:
        """
        Idempotent: ranks NGOs and notifies — used by Pub/Sub subscriber or inline fallback.
        Skips donations that already have a queue or are in manual review.
        """
        donation = self.donations.get(donation_id)
        if not donation:
            return
        if donation.status in {DonationStatus.needs_review, DonationStatus.pending_scan_retry}:
            return
        if donation.ngo_queue:
            return
        payload = self._donation_to_create_payload(donation)
        queue = self.rank_ngos(payload)
        top = queue[0] if queue else None
        donation.ngo_queue = queue
        donation.current_radius_km = top.distance_km if top else 0.0
        donation.notified_ngo_ids = [top.ngo_id] if top else []
        donation.updated_at = datetime.now(timezone.utc)
        wave_now = datetime.now(timezone.utc)
        if queue:
            donation.status = DonationStatus.notified
            donation.wave_started_at = wave_now
            donation.wave_expires_at = wave_now + scaled_timedelta_minutes(30)
        self.donations[donation.id] = donation
        self._write_doc("donations", donation.id, donation)
        self._sync_active_feed(donation)
        self._create_donation_notifications(donation)
        if donation.status == DonationStatus.notified:
            from app.services.escalation_service import escalation_service

            escalation_service.schedule_escalation(donation)

    def create_donation(self, payload: DonationCreate, *, image_bytes: bytes | None = None) -> Donation:
        donor = self.donors[payload.donor_id]
        settings = get_settings()
        use_pubsub_pipeline = settings.pubsub_matching_enabled

        if image_bytes is not None:
            hint = payload.food_type or (payload.notes or "")[:200] or "mixed meals"
            scan = scan_food_multimodal(hint, payload.notes, image_bytes)
            items = payload.items or [
                DonationItem(
                    food_type=scan.detected_food_type or payload.food_type,
                    quantity_kg=payload.quantity_kg,
                    meal_count=payload.meal_count,
                )
            ]
        else:
            items = payload.items or [
                DonationItem(food_type=payload.food_type, quantity_kg=payload.quantity_kg, meal_count=payload.meal_count)
            ]
        total_qty = round(sum(item.quantity_kg for item in items), 2)
        total_meals = int(sum(item.meal_count for item in items))
        primary_food_type = items[0].food_type if items else payload.food_type
        photo_url = payload.photo_url
        if image_bytes is not None:
            photo_url = self.upload_image_to_gcp(image_bytes, f"{uuid4().hex}.jpg")
        payload = DonationCreate(
            **{
                **payload.model_dump(),
                "food_type": primary_food_type,
                "quantity_kg": total_qty,
                "meal_count": total_meals,
                "items": items,
                "photo_url": photo_url,
            }
        )
        if image_bytes is None:
            scan = scan_food(primary_food_type, payload.notes)
        queue = [] if use_pubsub_pipeline else self.rank_ngos(payload)
        donation = Donation.from_create(payload, donor, scan, queue)
        # Weather uses donor profile coordinates from DB (authoritative venue location).
        weather = fetch_weather_at_listing(donor.location.lat, donor.location.lng)
        donation.weather_at_listing = weather
        donation.accuracy = evaluate_donation_accuracy(
            scan,
            quantity_kg=payload.quantity_kg,
            notes=payload.notes,
            donor_trust_score=donor.score.trust_score if donor.score else None,
            donor_trust_tier=donor.score.trust_tier if donor.score else None,
            food_prepared_at=payload.food_prepared_at,
            storage_ambient_temp_c=payload.storage_ambient_temp_c,
            held_in_refrigeration=payload.held_in_refrigeration,
            operational_metrics_notes=payload.operational_metrics_notes,
            weather=weather,
            listing_created_at=donation.created_at,
        )
        rec = donation.accuracy.recommendation
        hard_fail = rec == "auto_reject"
        soft_fail = (not scan.passed) or rec == "manual_review"
        if hard_fail or soft_fail:
            donation.ngo_queue = []
            donation.notified_ngo_ids = []
            donation.current_radius_km = 0.0

        if hard_fail:
            donation.status = DonationStatus.needs_review
            donation.scan_phase_failures = max(donation.scan_phase_failures, 1)
        elif soft_fail:
            donation.status = DonationStatus.pending_scan_retry
            donation.scan_phase_failures = 1
        elif use_pubsub_pipeline:
            donation.status = DonationStatus.pending_match
        elif queue:
            donation.status = DonationStatus.notified
        else:
            donation.status = DonationStatus.pending_match

        matching_deferred = bool(use_pubsub_pipeline and donation.status == DonationStatus.pending_match)

        self.donations[donation.id] = donation
        self._write_doc("donations", donation.id, donation)
        self._persist_donation_scan_record(
            donation_id=donation.id,
            donor_id=donation.donor_id,
            scan=donation.scan,
            kind="donation_created",
        )
        self._sync_active_feed(donation)

        pub_body = {
            "event": "donation_created",
            "donation_id": donation.id,
            "donor_id": donation.donor_id,
            "food_type": donation.food_type,
            "quantity_kg": donation.quantity_kg,
            "lat": payload.location.lat if payload.location else donor.location.lat,
            "lng": payload.location.lng if payload.location else donor.location.lng,
            "timestamp": donation.created_at.isoformat(),
            "matching_deferred": matching_deferred,
        }
        self._publish_event("foodbridge-donations", pub_body)

        if hard_fail:
            self._create_donation_notifications(donation)
        elif soft_fail:
            self._notify_scan_retry_donor(donation)
        elif use_pubsub_pipeline:
            if settings.pubsub_matching_inline_completion:
                self.run_matching_for_donation(donation.id)
        else:
            self._create_donation_notifications(donation)
            if donation.status == DonationStatus.notified:
                from app.services.escalation_service import escalation_service

                escalation_service.schedule_escalation(donation)

        donation = self.donations[donation.id]
        log_event(
            event_type="donation_created",
            actor_id=donation.donor_id,
            donation_id=donation.id,
            status=donation.status.value,
            payload={"food_type": donation.food_type, "quantity_kg": donation.quantity_kg},
        )

        self._recompute_all_donor_scores()
        self._sync_entity_directory_feed()

        export_donation_ml_event(donation, "donation_created")

        return donation

    def _notify_scan_retry_donor(self, donation: Donation) -> None:
        self.create_notification(
            Notification(
                donation_id=donation.id,
                recipient_role=Role.donor,
                recipient_id=donation.donor_id,
                title="Photo or details need another try",
                body=(
                    f"Gemini could not confidently verify {donation.food_type}. "
                    "Update your listing or add a clearer photo, then tap Retry on the donate screen."
                ),
                channel="dashboard",
            )
        )

    def retry_donation_scan(self, donation_id: str, payload: DonationCreate, *, image_bytes: bytes | None = None) -> Donation:
        """Second scan attempt for `pending_scan_retry`. Further soft failure → Super Admin queue."""
        donation = self.donations.get(donation_id)
        if not donation:
            raise ValueError("Donation not found")
        if donation.status != DonationStatus.pending_scan_retry:
            raise ValueError("Donation is not awaiting scan retry")
        if payload.donor_id != donation.donor_id:
            raise ValueError("Donor mismatch")
        donor = self.donors[payload.donor_id]
        settings = get_settings()
        use_pubsub_pipeline = settings.pubsub_matching_enabled

        if image_bytes is not None:
            hint = payload.food_type or (payload.notes or "")[:200] or "mixed meals"
            scan = scan_food_multimodal(hint, payload.notes, image_bytes)
            items = payload.items or [
                DonationItem(
                    food_type=scan.detected_food_type or payload.food_type,
                    quantity_kg=payload.quantity_kg,
                    meal_count=payload.meal_count,
                )
            ]
        else:
            items = payload.items or [
                DonationItem(food_type=payload.food_type, quantity_kg=payload.quantity_kg, meal_count=payload.meal_count)
            ]
        total_qty = round(sum(item.quantity_kg for item in items), 2)
        total_meals = int(sum(item.meal_count for item in items))
        primary_food_type = items[0].food_type if items else payload.food_type
        photo_url = payload.photo_url
        if image_bytes is not None:
            photo_url = self.upload_image_to_gcp(image_bytes, f"{uuid4().hex}.jpg")
        payload = DonationCreate(
            **{
                **payload.model_dump(),
                "food_type": primary_food_type,
                "quantity_kg": total_qty,
                "meal_count": total_meals,
                "items": items,
                "photo_url": photo_url,
            }
        )
        if image_bytes is None:
            scan = scan_food(primary_food_type, payload.notes)

        queue = [] if use_pubsub_pipeline else self.rank_ngos(payload)

        donation.scan = scan
        weather = fetch_weather_at_listing(donor.location.lat, donor.location.lng)
        donation.weather_at_listing = weather
        listing_ts = datetime.now(timezone.utc)
        donation.accuracy = evaluate_donation_accuracy(
            scan,
            quantity_kg=payload.quantity_kg,
            notes=payload.notes,
            donor_trust_score=donor.score.trust_score if donor.score else None,
            donor_trust_tier=donor.score.trust_tier if donor.score else None,
            food_prepared_at=payload.food_prepared_at,
            storage_ambient_temp_c=payload.storage_ambient_temp_c,
            held_in_refrigeration=payload.held_in_refrigeration,
            operational_metrics_notes=payload.operational_metrics_notes,
            weather=weather,
            listing_created_at=listing_ts,
        )
        donation.items = list(payload.items)
        donation.food_type = primary_food_type
        donation.quantity_kg = total_qty
        donation.meal_count = total_meals
        donation.notes = payload.notes
        donation.food_prepared_at = payload.food_prepared_at
        donation.storage_ambient_temp_c = payload.storage_ambient_temp_c
        donation.held_in_refrigeration = payload.held_in_refrigeration
        donation.operational_metrics_notes = payload.operational_metrics_notes
        donation.photo_url = payload.photo_url
        donation.scan_contract_version = scan_phase2_contract_version(scan)

        rec = donation.accuracy.recommendation
        hard_fail = rec == "auto_reject"
        soft_fail = (not scan.passed) or rec == "manual_review"

        top_q = queue[0] if queue else None
        donation.expires_at = datetime.now(timezone.utc) + scaled_timedelta_minutes(scan.freshness_window_minutes)
        donation.current_radius_km = top_q.distance_km if top_q else 0.0

        if hard_fail:
            donation.status = DonationStatus.needs_review
            donation.scan_phase_failures = max(donation.scan_phase_failures, 2)
            donation.ngo_queue = []
            donation.notified_ngo_ids = []
        elif soft_fail:
            donation.status = DonationStatus.needs_review
            donation.scan_phase_failures = 2
            donation.ngo_queue = []
            donation.notified_ngo_ids = []
        elif use_pubsub_pipeline:
            donation.status = DonationStatus.pending_match
            donation.ngo_queue = []
            donation.notified_ngo_ids = []
        else:
            donation.ngo_queue = queue
            donation.notified_ngo_ids = [queue[0].ngo_id] if queue else []
            donation.status = DonationStatus.notified if queue else DonationStatus.pending_match
            wave_now = datetime.now(timezone.utc)
            donation.wave_started_at = wave_now
            donation.wave_expires_at = wave_now + scaled_timedelta_minutes(30)

        donation.updated_at = datetime.now(timezone.utc)
        self.donations[donation.id] = donation
        self._write_doc("donations", donation.id, donation)
        self._persist_donation_scan_record(
            donation_id=donation.id,
            donor_id=donation.donor_id,
            scan=donation.scan,
            kind="scan_retry",
        )
        self._sync_active_feed(donation)

        pub_body = {
            "event": "donation_retry_scan",
            "donation_id": donation.id,
            "donor_id": donation.donor_id,
            "food_type": donation.food_type,
            "status": donation.status.value,
            "matching_deferred": bool(use_pubsub_pipeline and donation.status == DonationStatus.pending_match),
            "timestamp": donation.updated_at.isoformat(),
        }
        self._publish_event("foodbridge-donations", pub_body)

        if hard_fail or soft_fail:
            self._create_donation_notifications(donation)
        elif use_pubsub_pipeline:
            if settings.pubsub_matching_inline_completion:
                self.run_matching_for_donation(donation.id)
        else:
            self._create_donation_notifications(donation)
            if donation.status == DonationStatus.notified:
                from app.services.escalation_service import escalation_service

                escalation_service.schedule_escalation(donation)

        self._recompute_all_donor_scores()
        self._sync_entity_directory_feed()
        log_event(
            event_type="donation_scan_retry",
            actor_id=donation.donor_id,
            donation_id=donation.id,
            status=donation.status.value,
            payload={"food_type": donation.food_type, "scan_phase_failures": donation.scan_phase_failures},
        )
        export_donation_ml_event(self.donations[donation.id], "donation_created")
        return self.donations[donation.id]

    def admin_resolve_scan_review(self, donation_id: str, *, approved: bool) -> Donation:
        """Super Admin: approve routes to NGOs; reject marks wasted."""
        donation = self.donations.get(donation_id)
        if not donation:
            raise ValueError("Donation not found")
        if donation.status != DonationStatus.needs_review:
            raise ValueError("Donation is not in manual review")

        if not approved:
            donation.status = DonationStatus.wasted
            donation.updated_at = datetime.now(timezone.utc)
            self.donations[donation.id] = donation
            self._write_doc("donations", donation.id, donation)
            self._sync_active_feed(donation)
            self.create_notification(
                Notification(
                    donation_id=donation.id,
                    recipient_role=Role.donor,
                    recipient_id=donation.donor_id,
                    title="Listing not cleared",
                    body=f"Your {donation.food_type} donation was not released to NGOs after review.",
                    channel="dashboard",
                )
            )
            log_event(
                event_type="donation_admin_rejected",
                actor_id="super_admin",
                donation_id=donation.id,
                status=donation.status.value,
                payload={},
            )
            return donation

        settings = get_settings()
        use_pubsub_pipeline = settings.pubsub_matching_enabled
        payload = self._donation_to_create_payload(donation)
        queue = [] if use_pubsub_pipeline else self.rank_ngos(payload)
        donation.ngo_queue = queue
        top = queue[0] if queue else None
        donation.current_radius_km = top.distance_km if top else 0.0
        donation.notified_ngo_ids = [top.ngo_id] if top else []
        wave_now = datetime.now(timezone.utc)
        donation.wave_started_at = wave_now
        donation.wave_expires_at = wave_now + scaled_timedelta_minutes(30)
        donation.updated_at = wave_now

        if use_pubsub_pipeline:
            donation.status = DonationStatus.pending_match
        elif queue:
            donation.status = DonationStatus.notified
        else:
            donation.status = DonationStatus.pending_match

        self.donations[donation.id] = donation
        self._write_doc("donations", donation.id, donation)
        self._sync_active_feed(donation)

        if use_pubsub_pipeline:
            if settings.pubsub_matching_inline_completion:
                self.run_matching_for_donation(donation.id)
        else:
            self._create_donation_notifications(donation)
            if donation.status == DonationStatus.notified:
                from app.services.escalation_service import escalation_service

                escalation_service.schedule_escalation(donation)

        self.create_notification(
            Notification(
                donation_id=donation.id,
                recipient_role=Role.donor,
                recipient_id=donation.donor_id,
                title="Listing cleared",
                body=f"Super Admin approved your {donation.food_type} donation — NGOs can now respond.",
                channel="dashboard",
            )
        )
        log_event(
            event_type="donation_admin_approved",
            actor_id="super_admin",
            donation_id=donation.id,
            status=donation.status.value,
            payload={},
        )
        return self.donations[donation.id]

    def create_donor(self, payload: DonorCreate) -> Donor:
        if any(donor.fssai_license == payload.fssai_license for donor in self.donors.values()):
            raise ValueError("FSSAI license already registered")

        donor_id = f"donor_{slugify(payload.name)}"
        suffix = 2
        base_id = donor_id
        while donor_id in self.donors:
            donor_id = f"{base_id}_{suffix}"
            suffix += 1

        donor = Donor(
            id=donor_id,
            name=payload.name,
            area=payload.area,
            type=payload.type,
            fssai_license=payload.fssai_license,
            contact_name=payload.contact_name,
            phone=payload.phone,
            email=payload.email,
            avg_surplus_kg=payload.avg_surplus_kg,
            verification_status="verified",
            location=Location(
                area=payload.area,
                address=payload.address,
                lat=payload.lat,
                lng=payload.lng,
            ),
        )
        self.donors[donor.id] = donor
        self._recompute_all_donor_scores()
        self.users[donor.id] = UserProfile(
            id=donor.id,
            role=Role.donor,
            display_name=donor.name,
            status="verified",
            entity_id=donor.id,
            duplicate_flag=False,
        )
        self._write_doc("donors", donor.id, donor)
        self._write_doc("users", donor.id, self.users[donor.id])
        self._sync_entity_directory_feed()
        self.create_notification(
            Notification(
                recipient_role=Role.super_admin,
                recipient_id="super_admin",
                title="New donor registration",
                body=f"{donor.name} registered with FSSAI {donor.fssai_license}. Verify before pilot use.",
            )
        )
        return donor

    def create_ngo(self, payload: NgoCreate) -> Ngo:
        if any(ngo.ngo_darpan_id == payload.ngo_darpan_id for ngo in self.ngos.values()):
            raise ValueError("NGO Darpan ID already registered")

        ngo_id = f"ngo_{slugify(payload.name)}"
        suffix = 2
        base_id = ngo_id
        while ngo_id in self.ngos:
            ngo_id = f"{base_id}_{suffix}"
            suffix += 1

        ngo = Ngo(
            id=ngo_id,
            name=payload.name,
            area=payload.area,
            focus=payload.focus,
            ngo_darpan_id=payload.ngo_darpan_id,
            beneficiary_count=payload.beneficiary_count,
            food_preferences=payload.food_preferences,
            dietary_restrictions=payload.dietary_restrictions,
            location=Location(area=payload.area, address=payload.address, lat=payload.lat, lng=payload.lng),
            verification_status="pending",
            aadhaar_document_url=payload.aadhaar_document_url,
            meal_time_schedule=payload.meal_time_schedule,
            coordinator_name=payload.coordinator_name,
            coordinator_phone=payload.coordinator_phone,
        )
        self.ngos[ngo.id] = ngo
        self.users[ngo.id] = UserProfile(
            id=ngo.id,
            role=Role.ngo_coordinator,
            display_name=ngo.name,
            status="pending",
            entity_id=ngo.id,
            duplicate_flag=False,
        )
        self._write_doc("ngos", ngo.id, ngo)
        self._write_doc("users", ngo.id, self.users[ngo.id])
        self._sync_entity_directory_feed()
        self.create_notification(
            Notification(
                recipient_role=Role.super_admin,
                recipient_id="super_admin",
                title="NGO approval required",
                body=f"{ngo.name} submitted Darpan ID {ngo.ngo_darpan_id}. Review Aadhaar and beneficiary profile.",
            )
        )
        return ngo

    def verify_user(self, user_id: str, payload: UserVerifyUpdate) -> UserProfile:
        user = self.users[user_id]
        user.status = payload.status
        if user.role == Role.ngo_coordinator and user.entity_id and user.entity_id in self.ngos:
            ngo = self.ngos[user.entity_id]
            ngo.verification_status = "verified" if payload.status == "verified" else "suspended"
            self._write_doc("ngos", ngo.id, ngo)
            self.create_notification(
                Notification(
                    recipient_role=Role.ngo_coordinator,
                    recipient_id=ngo.id,
                    title="NGO verification updated",
                    body=f"Your FoodBridge account status is now {payload.status}.",
                )
            )
        self.users[user_id] = user
        self._write_doc("users", user.id, user)
        self._sync_entity_directory_feed()
        return user

    def invite_volunteer(self, payload: VolunteerInviteCreate) -> VolunteerProfile:
        if payload.ngo_id not in self.ngos:
            raise KeyError("NGO not found")
        if any(item.ngo_id == payload.ngo_id and item.phone == payload.phone for item in self.volunteers.values()):
            raise ValueError("Volunteer already invited for this NGO")
        import secrets
        from app.services.email_service import send_volunteer_invite_email

        volunteer = VolunteerProfile(
            ngo_id=payload.ngo_id,
            name=payload.name,
            phone=payload.phone,
            email=payload.email,
            invite_link="",
        )
        token = secrets.token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
        invite = VolunteerInviteToken(
            token=token,
            ngo_id=payload.ngo_id,
            ngo_name=self.ngos[payload.ngo_id].name,
            volunteer_id=volunteer.id,
            name=payload.name,
            email=payload.email or "",
            phone=payload.phone,
            expires_at=expires_at,
        )
        invite_link = f"{get_settings().frontend_base_url}/volunteer/register?token={token}"
        volunteer.invite_link = invite_link
        self.volunteers[volunteer.id] = volunteer
        self.volunteer_invites[token] = invite
        self.users[volunteer.id] = UserProfile(
            id=volunteer.id,
            role=Role.ngo_volunteer,
            display_name=volunteer.name,
            status="pending",
            entity_id=payload.ngo_id,
            email=payload.email,
        )
        self._write_doc("volunteers", volunteer.id, volunteer)
        self._write_doc("volunteer_invites", token, invite)
        self._write_doc("users", volunteer.id, self.users[volunteer.id])
        self._sync_entity_directory_feed()
        send_volunteer_invite_email(
            to_email=payload.email or "",
            volunteer_name=payload.name,
            ngo_name=self.ngos[payload.ngo_id].name,
            invite_link=invite_link,
        )
        log_event(
            event_type="volunteer_invited",
            actor_id=payload.ngo_id,
            payload={
                "volunteer_id": volunteer.id,
                "email": volunteer.email,
                "invite_token": token,
            },
        )
        return volunteer

    def get_volunteer_invite(self, token: str) -> VolunteerInviteToken | None:
        invite = self.volunteer_invites.get(token)
        if not invite:
            db = self._firestore()
            if db:
                doc = db.collection("volunteer_invites").document(token).get()
                if doc.exists:
                    invite = VolunteerInviteToken(**doc.to_dict())
                    self.volunteer_invites[token] = invite
        return invite

    def _revoke_open_invites(self, volunteer_id: str) -> None:
        now = datetime.now(timezone.utc)
        for token, invite in list(self.volunteer_invites.items()):
            if invite.volunteer_id != volunteer_id:
                continue
            if invite.used or invite.revoked:
                continue
            invite.revoked = True
            invite.revoked_at = now
            self.volunteer_invites[token] = invite
            self._write_doc("volunteer_invites", token, invite)

    def activate_volunteer_from_invite(self, token: str, uid: str, email: str) -> VolunteerProfile:
        invite = self.get_volunteer_invite(token)
        if not invite:
            raise ValueError("Invite not found")
        if invite.used:
            raise ValueError("Invite already used")
        if invite.revoked:
            raise ValueError("Invite revoked")
        if invite.expires_at < datetime.now(timezone.utc):
            raise ValueError("Invite expired")
        if invite.email and invite.email.lower() != (email or "").lower():
            raise ValueError("Invite email mismatch")

        volunteer = self.volunteers.get(invite.volunteer_id)
        if not volunteer:
            raise ValueError("Volunteer profile missing")
        volunteer.status = "pending_approval"
        volunteer.registered_uid = uid
        self.volunteers[volunteer.id] = volunteer
        self._write_doc("volunteers", volunteer.id, volunteer)

        self.users[uid] = UserProfile(
            id=uid,
            role=Role.ngo_volunteer,
            display_name=volunteer.name,
            status="pending",
            entity_id=volunteer.ngo_id,
            email=email,
        )
        self._write_doc("users", uid, self.users[uid])

        invite.used = True
        invite.used_by_uid = uid
        self.volunteer_invites[token] = invite
        self._write_doc("volunteer_invites", token, invite)
        self._sync_entity_directory_feed()
        log_event(
            event_type="volunteer_registered_from_invite",
            actor_id=uid,
            payload={"volunteer_id": volunteer.id, "invite_token": token},
        )
        return volunteer

    def set_volunteer_approval(self, volunteer_id: str, ngo_id: str, approved: bool) -> VolunteerProfile:
        volunteer = self.volunteers.get(volunteer_id)
        if not volunteer:
            raise ValueError("Volunteer not found")
        if volunteer.ngo_id != ngo_id:
            raise ValueError("Volunteer does not belong to this NGO")
        volunteer.status = "active" if approved else "rejected"
        self.volunteers[volunteer.id] = volunteer
        self._write_doc("volunteers", volunteer.id, volunteer)
        self._sync_entity_directory_feed()
        log_event(
            event_type="volunteer_approval_updated",
            actor_id=ngo_id,
            payload={"volunteer_id": volunteer.id, "approved": approved, "status": volunteer.status},
        )
        return volunteer

    def resend_volunteer_invite(self, volunteer_id: str, ngo_id: str) -> VolunteerProfile:
        volunteer = self.volunteers.get(volunteer_id)
        if not volunteer:
            raise ValueError("Volunteer not found")
        if volunteer.ngo_id != ngo_id:
            raise ValueError("Volunteer does not belong to this NGO")
        if volunteer.status in {"active", "rejected"}:
            raise ValueError(f"Cannot resend invite for {volunteer.status} volunteer")

        self._revoke_open_invites(volunteer_id)

        import secrets
        from app.services.email_service import send_volunteer_invite_email

        token = secrets.token_urlsafe(24)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
        invite = VolunteerInviteToken(
            token=token,
            ngo_id=ngo_id,
            ngo_name=self.ngos[ngo_id].name,
            volunteer_id=volunteer.id,
            name=volunteer.name,
            email=volunteer.email or "",
            phone=volunteer.phone,
            expires_at=expires_at,
        )
        invite_link = f"{get_settings().frontend_base_url}/volunteer/register?token={token}"
        volunteer.invite_link = invite_link
        self.volunteers[volunteer.id] = volunteer
        self.volunteer_invites[token] = invite
        self._write_doc("volunteers", volunteer.id, volunteer)
        self._write_doc("volunteer_invites", token, invite)
        self._sync_entity_directory_feed()

        send_volunteer_invite_email(
            to_email=volunteer.email or "",
            volunteer_name=volunteer.name,
            ngo_name=self.ngos[ngo_id].name,
            invite_link=invite_link,
        )
        log_event(
            event_type="volunteer_invite_resent",
            actor_id=ngo_id,
            payload={"volunteer_id": volunteer.id, "invite_token": token},
        )
        return volunteer

    def revoke_volunteer_invite(self, volunteer_id: str, ngo_id: str) -> VolunteerProfile:
        volunteer = self.volunteers.get(volunteer_id)
        if not volunteer:
            raise ValueError("Volunteer not found")
        if volunteer.ngo_id != ngo_id:
            raise ValueError("Volunteer does not belong to this NGO")
        if volunteer.status in {"active", "rejected"}:
            raise ValueError(f"Cannot revoke invite for {volunteer.status} volunteer")
        self._revoke_open_invites(volunteer_id)
        volunteer.status = "rejected"
        self.volunteers[volunteer.id] = volunteer
        self._write_doc("volunteers", volunteer.id, volunteer)
        self._sync_entity_directory_feed()
        log_event(
            event_type="volunteer_invite_revoked",
            actor_id=ngo_id,
            payload={"volunteer_id": volunteer.id},
        )
        return volunteer

    def verify_auth(self, role: Role | None = None, profile_id: str | None = None):
        if profile_id and profile_id in self.users:
            user = self.users[profile_id]
        else:
            # If user not in DB, create a temporary one for the session
            selected_role = role or Role.donor
            user = UserProfile(
                id=profile_id or "anonymous",
                role=selected_role,
                display_name=f"User {selected_role.value}",
                status="active" if selected_role != Role.ngo_coordinator else "pending",
            )
            if profile_id:
                self.users[profile_id] = user

        redirect_map = {
            Role.super_admin: "/admin",
            Role.municipal_admin: "/municipal",
            Role.donor: "/donor",
            Role.ngo_coordinator: "/ngo",
            Role.ngo_volunteer: "/volunteer",
        }
        profile = None
        if user.role == Role.donor and user.entity_id:
            profile = self.donors.get(user.entity_id)
        elif user.role == Role.ngo_coordinator and user.entity_id:
            profile = self.ngos.get(user.entity_id)
            
        return user, profile, redirect_map[user.role]

    def update_donor_telegram(self, donor_id: str, payload: DonorTelegramUpdate) -> Donor:
        donor = self.donors[donor_id]
        donor.telegram_enabled = payload.enabled
        donor.telegram_chat_id = payload.telegram_chat_id
        donor.telegram_username = payload.telegram_username
        self.donors[donor_id] = donor
        self._write_doc("donors", donor.id, donor)

        if payload.enabled:
            self.link_telegram_donor(
                TelegramLinkRequest(chat_id=payload.telegram_chat_id, fssai_license=donor.fssai_license)
            )
            self.create_notification(
                Notification(
                    recipient_role=Role.donor,
                    recipient_id=donor.id,
                    title="Telegram intake enabled",
                    body="Restaurant staff can now send food photos and captions through Telegram after the /link step.",
                    channel="telegram",
                )
            )

        return donor

    def _create_donation_notifications(self, donation: Donation) -> None:
        if donation.status == DonationStatus.needs_review:
            self.create_notification(
                Notification(
                    donation_id=donation.id,
                    recipient_role=Role.super_admin,
                    recipient_id="super_admin",
                    title="Photo review needed",
                    body=f"{donation.donor_name} needs manual review for {donation.food_type}.",
                )
            )
            return

        if donation.ngo_queue:
            top = donation.ngo_queue[0]
            self.create_notification(
                Notification(
                    donation_id=donation.id,
                    recipient_role=Role.ngo_coordinator,
                    recipient_id=top.ngo_id,
                    title="New surplus donation nearby",
                    body=f"{donation.donor_name} posted {donation.quantity_kg:g} kg {donation.food_type}. Match score {top.total_score}.",
                    channel="fcm",
                )
            )

        self.create_notification(
            Notification(
                donation_id=donation.id,
                recipient_role=Role.super_admin,
                recipient_id="super_admin",
                title="New donation created",
                body=f"{donation.donor_name} posted {donation.quantity_kg:g} kg {donation.food_type}. Top NGO notified: {donation.notified_ngo_ids[0] if donation.notified_ngo_ids else 'none'}.",
            )
        )

        self.create_notification(
            Notification(
                donation_id=donation.id,
                recipient_role=Role.donor,
                recipient_id=donation.donor_id,
                title="Donation scan complete",
                body=f"Gemini approved {donation.food_type} and notified the top NGO queue.",
            )
        )

    def update_donation_status(self, donation_id: str, payload: DonationStatusUpdate) -> Donation:
        donation = self.donations[donation_id]
        previous_status = donation.status
        donation.status = payload.status
        donation.updated_at = datetime.now(timezone.utc)

        if payload.ngo_id:
            ngo = self.ngos[payload.ngo_id]
            donation.assigned_ngo_id = ngo.id
            donation.assigned_ngo_name = ngo.name

        if payload.volunteer_uid:
            donation.volunteer_uid = payload.volunteer_uid

        if payload.volunteer_name:
            donation.volunteer_name = payload.volunteer_name

        if payload.status == DonationStatus.accepted:
            if donation.accepted_at is None:
                donation.accepted_at = donation.updated_at
                donation.acceptance_seconds = int((donation.accepted_at - donation.created_at).total_seconds())
            donation.volunteer_task_status = VolunteerTaskStatus.assigned
            donation.wave_expires_at = None
        if payload.status == DonationStatus.assigned and payload.buffer_minutes and payload.buffer_minutes > 0:
            donation.expires_at = donation.expires_at + scaled_timedelta_minutes(payload.buffer_minutes)
            donation.pickup_buffer_extensions = (donation.pickup_buffer_extensions or 0) + 1

        if payload.volunteer_task_status is not None:
            donation.volunteer_task_status = payload.volunteer_task_status
            if payload.volunteer_task_status == VolunteerTaskStatus.heading_to_pickup and donation.heading_started_at is None:
                donation.heading_started_at = donation.updated_at
                donation.delivery_started_at = donation.updated_at
            if payload.volunteer_task_status == VolunteerTaskStatus.pickup_rejected:
                donation.volunteer_reject_reason = payload.reject_reason or payload.notes
            if payload.volunteer_task_status == VolunteerTaskStatus.reached_pickup:
                donation.pickup_reached_at = donation.updated_at
            if payload.volunteer_task_status == VolunteerTaskStatus.pickup_successful:
                donation.pickup_completed_at = donation.updated_at
                if payload.received_food_type:
                    donation.food_type = payload.received_food_type
                if payload.received_quantity_kg:
                    donation.quantity_kg = payload.received_quantity_kg
                if payload.received_meal_count:
                    donation.meal_count = payload.received_meal_count
                donation.volunteer_pickup_notes = payload.notes
            if payload.volunteer_task_status == VolunteerTaskStatus.enroute_to_ngo:
                if donation.delivery_started_at is None:
                    donation.delivery_started_at = donation.updated_at
            if payload.volunteer_task_status == VolunteerTaskStatus.delivered_pending_confirmation:
                donation.delivery_marked_at = donation.updated_at
                if donation.heading_started_at:
                    donation.volunteer_total_seconds = int((donation.delivery_marked_at - donation.heading_started_at).total_seconds())
            if payload.volunteer_task_status == VolunteerTaskStatus.delivered_confirmed:
                donation.delivery_confirmed_at = donation.updated_at

        if payload.status == DonationStatus.completed:
            donation.completed_meals_served = payload.meals_served or donation.meal_count
            donation.pickup_photo_url = payload.pickup_photo_url
            if donation.completed_at is None:
                donation.completed_at = donation.updated_at
            if donation.accepted_at:
                donation.delivery_seconds = int((donation.completed_at - donation.accepted_at).total_seconds())
            else:
                donation.delivery_seconds = int((donation.completed_at - donation.created_at).total_seconds())
            if donation.volunteer_task_status is None:
                donation.volunteer_task_status = VolunteerTaskStatus.delivered_confirmed

        self._write_doc("donations", donation.id, donation)
        self._recompute_all_donor_scores()
        self._sync_entity_directory_feed()
        self._sync_active_feed(donation)
        self._create_status_communication(donation, payload)

        if payload.status == DonationStatus.declined:
            from app.services.escalation_service import escalation_service
            escalation_service.handle_ngo_decline(donation_id, payload.ngo_id or "")

        log_event(
            event_type="donation_status_updated",
            actor_id=payload.volunteer_uid or payload.ngo_id or donation.donor_id,
            donation_id=donation.id,
            status=donation.status.value,
            payload={
                "volunteer_uid": payload.volunteer_uid,
                "volunteer_name": payload.volunteer_name,
                "meals_served": payload.meals_served,
                "previous_status": previous_status.value,
                "buffer_minutes": payload.buffer_minutes,
                "volunteer_task_status": payload.volunteer_task_status.value if payload.volunteer_task_status else None,
                "reject_reason": payload.reject_reason,
            },
        )
        self._publish_event(
            "foodbridge-donations",
            {
                "event": "donation_status_updated",
                "donation_id": donation.id,
                "status": donation.status.value,
                "volunteer_task_status": donation.volunteer_task_status.value if donation.volunteer_task_status else None,
                "updated_at": donation.updated_at.isoformat(),
            },
        )

        export_donation_ml_event(donation, "status_updated", previous_status=previous_status.value)
        if donation.status.value in terminal_statuses() and previous_status.value not in terminal_statuses():
            export_donation_ml_event(
                donation,
                "terminal",
                previous_status=previous_status.value,
                terminal_label=donation.status.value,
            )

        return donation

    def _create_status_communication(self, donation: Donation, payload: DonationStatusUpdate) -> None:
        if payload.status == DonationStatus.accepted and donation.assigned_ngo_id:
            self.create_message(
                CommunicationMessageCreate(
                    donation_id=donation.id,
                    sender_role=Role.ngo_coordinator,
                    sender_id=donation.assigned_ngo_id,
                    recipient_role=Role.donor,
                    recipient_id=donation.donor_id,
                    body=f"{donation.assigned_ngo_name} accepted the pickup. Please keep {donation.food_type} sealed and ready.",
                )
            )
            self.create_notification(
                Notification(
                    donation_id=donation.id,
                    recipient_role=Role.donor,
                    recipient_id=donation.donor_id,
                    title="NGO accepted pickup",
                    body=f"{donation.assigned_ngo_name} accepted {donation.food_type}.",
                )
            )

        if payload.status == DonationStatus.completed:
            self.create_message(
                CommunicationMessageCreate(
                    donation_id=donation.id,
                    sender_role=Role.ngo_volunteer,
                    sender_id=payload.volunteer_name or "volunteer",
                    recipient_role=Role.donor,
                    recipient_id=donation.donor_id,
                    body=f"Pickup completed. Meals served logged: {donation.completed_meals_served or donation.meal_count}.",
                )
            )

    def create_emergency_request(self, payload: EmergencyRequestCreate) -> EmergencyRequest:
        ngo = self.ngos[payload.ngo_id]
        from app.services.emergency_pledge_vertex import select_emergency_donors_and_pledge_copy

        donor_ids, pledge_copy = select_emergency_donors_and_pledge_copy(
            payload=payload,
            ngo=ngo,
            donors=self.donors,
            donations=list(self.donations.values()),
        )
        request = EmergencyRequest(
            ngo_id=ngo.id,
            ngo_name=ngo.name,
            food_type=payload.food_type,
            quantity_goal_kg=payload.quantity_goal_kg,
            reason=payload.reason,
            urgency_level=payload.urgency_level,
            beneficiary_count=payload.beneficiary_count,
            required_by_meal_time=payload.required_by_meal_time,
            contact_phone=payload.contact_phone,
            pickup_address=payload.pickup_address,
            min_contribution_kg=payload.min_contribution_kg,
            max_contribution_kg=payload.max_contribution_kg,
            donor_targets=donor_ids,
            deadline_at=datetime.now(timezone.utc) + scaled_timedelta_minutes(payload.deadline_minutes),
            popup_expires_at=datetime.now(timezone.utc) + scaled_timedelta_minutes(payload.deadline_minutes),
            notes=payload.notes,
        )
        request.pledged_kg = 0
        request.updated_at = datetime.now(timezone.utc)
        self.emergency_requests[request.id] = request
        self._write_doc(EMERGENCY_REQUESTS_COLLECTION, request.id, request)
        self._sync_emergency_feed(request)
        for donor_id in request.donor_targets:
            title, body = pledge_copy.get(donor_id) or (
                f"Emergency pledge · {request.ngo_name}",
                f"{request.ngo_name} needs ~{request.quantity_goal_kg:g} kg {request.food_type}. {request.reason[:120]}",
            )
            self.create_notification(
                Notification(
                    recipient_role=Role.donor,
                    recipient_id=donor_id,
                    title=title,
                    body=body,
                    channel="fcm",
                )
            )

        self._publish_event("foodbridge-emergencies", {
            "event": "emergency_created",
            "emergency_id": request.id,
            "ngo_id": request.ngo_id,
            "food_type": request.food_type,
            "quantity_goal_kg": request.quantity_goal_kg,
            "lat": ngo.location.lat,
            "lng": ngo.location.lng,
            "timestamp": request.created_at.isoformat()
        })
        log_event(
            event_type="emergency_request_created",
            actor_id=request.ngo_id,
            status=request.status,
            payload={"food_type": request.food_type, "quantity_goal_kg": request.quantity_goal_kg},
        )

        return request

    def contribute_emergency_pool(self, request_id: str, payload: EmergencyContributionCreate) -> EmergencyRequest:
        if request_id not in self.emergency_requests:
            raise KeyError("Emergency request not found")
        request = self.emergency_requests[request_id]
        if request.status in {"cancelled", "fulfilled"} or not request.pool_open:
            raise ValueError("Emergency pool is closed")
        if payload.donor_id not in self.donors:
            raise KeyError("Donor not found")
        donor = self.donors[payload.donor_id]
        ngo = self.ngos.get(request.ngo_id)
        if ngo is None:
            raise KeyError("NGO not found")

        if payload.quantity_kg < (request.min_contribution_kg or 0):
            raise ValueError(f"Minimum contribution is {request.min_contribution_kg} kg")
        if request.max_contribution_kg and payload.quantity_kg > request.max_contribution_kg:
            raise ValueError(f"Maximum contribution is {request.max_contribution_kg} kg")

        contribution = EmergencyContribution(
            donor_id=donor.id,
            donor_name=donor.name,
            quantity_kg=payload.quantity_kg,
            distance_km=distance_km(
                donor.location.lat,
                donor.location.lng,
                ngo.location.lat,
                ngo.location.lng,
            ),
        )
        request.contributions.append(contribution)

        # Conflict-safe ordering strategy: nearest donor contributions are accepted first.
        ordered = sorted(
            request.contributions,
            key=lambda item: (item.distance_km, item.created_at),
        )
        total = 0.0
        for item in ordered:
            if total + item.quantity_kg <= request.quantity_goal_kg:
                item.accepted = True
                total += item.quantity_kg
            else:
                item.accepted = False

        request.pledged_kg = round(total, 2)
        if request.pledged_kg >= request.quantity_goal_kg:
            request.status = "fulfilled"
            request.pool_open = False
            request.popup_active = False
        elif request.pledged_kg > 0:
            request.status = "partial_accepted"
        else:
            request.status = "open"
        request.updated_at = datetime.now(timezone.utc)

        self.emergency_requests[request.id] = request
        self._write_doc(EMERGENCY_REQUESTS_COLLECTION, request.id, request)
        self._sync_emergency_feed(request)
        self._publish_event(
            "foodbridge-emergencies",
            {
                "event": "emergency_pool_updated",
                "emergency_id": request.id,
                "ngo_id": request.ngo_id,
                "pledged_kg": request.pledged_kg,
                "quantity_goal_kg": request.quantity_goal_kg,
                "status": request.status,
                "pool_open": request.pool_open,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        log_event(
            event_type="emergency_pool_contribution",
            actor_id=donor.id,
            status=request.status,
            payload={
                "request_id": request.id,
                "quantity_kg": payload.quantity_kg,
                "accepted": any(
                    c.donor_id == donor.id
                    and c.quantity_kg == payload.quantity_kg
                    and c.created_at == contribution.created_at
                    and c.accepted
                    for c in request.contributions
                ),
            },
        )
        return request

    def resolve_emergency_request(
        self,
        request_id: str,
        actor_id: str,
        payload: EmergencyResolveRequest,
    ) -> EmergencyRequest:
        request = self.emergency_requests.get(request_id)
        if not request:
            raise KeyError("Emergency request not found")
        if not request.pool_open and request.status in {"fulfilled", "cancelled", "partial_accepted"}:
            return request

        now = datetime.now(timezone.utc)
        if payload.action == "accept_partial":
            if request.pledged_kg <= 0:
                raise ValueError("Cannot accept partial when pledged amount is zero")
            request.status = "partial_accepted"
            request.pool_open = False
            request.popup_active = False
            event_type = "emergency_resolved_partial"
        elif payload.action == "cancel":
            request.status = "cancelled"
            request.pool_open = False
            request.popup_active = False
            event_type = "emergency_cancelled"
        else:
            raise ValueError("Unsupported resolve action")

        request.updated_at = now
        self.emergency_requests[request.id] = request
        self._write_doc("emergency_requests", request.id, request)
        self._sync_emergency_feed(request)
        self._publish_event(
            "foodbridge-emergencies",
            {
                "event": event_type,
                "emergency_id": request.id,
                "ngo_id": request.ngo_id,
                "status": request.status,
                "pledged_kg": request.pledged_kg,
                "quantity_goal_kg": request.quantity_goal_kg,
                "reason": payload.reason,
                "actor_id": actor_id,
                "updated_at": request.updated_at.isoformat(),
            },
        )
        log_event(
            event_type=event_type,
            actor_id=actor_id,
            status=request.status,
            payload={
                "request_id": request.id,
                "pledged_kg": request.pledged_kg,
                "quantity_goal_kg": request.quantity_goal_kg,
                "reason": payload.reason,
            },
        )
        return request

    def process_due_emergency_requests(self) -> int:
        now = datetime.now(timezone.utc)
        processed = 0
        for request in list(self.emergency_requests.values()):
            if not request.pool_open:
                continue
            if request.deadline_at > now:
                continue
            request.pool_open = False
            request.popup_active = False
            if request.pledged_kg > 0:
                request.status = "partial_accepted"
                event_type = "emergency_auto_resolved_partial"
            else:
                request.status = "cancelled"
                event_type = "emergency_auto_cancelled_deadline"
            request.updated_at = now
            self.emergency_requests[request.id] = request
            self._write_doc("emergency_requests", request.id, request)
            self._sync_emergency_feed(request)
            self._publish_event(
                "foodbridge-emergencies",
                {
                    "event": event_type,
                    "emergency_id": request.id,
                    "ngo_id": request.ngo_id,
                    "status": request.status,
                    "pledged_kg": request.pledged_kg,
                    "quantity_goal_kg": request.quantity_goal_kg,
                    "updated_at": request.updated_at.isoformat(),
                },
            )
            log_event(
                event_type=event_type,
                actor_id=request.ngo_id,
                status=request.status,
                payload={
                    "request_id": request.id,
                    "pledged_kg": request.pledged_kg,
                    "quantity_goal_kg": request.quantity_goal_kg,
                },
            )
            processed += 1
        return processed

    def create_notification(self, notification: Notification) -> Notification:
        self.notifications[notification.id] = notification
        self._write_doc("notifications", notification.id, notification)
        return notification

    def list_notifications(self, recipient_id: str | None = None) -> list[Notification]:
        notifications = list(self.notifications.values())
        if recipient_id:
            notifications = [item for item in notifications if item.recipient_id == recipient_id]
        return sorted(notifications, key=lambda item: item.created_at, reverse=True)

    def create_message(self, payload: CommunicationMessageCreate) -> CommunicationMessage:
        message = CommunicationMessage(**payload.model_dump())
        self.messages[message.id] = message
        self._write_doc("messages", message.id, message)
        return message

    def list_messages(self, donation_id: str | None = None) -> list[CommunicationMessage]:
        messages = list(self.messages.values())
        if donation_id:
            messages = [item for item in messages if item.donation_id == donation_id]
        return sorted(messages, key=lambda item: item.created_at)

    def link_telegram_donor(self, payload: TelegramLinkRequest) -> TelegramLink:
        donor = next(
            (item for item in self.donors.values() if item.fssai_license == payload.fssai_license),
            None,
        )
        if donor is None:
            raise KeyError("No donor found for FSSAI license")
        link = TelegramLink(
            chat_id=payload.chat_id,
            donor_id=donor.id,
            donor_name=donor.name,
            fssai_license=payload.fssai_license,
        )
        self.telegram_links[payload.chat_id] = link
        self._write_doc("telegram_links", payload.chat_id, link)
        return link

    def create_linking_token(self, chat_id: str, chat_title: str | None = None) -> str:
        import random
        import string
        token = "FB-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        linking_token = TelegramLinkingToken(
            token=token,
            chat_id=chat_id,
            chat_title=chat_title
        )
        self.linking_tokens[token] = linking_token
        self._write_doc("telegram_linking_tokens", token, linking_token)
        return token

    def activate_telegram_link(self, donor_id: str, token: str) -> Donor:
        token_data = self.linking_tokens.get(token)
        
        # Fallback to Firestore if not in memory
        if not token_data:
            db = self._firestore()
            if db:
                doc = db.collection("telegram_linking_tokens").document(token).get()
                if doc.exists:
                    token_data = TelegramLinkingToken(**doc.to_dict())
        
        if not token_data:
            raise ValueError("Invalid or expired token")
        
        if token_data.expires_at < datetime.now(timezone.utc):
            raise ValueError("Token has expired")
            
        donor = self.donors.get(donor_id)
        if not donor:
            raise KeyError("Donor not found")
            
        donor.telegram_enabled = True
        donor.telegram_chat_id = token_data.chat_id
        donor.telegram_username = token_data.chat_title or "Telegram User"
        
        self.donors[donor_id] = donor
        self._write_doc("donors", donor.id, donor)
        
        # Also create the TelegramLink record
        link = TelegramLink(
            chat_id=token_data.chat_id,
            donor_id=donor.id,
            donor_name=donor.name,
            fssai_license=donor.fssai_license
        )
        self.telegram_links[token_data.chat_id] = link
        self._write_doc("telegram_links", token_data.chat_id, link)
        
        # Cleanup token
        if token in self.linking_tokens:
            del self.linking_tokens[token]
        db = self._firestore()
        if db:
            db.collection("telegram_linking_tokens").document(token).delete()
            
        return donor

    def create_auth_state(self, donor_id: str) -> str:
        import uuid
        state_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        auth_state = TelegramAuthState(
            state_token=state_token,
            donor_id=donor_id,
            expires_at=expires_at
        )
        self.auth_states[state_token] = auth_state
        self._write_doc("auth_states", state_token, auth_state)
        return state_token

    def get_auth_state(self, state_token: str) -> TelegramAuthState | None:
        state = self.auth_states.get(state_token)
        if not state:
            db = self._firestore()
            if db:
                doc = db.collection("auth_states").document(state_token).get()
                if doc.exists:
                    state = TelegramAuthState(**doc.to_dict())
        return state

    def update_auth_state(self, state_token: str, **kwargs) -> TelegramAuthState:
        state = self.get_auth_state(state_token)
        if not state:
            raise ValueError("Auth state not found")
        
        updated_data = state.model_dump()
        updated_data.update(kwargs)
        new_state = TelegramAuthState(**updated_data)
        self.auth_states[state_token] = new_state
        self._write_doc("auth_states", state_token, new_state)
        return new_state

    def register_slave_bot(self, slave_bot: SlaveBot):
        self.slave_bots[slave_bot.donor_id] = slave_bot
        self._write_doc("slave_bots", slave_bot.donor_id, slave_bot)
        
        # Also update telegram_sessions (linked in donor profile or separate collection)
        donor = self.donors.get(slave_bot.donor_id)
        if donor:
            donor.telegram_username = slave_bot.bot_username
            donor.telegram_enabled = True
            self.donors[donor.id] = donor
            self._write_doc("donors", donor.id, donor)

    def get_slave_bot(self, donor_id: str) -> SlaveBot | None:
        bot = self.slave_bots.get(donor_id)
        if not bot:
            db = self._firestore()
            if db:
                doc = db.collection("slave_bots").document(donor_id).get()
                if doc.exists:
                    bot = SlaveBot(**doc.to_dict())
        return bot

    def get_conversation_state(self, chat_id: str) -> ConversationState | None:
        state = self.conversation_states.get(chat_id)
        if not state:
            db = self._firestore()
            if db:
                doc = db.collection("conversation_states").document(chat_id).get()
                if doc.exists:
                    state = ConversationState(**doc.to_dict())
        return state

    def update_conversation_state(self, chat_id: str, **kwargs) -> ConversationState:
        state = self.get_conversation_state(chat_id)
        if not state:
            # Create new if not exists
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
            state = ConversationState(chat_id=chat_id, step=ConversationStep.idle, expires_at=expires_at)
        
        updated_data = state.model_dump()
        updated_data.update(kwargs)
        # Update expiry on interaction
        updated_data["expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=15)
        
        new_state = ConversationState(**updated_data)
        self.conversation_states[chat_id] = new_state
        self._write_doc("conversation_states", chat_id, new_state)
        return new_state

    def clear_conversation_state(self, chat_id: str):
        if chat_id in self.conversation_states:
            del self.conversation_states[chat_id]
        db = self._firestore()
        if db:
            db.collection("conversation_states").document(chat_id).delete()

    def donor_for_telegram_chat(self, chat_id: str | None):
        if chat_id and chat_id in self.telegram_links:
            return self.donors[self.telegram_links[chat_id].donor_id]
        return next(iter(self.donors.values()))

    def create_telegram_donation(self, chat_id: str | None, caption: str, photo_url: str | None = None) -> TelegramDonationResult:
        donor = self.donor_for_telegram_chat(chat_id)
        food_type, quantity = parse_telegram_caption(caption)
        if not food_type or quantity <= 0:
            return TelegramDonationResult(
                ok=False,
                chat_id=chat_id,
                donor_id=donor.id,
                reply="Please send a food photo with a caption like: biryani 18kg, dal 6kg.",
            )

        donation = self.create_donation(
            DonationCreate(
                donor_id=donor.id,
                food_type=food_type,
                quantity_kg=quantity,
                meal_count=max(1, round(quantity * 5)),
                photo_url=photo_url,
                notes=caption,
                source="telegram",
                telegram_chat_id=chat_id,
            )
        )
        return TelegramDonationResult(
            ok=True,
            chat_id=chat_id,
            donor_id=donor.id,
            donation_id=donation.id,
            parsed_food_type=food_type,
            quantity_kg=quantity,
            reply=f"Donation created for {quantity:g} kg {food_type}. Gemini scan passed and the top NGO has been notified.",
        )

    def predictions(self) -> list[Prediction]:
        from app.services.surplus_prediction_service import compute_surplus_predictions

        return compute_surplus_predictions(self)

    def impact(self) -> ImpactStats:
        completed = [item for item in self.donations.values() if item.status == DonationStatus.completed]
        active = [
            item
            for item in self.donations.values()
            if item.status
            not in {
                DonationStatus.completed,
                DonationStatus.expired,
                DonationStatus.declined,
                DonationStatus.wasted,
            }
        ]
        meals = sum(item.completed_meals_served or item.meal_count or 0 for item in completed)
        kg_saved = sum(item.quantity_kg for item in completed)
        return ImpactStats(
            meals_served=meals,
            kg_saved=round(kg_saved, 1),
            co2_offset_kg=round(kg_saved * 0.61, 1),
            active_donations=len(active),
            completed_donations=len(completed),
        )


store = DemoStore()


def parse_telegram_caption(caption: str) -> tuple[str | None, float]:
    cleaned = caption.strip().lower()
    if not cleaned:
        return None, 0

    match = re.search(r"([a-zA-Z\u0900-\u097F\u0C00-\u0C7F ]+?)\s*(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilogram|kilograms)", cleaned)
    if match:
        food_type = " ".join(match.group(1).replace(",", " ").split())
        return food_type, float(match.group(2))

    number = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if number:
        food_type = " ".join(cleaned[: number.start()].replace(",", " ").split()) or "mixed food"
        return food_type, float(number.group(1))

    return cleaned, 0


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "restaurant"
