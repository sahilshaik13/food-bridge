from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from app.core.config import get_settings
from app.models import AccuracyAssessment, GeminiScan, WeatherSnapshot

_ACCURACY_METRICS_LOCK = threading.Lock()
_accuracy_counts = {"vertex_assessments": 0, "heuristic_assessments": 0}


def get_accuracy_pipeline_metrics() -> dict[str, int]:
    with _ACCURACY_METRICS_LOCK:
        return dict(_accuracy_counts)


def _record_accuracy_vertex() -> None:
    with _ACCURACY_METRICS_LOCK:
        _accuracy_counts["vertex_assessments"] += 1


def _record_accuracy_heuristic() -> None:
    with _ACCURACY_METRICS_LOCK:
        _accuracy_counts["heuristic_assessments"] += 1


def _accuracy_vertex_enabled(settings) -> bool:
    if os.environ.get("DISABLE_AI_INTEGRATION", "false").lower() == "true":
        return False
    return settings.accuracy_vertex_enabled


def apply_accuracy_safety_rails(assessment: AccuracyAssessment, scan: GeminiScan) -> AccuracyAssessment:
    """
    Hard gates: failed visual scan cannot receive an unconditional approve;
    scan fallback cannot yield a plain approve.
    """
    score = max(0.0, min(1.0, float(assessment.score)))
    anomaly = max(0.0, min(1.0, float(assessment.anomaly_probability)))
    rec = assessment.recommendation
    band = assessment.band
    explanation = assessment.explanation

    if not scan.passed:
        score = min(score, 0.52)
        anomaly = max(anomaly, 0.45)
        if rec in ("approve", "approve_with_caution"):
            rec = "manual_review"
        explanation = f"[Safety gate: primary scan marked not passed.] {explanation}"
        if score < 0.35:
            band = "low"
        elif band == "high":
            band = "medium"

    if scan.fallback_used and rec == "approve":
        rec = "approve_with_caution"
        score = min(score, 0.78)
        explanation = f"[Scan used fallback pipeline; routing requires caution.] {explanation}"

    # Align band to score bands for consistency after adjustments
    if score < 0.40:
        band = "low"
    elif score < 0.75:
        if band == "high":
            band = "medium"
    else:
        if band == "low":
            band = "medium"

    return assessment.model_copy(
        update={
            "score": round(score, 4),
            "anomaly_probability": round(anomaly, 4),
            "recommendation": rec,
            "band": band,
            "explanation": explanation.strip(),
        }
    )


def _dt_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def evaluate_donation_accuracy_heuristic(
    scan: GeminiScan,
    *,
    quantity_kg: float,
    notes: str | None = None,
    food_prepared_at: datetime | None = None,
    storage_ambient_temp_c: float | None = None,
    held_in_refrigeration: bool | None = None,
    operational_metrics_notes: str | None = None,
    weather: WeatherSnapshot | None = None,
    listing_created_at: datetime | None = None,
) -> AccuracyAssessment:
    """Deterministic baseline (Phase 3 fallback)."""
    combined = " ".join(x for x in (notes, operational_metrics_notes) if x)
    notes_lower = combined.lower()
    score = max(0.0, min(1.0, float(scan.confidence)))
    anomaly = max(0.0, min(1.0, 1.0 - score))
    factors: list[str] = []

    if scan.fallback_used:
        score -= 0.15
        anomaly += 0.2
        factors.append("fallback_scan_used")

    if not scan.passed:
        score -= 0.35
        anomaly += 0.25
        factors.append("visual_safety_failed")

    if scan.freshness_window_minutes <= 90:
        score -= 0.10
        anomaly += 0.08
        factors.append("short_freshness_window")
    elif scan.freshness_window_minutes >= 240:
        score += 0.05
        anomaly -= 0.03
        factors.append("long_freshness_window")

    if quantity_kg > 75:
        score -= 0.05
        anomaly += 0.06
        factors.append("large_quantity_outlier")

    for token in ("smell", "stale", "sour", "spoiled", "contaminated"):
        if token in notes_lower:
            score -= 0.12
            anomaly += 0.10
            factors.append(f"risk_keyword:{token}")
            break

    has_any_metric = (
        food_prepared_at is not None
        or storage_ambient_temp_c is not None
        or held_in_refrigeration is not None
        or bool((operational_metrics_notes or "").strip())
    )
    if not has_any_metric:
        anomaly += 0.035
        factors.append("operational_metrics_not_provided")
    else:
        factors.append("operational_metrics_partial_or_full")

    if held_in_refrigeration is True:
        score += 0.04
        anomaly -= 0.03
        factors.append("stated_refrigerated_hold")
    elif held_in_refrigeration is False:
        factors.append("stated_non_refrigerated_hold")

    if storage_ambient_temp_c is not None:
        if storage_ambient_temp_c >= 32:
            score -= 0.08
            anomaly += 0.09
            factors.append("high_ambient_storage_temp")
        elif storage_ambient_temp_c <= 22:
            score += 0.03
            anomaly -= 0.02
            factors.append("cool_room_storage_temp")

    prepared = _dt_utc(food_prepared_at)
    listed = _dt_utc(listing_created_at)
    if prepared is not None and listed is not None:
        delta_min = (listed - prepared).total_seconds() / 60.0
        if delta_min > 240 and held_in_refrigeration is not True:
            score -= 0.06
            anomaly += 0.07
            factors.append("long_hold_time_without_refrigeration_flag")

    if weather is not None:
        if weather.temp_c >= 35:
            anomaly += 0.05
            factors.append("hot_outdoor_conditions_near_venue")
        elif weather.temp_c <= 28:
            anomaly -= 0.02

    score = max(0.0, min(1.0, score))
    anomaly = max(0.0, min(1.0, anomaly))

    if score < 0.40:
        band = "low"
        recommendation = "auto_reject"
    elif score < 0.60:
        band = "low"
        recommendation = "manual_review"
    elif score < 0.80:
        band = "medium"
        recommendation = "approve_with_caution"
    else:
        band = "high"
        recommendation = "approve"

    recommendation_text = {
        "auto_reject": "Auto reject due to high modeled risk.",
        "manual_review": "Manual review required before NGO acceptance.",
        "approve_with_caution": "Approve with caution and field verification.",
        "approve": "Approved for normal routing.",
    }[recommendation]
    explanation = (
        f"Accuracy band: {band}. "
        f"Estimated anomaly probability: {round(anomaly * 100, 1)}%. "
        f"{recommendation_text}"
    )

    return AccuracyAssessment(
        score=round(score, 4),
        band=band,
        anomaly_probability=round(anomaly, 4),
        recommendation=recommendation,
        top_factors=factors[:6] if factors else ["baseline_confidence"],
        explanation=explanation,
        model_id="foodbridge-accuracy-heuristic-v1",
        model_version="2.1.0",
        generated_at=datetime.now(timezone.utc),
        fallback_used=True,
    )


def evaluate_donation_accuracy(
    scan: GeminiScan,
    *,
    quantity_kg: float,
    notes: str | None = None,
    donor_trust_score: int | None = None,
    donor_trust_tier: str | None = None,
    food_prepared_at: datetime | None = None,
    storage_ambient_temp_c: float | None = None,
    held_in_refrigeration: bool | None = None,
    operational_metrics_notes: str | None = None,
    weather: WeatherSnapshot | None = None,
    listing_created_at: datetime | None = None,
) -> AccuracyAssessment:
    """
    Phase 3: try Vertex structured assessment, then deterministic heuristic.
    Safety rails apply to both paths (Vertex output is gated before return).
    """
    settings = get_settings()
    assessed: AccuracyAssessment | None = None

    if _accuracy_vertex_enabled(settings):
        try:
            from app.services.accuracy_vertex_service import try_vertex_accuracy_assessment

            assessed = try_vertex_accuracy_assessment(
                scan,
                quantity_kg=quantity_kg,
                notes=notes,
                donor_trust_score=donor_trust_score,
                donor_trust_tier=donor_trust_tier,
                food_prepared_at=food_prepared_at,
                storage_ambient_temp_c=storage_ambient_temp_c,
                held_in_refrigeration=held_in_refrigeration,
                operational_metrics_notes=operational_metrics_notes,
                weather=weather,
                listing_created_at=listing_created_at,
            )
        except Exception as exc:
            print(f"Accuracy vertex orchestration error: {exc}")
            assessed = None

    if assessed is not None:
        _record_accuracy_vertex()
        return apply_accuracy_safety_rails(assessed, scan)

    _record_accuracy_heuristic()
    base = evaluate_donation_accuracy_heuristic(
        scan,
        quantity_kg=quantity_kg,
        notes=notes,
        food_prepared_at=food_prepared_at,
        storage_ambient_temp_c=storage_ambient_temp_c,
        held_in_refrigeration=held_in_refrigeration,
        operational_metrics_notes=operational_metrics_notes,
        weather=weather,
        listing_created_at=listing_created_at,
    )
    return apply_accuracy_safety_rails(base, scan)
