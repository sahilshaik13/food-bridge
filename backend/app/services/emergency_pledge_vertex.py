"""
PRD §5-style emergency pledge intelligence: prioritize donors for pledge asks and (optionally)
personalize notification title/body via Vertex Gemini. Heuristic fallback always available.
"""

from __future__ import annotations

import json
import os
import re
from math import asin, cos, radians, sin, sqrt
from typing import Any

from vertexai.generative_models import GenerativeModel

from app.core.cloud_clients import initialize_vertex_ai
from app.core.config import get_settings
from app.models import Donation, Donor, EmergencyRequestCreate, Ngo


def _distance_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    radius = 6371
    d_lat = radians(b_lat - a_lat)
    d_lng = radians(b_lng - a_lng)
    lat1 = radians(a_lat)
    lat2 = radians(b_lat)
    value = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lng / 2) ** 2
    return round(2 * radius * asin(sqrt(value)), 2)


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


def _candidate_pool(ngo: Ngo, donors: dict[str, Donor]) -> list[Donor]:
    city = [d for d in donors.values() if d.location.area and ngo.location.area]
    if city:
        return city
    return list(donors.values())


def _heuristic_rank(
    ngo: Ngo,
    payload: EmergencyRequestCreate,
    donors: dict[str, Donor],
    donations: list[Donation],
) -> list[str]:
    pool = _candidate_pool(ngo, donors)
    food_kw = re.split(r"[^\w\u0900-\u0c7f]+", payload.food_type.lower())
    food_kw = [w for w in food_kw if len(w) > 2][:4]

    def score(d: Donor) -> float:
        dist = _distance_km(d.location.lat, d.location.lng, ngo.location.lat, ngo.location.lng)
        trust = float(d.score.trust_score) if d.score else 42.0
        mine = [x for x in donations if x.donor_id == d.id]
        mine.sort(key=lambda x: x.created_at)
        recent = mine[-5:] if mine else []
        bonus = 0.0
        for item in recent:
            ft = item.food_type.lower()
            if any(k in ft for k in food_kw):
                bonus += 18.0
                break
        return trust + bonus - dist * 1.35

    ordered = sorted(pool, key=score, reverse=True)
    return [d.id for d in ordered]


def _default_copy(donor: Donor, ngo: Ngo, payload: EmergencyRequestCreate) -> tuple[str, str]:
    first = donor.name.strip().split()[0] if donor.name.strip() else "there"
    title = f"{ngo.name.split()[0]} · urgent surplus ask"
    reason_snip = (payload.reason or "").strip()
    if len(reason_snip) > 90:
        reason_snip = reason_snip[:87] + "…"
    body = (
        f"Hi {first}, {ngo.name} is short ~{payload.quantity_goal_kg:g} kg {payload.food_type}. "
        f"{reason_snip} Open FoodBridge to pledge what you can."
    )
    return title, body


def select_emergency_donors_and_pledge_copy(
    *,
    payload: EmergencyRequestCreate,
    ngo: Ngo,
    donors: dict[str, Donor],
    donations: list[Donation],
) -> tuple[list[str], dict[str, tuple[str, str]]]:
    """
    Returns donor ids to notify (capped) and per-donor (title, body) for dashboard / FCM-style channels.
    """
    settings = get_settings()
    cap = settings.emergency_donor_notify_cap
    heuristic_ids = _heuristic_rank(ngo, payload, donors, donations)
    messages: dict[str, tuple[str, str]] = {}
    if not heuristic_ids:
        return [], {}

    disable_ai = os.environ.get("DISABLE_AI_INTEGRATION", "false").lower() == "true"
    if disable_ai or not settings.emergency_vertex_enabled:
        picked = heuristic_ids[:cap]
        for did in picked:
            d = donors.get(did)
            if d:
                messages[did] = _default_copy(d, ngo, payload)
        return picked, messages

    if not initialize_vertex_ai(settings):
        picked = heuristic_ids[:cap]
        for did in picked:
            d = donors.get(did)
            if d:
                messages[did] = _default_copy(d, ngo, payload)
        return picked, messages

    pool_ids = heuristic_ids[: min(35, len(heuristic_ids))]
    if len(pool_ids) <= 1:
        picked = pool_ids[:cap]
        for did in picked:
            d = donors.get(did)
            if d:
                messages[did] = _default_copy(d, ngo, payload)
        return picked, messages

    cand_payload = []
    for did in pool_ids:
        d = donors.get(did)
        if not d:
            continue
        dist = _distance_km(d.location.lat, d.location.lng, ngo.location.lat, ngo.location.lng)
        trust = d.score.trust_score if d.score else None
        tier = d.score.trust_tier if d.score else None
        mine = [x for x in donations if x.donor_id == did]
        mine.sort(key=lambda x: x.created_at)
        recent_types = [x.food_type for x in mine[-4:]]
        cand_payload.append(
            {
                "donor_id": did,
                "name": d.name,
                "area": d.area,
                "distance_km": dist,
                "trust_score": trust,
                "trust_tier": tier,
                "avg_surplus_hint": d.avg_surplus_kg,
                "recent_surplus_foods": recent_types,
            }
        )

    prompt = f"""You help NGOs in India coordinate emergency food pledges from verified restaurants.

Emergency context:
- NGO: {ngo.name} ({ngo.area})
- Needed: {payload.quantity_goal_kg:g} kg {payload.food_type}
- Urgency: {payload.urgency_level}
- Reason: {payload.reason}
- Deadline window: {payload.deadline_minutes} minutes from broadcast

Donor candidates (JSON):
{json.dumps(cand_payload, ensure_ascii=False)}

Respond with ONLY valid JSON (no markdown fence):
{{
  "ranked_donor_ids": ["best_first", "..."],
  "pledge_messages": [
    {{"donor_id": "...", "title": "short push title max 60 chars", "body": "personalised ask max 220 chars, warm tone, mention distance or trust implicitly if helpful"}}
  ]
}}

Rules:
- Include only donor_ids from candidates; rank by likelihood to fulfill quickly (proximity, surplus capacity hints, food affinity from recent_surplus_foods).
- Produce exactly one pledge_messages entry per donor you want to notify (same people as ranked order), maximum {cap} donors.
- Title and body must be plain text, no markdown.
- Keep language concise for mobile push notifications."""

    try:
        model = GenerativeModel(settings.vertex_ai_model_id)
        response = model.generate_content(prompt)
        data = _parse_json_response(response.text)
        ranked = data.get("ranked_donor_ids") or data.get("rankedDonorIds") or []
        pm = data.get("pledge_messages") or data.get("pledgeMessages") or []
        allowed = set(pool_ids)
        ordered: list[str] = []
        if isinstance(ranked, list):
            for raw in ranked:
                sid = str(raw).strip()
                if sid in allowed and sid not in ordered:
                    ordered.append(sid)
        for did in pool_ids:
            if did not in ordered:
                ordered.append(did)
        if not ordered:
            ordered = list(pool_ids)

        msg_by_id: dict[str, tuple[str, str]] = {}
        if isinstance(pm, list):
            for row in pm:
                if not isinstance(row, dict):
                    continue
                did = str(row.get("donor_id") or row.get("donorId") or "").strip()
                title = str(row.get("title") or "").strip()
                body = str(row.get("body") or "").strip()
                if did in allowed and title and body:
                    msg_by_id[did] = (title[:120], body[:280])

        picked = ordered[:cap]
        out_messages: dict[str, tuple[str, str]] = {}
        for did in picked:
            if did in msg_by_id:
                out_messages[did] = msg_by_id[did]
            else:
                d = donors.get(did)
                if d:
                    out_messages[did] = _default_copy(d, ngo, payload)
        return picked, out_messages
    except Exception as exc:
        print(f"emergency pledge Vertex fallback: {exc}")
        picked = heuristic_ids[:cap]
        for did in picked:
            d = donors.get(did)
            if d:
                messages[did] = _default_copy(d, ngo, payload)
        return picked, messages
