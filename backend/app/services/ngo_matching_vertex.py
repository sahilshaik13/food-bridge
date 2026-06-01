"""
PRD: Gemini-assisted NGO ranking (proximity + food fit + nutritional compatibility narrative).

Refines the heuristic queue from demo_store; on any failure returns the heuristic order unchanged.
"""

from __future__ import annotations

import json
from typing import Any

from vertexai.generative_models import GenerativeModel

from app.core.cloud_clients import initialize_vertex_ai
from app.core.config import get_settings
from app.models import MatchScore


def _parse_json_response(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            return json.loads(candidate[start : end + 1])
        raise


def refine_ngo_queue_with_vertex(
    *,
    primary_food_type: str,
    quantity_kg: float,
    donor_area: str,
    heuristic_scores: list[MatchScore],
    max_candidates: int = 22,
) -> list[MatchScore]:
    """
    Send top heuristic NGOs to Gemini for re-ordering; preserves tail unchanged.
    """
    if len(heuristic_scores) <= 1:
        return heuristic_scores

    settings = get_settings()
    if not initialize_vertex_ai(settings):
        return heuristic_scores

    head = heuristic_scores[:max_candidates]
    tail = heuristic_scores[max_candidates:]
    allowed_ids = {m.ngo_id for m in head}
    ngo_payload = [
        {
            "ngo_id": m.ngo_id,
            "ngo_name": m.ngo_name,
            "distance_km": round(m.distance_km, 2),
            "proximity_score": m.proximity_score,
            "food_type_score": m.food_type_score,
            "nutrition_score": m.nutrition_score,
            "heuristic_total": m.total_score,
        }
        for m in head
    ]

    prompt = f"""You prioritize NGOs for surplus food redistribution (India / Hyderabad context).

Donation context:
- Primary food: {primary_food_type}
- Quantity (kg): {quantity_kg}
- Donor area (hint): {donor_area}

Each NGO below already has distance-based and preference-based heuristic subscores. Re-rank them for
best beneficiary nutritional fit and operational likelihood to absorb this donation soon.

Candidates (JSON array):
{json.dumps(ngo_payload, ensure_ascii=False)}

Respond with ONLY valid JSON (no markdown fence):
{{"ranked_ngo_ids": ["ngo_id_in_best_first_order", "..."]}}

Rules:
- Include every ngo_id from candidates exactly once.
- Prefer closer NGOs when fit is comparable; weight nutrition / dietary alignment heavily."""

    try:
        model = GenerativeModel(settings.vertex_ai_model_id)
        response = model.generate_content(prompt)
        data = _parse_json_response(response.text)
        ranked_ids = data.get("ranked_ngo_ids") or data.get("rankedNgos")
        if not isinstance(ranked_ids, list) or len(ranked_ids) == 0:
            return heuristic_scores

        by_id = {m.ngo_id: m for m in head}
        ordered_head: list[MatchScore] = []
        used: set[str] = set()
        for nid in ranked_ids:
            sid = str(nid).strip()
            if sid in by_id and sid not in used:
                ordered_head.append(by_id[sid])
                used.add(sid)
        for m in head:
            if m.ngo_id not in used:
                ordered_head.append(m)

        # Refresh reason line for transparency (keep numeric scores from heuristic pass)
        for i, m in enumerate(ordered_head):
            reason = (
                f"Gemini-ranked #{i + 1}: {m.ngo_name} — proximity {m.proximity_score}, "
                f"food fit {m.food_type_score}, nutrition {m.nutrition_score}."
            )
            ordered_head[i] = m.model_copy(update={"reason": reason})

        return ordered_head + tail
    except Exception as exc:
        print(f"ngo_matching_vertex: fallback to heuristic ({exc})")
        return heuristic_scores
