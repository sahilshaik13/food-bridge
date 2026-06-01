"""
V3-style surplus time-window hints: optional BigQuery aggregates over ML export rows + heuristic
from in-memory donations. NGO pre-alert batch for scheduled jobs (Cloud Scheduler → HTTP → /jobs/...).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import TYPE_CHECKING
from uuid import uuid4

from app.core.config import get_settings
from app.models import Donation, DonationStatus, Donor, Ngo, Notification, Prediction, Role

if TYPE_CHECKING:
    from app.services.demo_store import DemoStore

_PREALERT_GUARD: dict[str, float] = {}
_PREALERT_TTL_SEC = 86400.0


def _distance_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    radius = 6371
    d_lat = radians(b_lat - a_lat)
    d_lng = radians(b_lng - a_lng)
    lat1 = radians(a_lat)
    lat2 = radians(b_lat)
    value = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lng / 2) ** 2
    return round(2 * radius * asin(sqrt(value)), 2)


def _hour_window_label(hour_utc: int) -> str:
    h = hour_utc % 24
    end = (h + 2) % 24
    return f"{h:02d}:00–{end:02d}:00 IST≈ (UTC {h:02d}:00)"


def _count_nearby_ngos(donor: Donor, ngos: dict[str, Ngo], radius_km: float = 14.0) -> int:
    n = 0
    for ngo in ngos.values():
        if _distance_km(donor.location.lat, donor.location.lng, ngo.location.lat, ngo.location.lng) <= radius_km:
            n += 1
    return max(1, n)


def _predictions_heuristic(
    donors: dict[str, Donor],
    donations: list[Donation],
    ngos: dict[str, Ngo],
) -> list[Prediction]:
    completed = [d for d in donations if d.status == DonationStatus.completed]
    by_donor: dict[str, list[Donation]] = {}
    for d in completed:
        by_donor.setdefault(d.donor_id, []).append(d)

    out: list[Prediction] = []
    for donor_id, items in by_donor.items():
        donor = donors.get(donor_id)
        if not donor:
            continue
        if len(items) < 1:
            continue
        hours: list[int] = []
        for it in items:
            ref = it.completed_at or it.created_at
            if ref.tzinfo is None:
                ref = ref.replace(tzinfo=timezone.utc)
            hours.append(ref.astimezone(timezone.utc).hour)
        if not hours:
            continue
        peak_hour = max(set(hours), key=hours.count)
        food_counts: dict[str, int] = {}
        for it in items:
            ft = (it.food_type or "mixed").strip()
            food_counts[ft] = food_counts.get(ft, 0) + 1
        top_food = max(food_counts, key=food_counts.get) if food_counts else "mixed meals"
        n = len(items)
        probability = min(0.93, 0.52 + 0.07 * n + 0.02 * max(0, hours.count(peak_hour) - 1))

        out.append(
            Prediction(
                id=f"pred_heur_{donor_id}_{peak_hour}_{uuid4().hex[:6]}",
                donor_id=donor_id,
                donor_name=donor.name,
                area=donor.area,
                food_type=top_food,
                predicted_time=_hour_window_label(peak_hour),
                probability=round(probability, 3),
                nearby_ngos=_count_nearby_ngos(donor, ngos),
                source="heuristic",
            )
        )

    out.sort(key=lambda p: p.probability, reverse=True)
    return out[:25]


def _predictions_bigquery_aggregate(donors: dict[str, Donor], ngos: dict[str, Ngo]) -> list[Prediction]:
    settings = get_settings()
    if not settings.v3_prediction_bigquery_enabled:
        return []
    try:
        from google.cloud import bigquery

        from app.core.cloud_clients import get_bigquery_client

        client = get_bigquery_client()
        table_fqn = f"`{settings.google_cloud_project}.{settings.bigquery_ml_dataset}.{settings.bigquery_ml_table}`"
        sql = f"""
WITH d AS (
  SELECT donor_id,
         food_type,
         EXTRACT(HOUR FROM ingested_at) AS hr,
         donation_status
  FROM {table_fqn}
  WHERE ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 120 DAY)
),
combo AS (
  SELECT donor_id, food_type, hr, COUNT(*) AS cnt,
         COUNTIF(donation_status = 'completed') AS completed_cnt
  FROM d
  GROUP BY donor_id, food_type, hr
),
ranked AS (
  SELECT donor_id, food_type, hr, cnt, completed_cnt,
         ROW_NUMBER() OVER (PARTITION BY donor_id ORDER BY cnt DESC, completed_cnt DESC) AS rn
  FROM combo
)
SELECT donor_id, food_type, hr, cnt, completed_cnt
FROM ranked
WHERE rn = 1 AND completed_cnt >= 1
ORDER BY cnt DESC
LIMIT 35
"""
        rows = list(client.query(sql).result())
        out: list[Prediction] = []
        for row in rows:
            donor_id = row["donor_id"]
            donor = donors.get(str(donor_id))
            if not donor:
                continue
            hr = int(row["hr"])
            ft = str(row["food_type"] or "mixed meals")
            cnt = int(row["cnt"])
            prob = min(0.94, 0.55 + 0.025 * cnt)
            out.append(
                Prediction(
                    id=f"pred_bq_{donor_id}_{hr}_{uuid4().hex[:6]}",
                    donor_id=str(donor_id),
                    donor_name=donor.name,
                    area=donor.area,
                    food_type=ft,
                    predicted_time=_hour_window_label(hr),
                    probability=round(prob, 3),
                    nearby_ngos=_count_nearby_ngos(donor, ngos),
                    source="bigquery_aggregate",
                )
            )
        out.sort(key=lambda p: p.probability, reverse=True)
        return out[:25]
    except Exception as exc:
        print(f"[surplus_prediction] BigQuery aggregate skipped: {exc}")
        return []


def merge_predictions(heuristic: list[Prediction], bq: list[Prediction]) -> list[Prediction]:
    """Prefer BigQuery aggregate when available for the same donor."""
    by_donor: dict[str, Prediction] = {p.donor_id: p for p in heuristic}
    for p in bq:
        prev = by_donor.get(p.donor_id)
        if prev is None:
            by_donor[p.donor_id] = p
        else:
            by_donor[p.donor_id] = p.model_copy(update={"source": "blended"})
    merged = list(by_donor.values())
    merged.sort(key=lambda x: x.probability, reverse=True)
    return merged[:30]


def compute_surplus_predictions(store: DemoStore) -> list[Prediction]:
    donors = store.donors
    donations = list(store.donations.values())
    ngos = store.ngos

    h = _predictions_heuristic(donors, donations, ngos)
    disable = os.environ.get("DISABLE_AI_INTEGRATION", "false").lower() == "true"
    bq: list[Prediction] = []
    if not disable:
        bq = _predictions_bigquery_aggregate(donors, ngos)

    if bq:
        merged = merge_predictions(h, bq)
    else:
        merged = h

    if merged:
        return merged

    # Demo fallback when no completed history (keeps smoke / empty DB useful)
    demo: list[Prediction] = []
    for donor in list(donors.values())[:5]:
        demo.append(
            Prediction(
                id=f"pred_demo_{donor.id}_{uuid4().hex[:6]}",
                donor_id=donor.id,
                donor_name=donor.name,
                area=donor.area,
                food_type="mixed meals",
                predicted_time="18:00–20:00 (baseline)",
                probability=0.55,
                nearby_ngos=_count_nearby_ngos(donor, ngos),
                source="heuristic",
            )
        )
    return demo[:2]


def run_surplus_pre_alert_job(store: DemoStore) -> dict[str, int | list[str]]:
    """Notify NGO coordinators about upcoming surplus windows (scheduled job entrypoint)."""
    settings = get_settings()
    if not settings.surplus_pre_alert_enabled:
        return {"skipped": 1, "reason": "disabled", "sent": 0, "keys": []}

    floor = settings.surplus_pre_alert_probability_floor
    radius = settings.surplus_pre_alert_radius_km
    preds = compute_surplus_predictions(store)
    sent_keys: list[str] = []
    n_sent = 0
    today = datetime.now(timezone.utc).date().isoformat()

    for p in preds:
        if p.probability < floor:
            continue
        donor = store.donors.get(p.donor_id)
        if not donor:
            continue
        for ngo in store.ngos.values():
            dist = _distance_km(donor.location.lat, donor.location.lng, ngo.location.lat, ngo.location.lng)
            if dist > radius:
                continue
            guard_key = f"{today}:{ngo.id}:{p.donor_id}:{p.predicted_time}"
            now = time.time()
            last = _PREALERT_GUARD.get(guard_key, 0)
            if now - last < _PREALERT_TTL_SEC:
                continue

            store.create_notification(
                Notification(
                    recipient_role=Role.ngo_coordinator,
                    recipient_id=ngo.id,
                    title=f"Surplus window hint · {donor.area}",
                    body=(
                        f"{p.donor_name} historically peaks near {p.predicted_time} "
                        f"({p.food_type}). Confidence {p.probability:.0%}. Distance ~{dist:.1f} km — prep pickup capacity."
                    ),
                    channel="fcm",
                )
            )
            _PREALERT_GUARD[guard_key] = now
            n_sent += 1
            sent_keys.append(guard_key)

    return {"sent": n_sent, "keys": sent_keys[:50], "predictions_scanned": len(preds)}
