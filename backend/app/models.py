from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.services.time_scale import scaled_timedelta_minutes


class Role(str, Enum):
    super_admin = "super_admin"
    municipal_admin = "municipal_admin"
    donor = "donor"
    ngo_coordinator = "ngo_coordinator"
    ngo_volunteer = "ngo_volunteer"


class DonationStatus(str, Enum):
    draft = "draft"
    pending_match = "pending_match"
    pending_scan_retry = "pending_scan_retry"
    notified = "notified"
    accepted = "accepted"
    declined = "declined"
    assigned = "assigned"
    completed = "completed"
    expired = "expired"
    needs_review = "needs_review"
    escalated_radius_2 = "escalated_radius_2"
    escalated_radius_3 = "escalated_radius_3"
    wasted = "wasted"


class VolunteerTaskStatus(str, Enum):
    assigned = "assigned"
    heading_to_pickup = "heading_to_pickup"
    pickup_rejected = "pickup_rejected"
    reached_pickup = "reached_pickup"
    pickup_successful = "pickup_successful"
    enroute_to_ngo = "enroute_to_ngo"
    delivered_pending_confirmation = "delivered_pending_confirmation"
    delivered_confirmed = "delivered_confirmed"


class Location(BaseModel):
    area: str
    address: str
    lat: float
    lng: float


class WeatherSnapshot(BaseModel):
    """Current weather near the listing location (server-fetched from OpenWeatherMap when configured)."""

    fetched_at: datetime
    temp_c: float
    feels_like_c: float | None = None
    humidity_percent: int | None = None
    conditions: str | None = None
    wind_speed_m_s: float | None = None
    lat: float
    lon: float
    provider: str = "openweathermap"


class Donor(BaseModel):
    id: str
    name: str
    area: str
    type: str
    fssai_license: str
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    location: Location
    avg_surplus_kg: str
    monthly_meals: int = 0
    verification_status: Literal["pending", "verified", "suspended"] = "verified"
    telegram_enabled: bool = False
    telegram_chat_id: str | None = None
    telegram_username: str | None = None
    score: Optional["DonorScore"] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DonorScore(BaseModel):
    trust_score: int = Field(ge=0, le=100)
    trust_tier: Literal["bronze", "silver", "gold", "platinum"]
    factors: list[str] = Field(default_factory=list)
    model_id: str = "foodbridge-donor-score-v1"
    model_version: str = "1.0.0"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DonorCreate(BaseModel):
    name: str
    area: str
    type: str = "Restaurant"
    fssai_license: str
    contact_name: str
    phone: str
    email: str | None = None
    address: str
    lat: float = 17.385
    lng: float = 78.4867
    avg_surplus_kg: str = "10-25 kg/day"


class DonorTelegramUpdate(BaseModel):
    telegram_chat_id: str
    telegram_username: str | None = None
    enabled: bool = True


class Ngo(BaseModel):
    id: str
    name: str
    area: str
    focus: str
    ngo_darpan_id: str
    beneficiary_count: int
    food_preferences: list[str]
    dietary_restrictions: list[str] = Field(default_factory=list)
    location: Location
    verification_status: Literal["pending", "verified", "suspended"] = "verified"
    aadhaar_document_url: str | None = None
    meal_time_schedule: str | None = None
    coordinator_name: str | None = None
    coordinator_phone: str | None = None
    coordinator_email: str | None = None


class NgoCreate(BaseModel):
    name: str
    area: str
    focus: str = "Food redistribution"
    ngo_darpan_id: str
    beneficiary_count: int = Field(gt=0)
    food_preferences: list[str] = Field(default_factory=lambda: ["rice", "dal", "roti"])
    dietary_restrictions: list[str] = Field(default_factory=list)
    address: str
    lat: float = 17.385
    lng: float = 78.4867
    aadhaar_document_url: str | None = None
    meal_time_schedule: str | None = None
    coordinator_name: str
    coordinator_phone: str


class UserProfile(BaseModel):
    id: str
    role: Role
    display_name: str
    status: Literal["pending", "verified", "active", "rejected", "suspended"]
    entity_id: str | None = None
    email: str | None = None
    duplicate_flag: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuthVerifyResponse(BaseModel):
    role: Role
    profile: UserProfile | Donor | Ngo | None = None
    redirect_to: str


class UserVerifyUpdate(BaseModel):
    status: Literal["verified", "rejected", "suspended"]
    notes: str | None = None


class VolunteerInviteCreate(BaseModel):
    ngo_id: str
    name: str
    phone: str | None = None
    email: str | None = None


class VolunteerProfile(BaseModel):
    id: str = Field(default_factory=lambda: f"vol_{uuid4().hex[:10]}")
    ngo_id: str
    name: str
    phone: str | None = None
    email: str | None = None
    registered_uid: str | None = None
    role: Role = Role.ngo_volunteer
    status: Literal["invited", "pending_approval", "active", "rejected"] = "invited"
    invite_link: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GeminiScan(BaseModel):
    """Visual/text safety scan output (Vertex or bridged legacy path)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "passed": True,
                "confidence": 0.91,
                "reason": "Food appears suitable for redistribution.",
                "detected_food_type": "biryani",
                "freshness_window_minutes": 180,
                "model_id": "gemini-3-flash-preview",
                "model_version": "preview",
                "generated_at": "2026-05-09T12:00:00Z",
                "fallback_used": False,
            }
        }
    )

    passed: bool = Field(description="Whether the scan considers the donation acceptable for routing.")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence in `passed` / classification (0–1).")
    reason: str = Field(description="Human-readable rationale from the scan pipeline.")
    detected_food_type: str = Field(description="Normalized food label used for matching and timers.")
    freshness_window_minutes: int = Field(ge=1, description="Minutes until pickup must complete (drives `expires_at`).")
    model_id: str | None = Field(
        default=None,
        description="Vertex / scan model identifier. Null on pre–Phase-2 stored documents.",
    )
    model_version: str | None = Field(
        default=None,
        description="Model release or config version string. Null on legacy stored documents.",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this scan result was produced (ISO 8601).",
    )
    fallback_used: bool = Field(
        default=False,
        description="True if the response used a non-primary or offline fallback path.",
    )

    @field_validator("generated_at", mode="before")
    @classmethod
    def _coerce_missing_generated_at(cls, value: object) -> object:
        # Firestore sometimes stores explicit null; treat as "use default now".
        if value is None:
            return datetime.now(timezone.utc)
        return value


class AccuracyAssessment(BaseModel):
    """Second-stage accuracy / anomaly assessment on donation context (Phase 2 contract)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "score": 0.82,
                "band": "high",
                "anomaly_probability": 0.12,
                "recommendation": "approve_with_caution",
                "top_factors": ["short_freshness_window"],
                "explanation": "Accuracy band: high. Estimated anomaly probability: 12%.",
                "model_id": "foodbridge-accuracy-v1",
                "model_version": "1.0.0",
                "generated_at": "2026-05-09T12:00:05Z",
                "fallback_used": False,
            }
        }
    )

    score: float = Field(ge=0.0, le=1.0, description="Continuous accuracy score (0–1); multiply by 100 for UI percent.")
    band: Literal["low", "medium", "high"] = Field(description="Discretized confidence band for routing policy.")
    anomaly_probability: float = Field(ge=0.0, le=1.0, description="Estimated probability of donation-data anomaly.")
    recommendation: Literal["auto_reject", "manual_review", "approve_with_caution", "approve"] = Field(
        description="Suggested handling before NGO acceptance."
    )
    top_factors: list[str] = Field(default_factory=list, description="Short factor codes / labels for explainability.")
    explanation: str = Field(default="", description="Plain-language explanation for dashboards and Telegram.")
    model_id: str = Field(description="Accuracy engine identifier.")
    model_version: str = Field(description="Accuracy engine version.")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this assessment was produced (ISO 8601).",
    )
    fallback_used: bool = Field(
        default=False,
        description="True if accuracy used degraded or deterministic fallback logic.",
    )

    @field_validator("generated_at", mode="before")
    @classmethod
    def _coerce_accuracy_generated_at(cls, value: object) -> object:
        if value is None:
            return datetime.now(timezone.utc)
        return value


class DonationScanRecord(BaseModel):
    """
    Append-only history of vision/safety scan outputs in Firestore collection `donation_scans`.
    The current scan remains embedded on `Donation.scan` for API responses; this table is for analytics and audit.
    """

    id: str = Field(default_factory=lambda: f"dscan_{uuid4().hex[:12]}")
    donation_id: str
    donor_id: str
    kind: Literal["donation_created", "scan_retry", "migrated_from_donation"] = "donation_created"
    scan: GeminiScan
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def scan_phase2_contract_version(scan: GeminiScan) -> Literal[1, 2]:
    """2 = scan carries Phase 2 model lineage (`model_id` + `model_version`)."""
    return 2 if (scan.model_id is not None and scan.model_version is not None) else 1


class MatchScore(BaseModel):
    ngo_id: str
    ngo_name: str
    distance_km: float
    total_score: int
    proximity_score: int
    food_type_score: int
    nutrition_score: int
    reason: str


class DonationItem(BaseModel):
    food_type: str
    quantity_kg: float = Field(gt=0)
    meal_count: int = Field(gt=0)
    condition: str | None = None


class DonationCreate(BaseModel):
    donor_id: str = "donor_paradise_jubilee"
    donor_name: str | None = None
    food_type: str
    quantity_kg: float = Field(gt=0)
    meal_count: int = Field(gt=0)
    items: list[DonationItem] = Field(default_factory=list)
    location: Location | None = None
    photo_url: str | None = None
    notes: str | None = None
    source: Literal["web", "telegram"] = "web"
    telegram_chat_id: str | None = None
    # Optional operational context — improves accuracy routing when present; omit when unavailable.
    food_prepared_at: datetime | None = None
    storage_ambient_temp_c: float | None = Field(
        default=None,
        description="Room or storage-area ambient temperature in °C, if known.",
    )
    held_in_refrigeration: bool | None = Field(
        default=None,
        description="True if surplus was held refrigerated; False if not; None if unknown.",
    )
    operational_metrics_notes: str | None = Field(
        default=None,
        description="Free-text kitchen/handling notes (e.g. blast chilled, held on counter).",
    )


class Donation(BaseModel):
    """
    Donation aggregate returned by the API. Phase 2 adds structured `scan` metadata, optional `accuracy`,
    and `scan_contract_version` for legacy vs full lineage (see `scan_phase2_contract_version`).
    """

    id: str = Field(default_factory=lambda: f"don_{uuid4().hex[:10]}")
    donor_id: str
    donor_name: str
    food_type: str
    quantity_kg: float
    meal_count: int
    items: list[DonationItem] = Field(default_factory=list)
    status: DonationStatus = DonationStatus.pending_match
    location: Location
    photo_url: str | None = None
    notes: str | None = None
    food_prepared_at: datetime | None = None
    storage_ambient_temp_c: float | None = None
    held_in_refrigeration: bool | None = None
    operational_metrics_notes: str | None = None
    weather_at_listing: WeatherSnapshot | None = None
    scan: GeminiScan
    accuracy: AccuracyAssessment | None = Field(
        default=None,
        description="Populated for donations created after the accuracy engine rollout; may be null on older Firestore docs.",
    )
    scan_contract_version: Literal[1, 2] = Field(
        default=1,
        description="1 = legacy/partial scan lineage; 2 = `scan.model_id` and `scan.model_version` both present (Phase 2 contract).",
    )
    ngo_queue: list[MatchScore] = Field(default_factory=list)
    assigned_ngo_id: str | None = None
    assigned_ngo_name: str | None = None
    volunteer_name: str | None = None
    volunteer_uid: str | None = None
    pickup_photo_url: str | None = None
    completed_meals_served: int | None = None
    accepted_at: datetime | None = None
    completed_at: datetime | None = None
    acceptance_seconds: int | None = None
    delivery_seconds: int | None = None
    pickup_buffer_extensions: int = 0
    volunteer_task_status: VolunteerTaskStatus | None = None
    volunteer_reject_reason: str | None = None
    volunteer_pickup_notes: str | None = None
    heading_started_at: datetime | None = None
    pickup_reached_at: datetime | None = None
    pickup_completed_at: datetime | None = None
    delivery_started_at: datetime | None = None
    delivery_marked_at: datetime | None = None
    delivery_confirmed_at: datetime | None = None
    volunteer_total_seconds: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    current_radius_km: float = 0.0
    escalation_level: int = 1
    broadcast_wave: int = 1
    wave_started_at: datetime | None = None
    wave_expires_at: datetime | None = None
    excluded_ngo_ids: list[str] = Field(default_factory=list)
    citywide_broadcasted: bool = False
    notified_ngo_ids: list[str] = Field(default_factory=list)
    last_escalation_at: datetime | None = None
    scan_phase_failures: int = Field(
        default=0,
        ge=0,
        description="Incremented on soft scan failures; second failure routes to Super Admin queue.",
    )

    @model_validator(mode="before")
    @classmethod
    def _infer_scan_contract_version(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if data.get("scan_contract_version") is not None:
            return data
        scan = data.get("scan")
        if isinstance(scan, dict):
            complete = bool(scan.get("model_id")) and bool(scan.get("model_version"))
        else:
            complete = False
        data["scan_contract_version"] = 2 if complete else 1
        return data

    @classmethod
    def from_create(
        cls,
        payload: DonationCreate,
        donor: Donor,
        scan: GeminiScan,
        queue: list[MatchScore],
    ) -> "Donation":
        expires_at = datetime.now(timezone.utc) + scaled_timedelta_minutes(scan.freshness_window_minutes)
        top_ngo = queue[0] if queue else None
        items = payload.items or [
            DonationItem(
                food_type=scan.detected_food_type or payload.food_type,
                quantity_kg=payload.quantity_kg,
                meal_count=payload.meal_count,
            )
        ]
        total_qty = round(sum(item.quantity_kg for item in items), 2)
        total_meals = int(sum(item.meal_count for item in items))
        primary_food_type = items[0].food_type if items else (scan.detected_food_type or payload.food_type)
        return cls(
            donor_id=donor.id,
            donor_name=donor.name,
            food_type=primary_food_type,
            quantity_kg=total_qty,
            meal_count=total_meals,
            items=items,
            location=payload.location or donor.location,
            photo_url=payload.photo_url,
            notes=payload.notes,
            food_prepared_at=payload.food_prepared_at,
            storage_ambient_temp_c=payload.storage_ambient_temp_c,
            held_in_refrigeration=payload.held_in_refrigeration,
            operational_metrics_notes=payload.operational_metrics_notes,
            weather_at_listing=None,
            scan=scan,
            scan_contract_version=scan_phase2_contract_version(scan),
            ngo_queue=queue,
            expires_at=expires_at,
            current_radius_km=top_ngo.distance_km if top_ngo else 0.0,
            escalation_level=1,
            broadcast_wave=1,
            wave_started_at=datetime.now(timezone.utc),
            wave_expires_at=datetime.now(timezone.utc) + scaled_timedelta_minutes(30),
            notified_ngo_ids=[top_ngo.ngo_id] if top_ngo else [],
        )


class DonationStatusUpdate(BaseModel):
    status: DonationStatus
    ngo_id: str | None = None
    volunteer_uid: str | None = None
    volunteer_name: str | None = None
    pickup_photo_url: str | None = None
    meals_served: int | None = None
    buffer_minutes: int | None = None
    notes: str | None = None
    volunteer_task_status: VolunteerTaskStatus | None = None
    reject_reason: str | None = None
    received_food_type: str | None = None
    received_quantity_kg: float | None = None
    received_meal_count: int | None = None


class EmergencyRequestCreate(BaseModel):
    ngo_id: str
    food_type: str
    quantity_goal_kg: float = Field(gt=0)
    deadline_minutes: int = Field(default=120, ge=10, le=1440)
    reason: str
    urgency_level: Literal["low", "medium", "high", "critical"] = "high"
    beneficiary_count: int = Field(default=50, ge=1, le=500000)
    required_by_meal_time: str | None = None
    contact_phone: str | None = None
    pickup_address: str | None = None
    min_contribution_kg: float = Field(default=1.0, gt=0)
    max_contribution_kg: float | None = Field(default=None, gt=0)
    notes: str | None = None


class EmergencyContribution(BaseModel):
    donor_id: str
    donor_name: str
    quantity_kg: float
    distance_km: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    accepted: bool = False


class EmergencyRequest(BaseModel):
    id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:10]}")
    ngo_id: str
    ngo_name: str
    food_type: str
    quantity_goal_kg: float
    pledged_kg: float = 0
    reason: str
    urgency_level: Literal["low", "medium", "high", "critical"] = "high"
    beneficiary_count: int = 50
    required_by_meal_time: str | None = None
    contact_phone: str | None = None
    pickup_address: str | None = None
    min_contribution_kg: float = 1.0
    max_contribution_kg: float | None = None
    pool_open: bool = True
    status: Literal["open", "partial_accepted", "cancelled", "fulfilled"] = "open"
    city_scope: bool = True
    popup_active: bool = True
    popup_expires_at: datetime | None = None
    donor_targets: list[str] = Field(default_factory=list)
    contributions: list[EmergencyContribution] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deadline_at: datetime
    notes: str | None = None


class EmergencyContributionCreate(BaseModel):
    donor_id: str
    quantity_kg: float


class EmergencyResolveRequest(BaseModel):
    action: Literal["accept_partial", "cancel"]
    reason: str | None = None


class Prediction(BaseModel):
    id: str
    donor_id: str
    donor_name: str
    area: str
    food_type: str
    predicted_time: str
    probability: float
    nearby_ngos: int
    source: Literal["heuristic", "bigquery_aggregate", "blended"] = "heuristic"


class ImpactStats(BaseModel):
    meals_served: int
    kg_saved: float
    co2_offset_kg: float
    active_donations: int
    completed_donations: int


class Notification(BaseModel):
    id: str = Field(default_factory=lambda: f"ntf_{uuid4().hex[:10]}")
    donation_id: str | None = None
    recipient_role: Role
    recipient_id: str
    title: str
    body: str
    channel: Literal["dashboard", "fcm", "telegram"] = "dashboard"
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommunicationMessageCreate(BaseModel):
    donation_id: str
    sender_role: Role
    sender_id: str
    recipient_role: Role
    recipient_id: str
    body: str


class CommunicationMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:10]}")
    donation_id: str
    sender_role: Role
    sender_id: str
    recipient_role: Role
    recipient_id: str
    body: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelegramLinkRequest(BaseModel):
    chat_id: str
    fssai_license: str


class TelegramLink(BaseModel):
    chat_id: str
    donor_id: str
    donor_name: str
    fssai_license: str
    linked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelegramLinkingToken(BaseModel):
    token: str
    chat_id: str
    chat_title: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(minutes=15))


class TelegramActivationRequest(BaseModel):
    token: str


class TelegramDonationResult(BaseModel):
    ok: bool
    chat_id: str | None = None
    donor_id: str | None = None
    donation_id: str | None = None
    parsed_food_type: str | None = None
    quantity_kg: float | None = None
    reply: str


class TelegramAuthState(BaseModel):
    state_token: str
    donor_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    used: bool = False
    confirmed: bool = False
    link_token: str | None = None


class VolunteerInviteToken(BaseModel):
    token: str
    ngo_id: str
    ngo_name: str
    volunteer_id: str
    name: str
    email: str
    phone: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    used: bool = False
    used_by_uid: str | None = None
    revoked: bool = False
    revoked_at: datetime | None = None


class SlaveBot(BaseModel):
    donor_id: str
    bot_token: str  # Encrypted
    bot_username: str
    bot_id: int
    slave_chat_id: str | None = None
    webhook_registered: bool = False
    confirmed: bool = False
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed_at: datetime | None = None


class ConversationStep(str, Enum):
    """Donation chat steps. `awaiting_operational_metrics` collects optional kitchen signals before POST."""

    idle = "idle"
    awaiting_food_type = "awaiting_food_type"
    awaiting_quantity = "awaiting_quantity"
    awaiting_quantity_text = "awaiting_quantity_text"
    awaiting_more_items = "awaiting_more_items"
    awaiting_operational_metrics = "awaiting_operational_metrics"
    awaiting_notes = "awaiting_notes"
    awaiting_photo = "awaiting_photo"
    awaiting_photo_retry = "awaiting_photo_retry"
    ai_scanning = "ai_scanning"
    gemini_scanning = "gemini_scanning"  # Backward compatibility for persisted states
    awaiting_confirmation = "awaiting_confirmation"
    awaiting_bot_token = "awaiting_bot_token"


class ConversationState(BaseModel):
    chat_id: str
    step: ConversationStep
    food_type: str | None = None
    quantity_kg: float | None = None
    meal_count: int | None = None
    donation_items: list[DonationItem] = Field(default_factory=list)
    notes: str | None = None
    # Deferred photo donation (awaiting_operational_metrics): caption-derived qty/meals + Telegram file id.
    pending_photo_file_id: str | None = None
    pending_photo_kg: float | None = None
    pending_photo_meals: int | None = None
    pending_photo_caption: str | None = None
    photo_file_id: str | None = None
    scan_attempts: int = 0
    food_category: str | None = None
    freshness_window_hrs: int | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
