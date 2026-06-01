from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from vertexai.generative_models import GenerativeModel

from app.core.cloud_clients import initialize_vertex_ai
from app.core.config import get_settings
from app.models import AccuracyAssessment, GeminiScan, WeatherSnapshot


class _VertexAccuracyJson(BaseModel):
    """Strict JSON shape returned by Vertex for accuracy assessment."""

    score: float = Field(ge=0.0, le=1.0)
    band: Literal["low", "medium", "high"]
    anomaly_probability: float = Field(ge=0.0, le=1.0)
    recommendation: Literal["auto_reject", "manual_review", "approve_with_caution", "approve"]
    top_factors: list[str] = Field(default_factory=list)
    explanation: str = Field(min_length=1, max_length=4000)


def _parse_json_response(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
        elif "\n" in candidate:
            candidate = candidate.split("\n", 1)[-1].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            return json.loads(candidate[start : end + 1])
        raise


def try_vertex_accuracy_assessment(
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
) -> AccuracyAssessment | None:
    """
    Phase 3: Vertex Gemini structured accuracy assessment.
    Returns None if Vertex is unavailable or the response is invalid.
    """
    settings = get_settings()
    if not initialize_vertex_ai(settings):
        return None

    payload = {
        "scan": {
            "passed": scan.passed,
            "confidence": scan.confidence,
            "reason": scan.reason,
            "detected_food_type": scan.detected_food_type,
            "freshness_window_minutes": scan.freshness_window_minutes,
            "fallback_used": scan.fallback_used,
        },
        "quantity_kg": quantity_kg,
        "notes": notes or "",
        "donor_trust_score": donor_trust_score,
        "donor_trust_tier": donor_trust_tier,
        "operational_metrics": {
            "food_prepared_at": food_prepared_at.isoformat() if food_prepared_at else None,
            "storage_ambient_temp_c": storage_ambient_temp_c,
            "held_in_refrigeration": held_in_refrigeration,
            "notes": operational_metrics_notes or "",
        },
        "weather_near_venue": weather.model_dump(mode="json") if weather else None,
        "listing_created_at": listing_created_at.isoformat() if listing_created_at else None,
    }

    prompt = f"""You are FoodBridge's donation accuracy risk assessor for surplus food redistribution in India.
Given structured inputs (JSON below), estimate how trustworthy and consistent this donation listing is for NGO routing — NOT laboratory food safety.

INPUT JSON:
{json.dumps(payload, ensure_ascii=False)}

Rules:
- score: 0–1 overall confidence that listing data is coherent and low-risk for routing (higher is better).
- anomaly_probability: 0–1 chance of data inconsistency, exaggeration, or mismatch with scan signals.
- band: low / medium / high aligned with score (low < ~0.4, medium ~0.4–0.75, high above).
- recommendation:
  - auto_reject only if score would justify blocking without human review;
  - manual_review when uncertain or conflicting signals;
  - approve_with_caution when generally OK but scan or quantity warrants caution;
  - approve only when signals are strong and consistent.
- top_factors: up to 6 short snake_case or plain tokens explaining drivers (e.g. scan_fallback_used, high_quantity).
- explanation: 2–4 sentences for NGO/coordinator dashboards; cite key signals; do not claim lab safety certification.
- Many venues cannot measure kitchen metrics: when operational_metrics are absent or null-heavy, add only a small anomaly uplift and recommend NGO pickup verification — do not harshly penalize missing optional fields.
- When weather_near_venue shows very hot outdoor temperature, routing caution may be appropriate for non-refrigerated holds.
- When held_in_refrigeration is true or cool storage temps are stated, that generally supports safer short-term holding.

Respond with ONLY valid JSON (no markdown fence), exactly these keys:
{{
  "score": <float 0-1>,
  "band": "low"|"medium"|"high",
  "anomaly_probability": <float 0-1>,
  "recommendation": "auto_reject"|"manual_review"|"approve_with_caution"|"approve",
  "top_factors": [<strings>],
  "explanation": "<string>"
}}
"""

    try:
        model = GenerativeModel(settings.vertex_ai_model_id)
        response = model.generate_content(prompt)
        text = getattr(response, "text", None)
        raw = _parse_json_response(text)
        # Tolerate minor JSON slips from the model before strict validation
        if isinstance(raw.get("score"), (int, float)):
            raw["score"] = max(0.0, min(1.0, float(raw["score"])))
        if isinstance(raw.get("anomaly_probability"), (int, float)):
            raw["anomaly_probability"] = max(0.0, min(1.0, float(raw["anomaly_probability"])))
        try:
            parsed = _VertexAccuracyJson.model_validate(raw)
        except Exception:
            return None
        now = datetime.now(timezone.utc)
        mid = "foodbridge-vertex-accuracy"
        ver = f"{settings.vertex_ai_model_id}@{settings.vertex_ai_model_version}"
        return AccuracyAssessment(
            score=round(parsed.score, 4),
            band=parsed.band,
            anomaly_probability=round(parsed.anomaly_probability, 4),
            recommendation=parsed.recommendation,
            top_factors=parsed.top_factors[:8] if parsed.top_factors else ["vertex_assessment"],
            explanation=parsed.explanation.strip(),
            model_id=mid,
            model_version=ver,
            generated_at=now,
            fallback_used=False,
        )
    except Exception as exc:
        print(f"Vertex accuracy assessment error ({settings.vertex_ai_model_id}): {exc}")
        return None
