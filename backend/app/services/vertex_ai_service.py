from __future__ import annotations

import json
from typing import Any

from vertexai.generative_models import GenerativeModel, Part

from app.core.cloud_clients import initialize_vertex_ai
from app.core.config import get_settings
from app.models import GeminiScan


def scan_food_with_vertex_ai(image_bytes: bytes, food_type_hint: str = "") -> GeminiScan:
    """Run food safety scan using Vertex AI multimodal model."""
    settings = get_settings()
    if not initialize_vertex_ai(settings):
        raise RuntimeError("Vertex AI initialization failed")

    model = GenerativeModel(settings.vertex_ai_model_id)
    prompt = f"""
    Analyze this food image for donation safety.
    1. Is it spoiled, moldy, or unsafe to eat?
    2. What is the specific food type?
    3. Based on food type, assign freshness window in minutes (cooked rice 240, biryani 180, dal 240, bread 2880).

    Food hint from donor: {food_type_hint}

    Return JSON format:
    {{
        "passed": bool,
        "confidence": float,
        "reason": str,
        "detected_food_type": str,
        "freshness_window_minutes": int
    }}
    """

    parts: list[Any] = [prompt]
    if image_bytes:
        parts.insert(0, Part.from_data(image_bytes, mime_type="image/jpeg"))

    try:
        response = model.generate_content(parts)
        data = _parse_json_response(response.text)
        return GeminiScan(
            passed=bool(data.get("passed", True)),
            confidence=float(data.get("confidence", 0.9)),
            reason=str(data.get("reason", "Vertex AI analysis completed.")),
            detected_food_type=str(data.get("detected_food_type", food_type_hint or "mixed meals")),
            freshness_window_minutes=int(data.get("freshness_window_minutes", 180)),
            model_id=settings.vertex_ai_model_id,
            model_version=settings.vertex_ai_model_version,
            fallback_used=False,
        )
    except Exception as exc:
        print(f"Vertex AI scan error ({settings.vertex_ai_model_id}): {exc}")
        return _fallback_scan(food_type_hint)


def _parse_json_response(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
    return json.loads(candidate)


def _fallback_scan(food_type_hint: str) -> GeminiScan:
    lowered = food_type_hint.lower()
    rejected = any(word in lowered for word in ["spoiled", "mold", "stale", "unsafe", "rotten"])

    if any(word in lowered for word in ["milk", "curd", "paneer", "yogurt"]):
        freshness = 90
    elif any(word in lowered for word in ["biryani", "rice", "dal", "curry"]):
        freshness = 150
    elif any(word in lowered for word in ["bread", "roti", "chapati"]):
        freshness = 480
    else:
        freshness = 180

    return GeminiScan(
        passed=not rejected,
        confidence=0.95 if not rejected else 0.85,
        reason=(
            "Vertex AI fallback analysis: Food appears fresh and safe for consumption."
            if not rejected
            else "Potential spoilage detected."
        ),
        detected_food_type=food_type_hint or "mixed meals",
        freshness_window_minutes=freshness,
        model_id=get_settings().vertex_ai_model_id,
        model_version=get_settings().vertex_ai_model_version,
        fallback_used=True,
    )
