"""
Municipal heatmap: GeoJSON surplus (donor-weighted) + demand (NGO) + coverage gap points.
Heuristic gap rule (PRD §8 heatmap_service): high-demand zones with no donor within N km.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.models import Donation, DonationStatus, Donor, Ngo

if TYPE_CHECKING:
    from app.services.demo_store import DemoStore

from app.services.demo_store import distance_km


def _donor_surplus_weight(donor: Donor, donations: list[Donation], days: int = 30) -> int:
    base = max(1, int(donor.monthly_meals or 0))
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    bonus = 0
    for d in donations:
        if d.donor_id != donor.id:
            continue
        if d.status != DonationStatus.completed:
            continue
        ref = d.completed_at or d.created_at
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        if ref >= cutoff:
            bonus += 1
    return base + min(bonus * 50, 500)


def _coverage_gap_features(
    donors: dict[str, Donor],
    ngos: dict[str, Ngo],
    radius_km: float,
    min_beneficiaries: int,
) -> list[dict]:
    donor_list = list(donors.values())
    if not donor_list or not ngos:
        return []

    scored: list[tuple[tuple[float, int], dict]] = []
    for ngo in ngos.values():
        if int(ngo.beneficiary_count or 0) < min_beneficiaries:
            continue
        nearest = min(
            (
                distance_km(
                    d.location.lat,
                    d.location.lng,
                    ngo.location.lat,
                    ngo.location.lng,
                )
                for d in donor_list
            ),
            default=999.0,
        )
        if nearest <= radius_km:
            continue
        demand = int(ngo.beneficiary_count or 0)
        if nearest >= radius_km + 3:
            severity = "high"
        elif nearest >= radius_km + 1.5:
            severity = "medium"
        else:
            severity = "low"
        reason = (
            f"High beneficiary demand (~{demand}), nearest recurring donor ≈ {nearest:.1f} km "
            f"(threshold {radius_km:.0f} km)."
        )
        feat = {
            "type": "Feature",
            "properties": {
                "kind": "coverage_gap",
                "severity": severity,
                "area": ngo.name,
                "reason": reason,
                "demand_weight": demand,
                "nearest_donor_km": round(nearest, 2),
                "suggested_coverage_radius_m": int(min(nearest * 1000, 25000)),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [ngo.location.lng, ngo.location.lat],
            },
        }
        scored.append(((nearest, demand), feat))

    scored.sort(key=lambda x: (x[0][0], x[0][1]), reverse=True)
    return [feat for _, feat in scored[:12]]


def build_heatmap_payload(store: "DemoStore") -> dict:
    """GeoJSON surplus/demand layers + gap FeatureCollection + summary stats."""
    settings = get_settings()
    radius_km = settings.heatmap_gap_radius_km
    min_ben = settings.heatmap_gap_min_beneficiaries

    donors = store.donors
    ngos = store.ngos
    donations = list(store.donations.values())

    surplus_features = [
        {
            "type": "Feature",
            "properties": {
                "kind": "surplus",
                "weight": _donor_surplus_weight(donor, donations),
                "name": donor.name,
                "donor_id": donor.id,
            },
            "geometry": {"type": "Point", "coordinates": [donor.location.lng, donor.location.lat]},
        }
        for donor in donors.values()
    ]
    demand_features = [
        {
            "type": "Feature",
            "properties": {
                "kind": "demand",
                "weight": max(1, int(ngo.beneficiary_count or 0)),
                "name": ngo.name,
                "ngo_id": ngo.id,
            },
            "geometry": {"type": "Point", "coordinates": [ngo.location.lng, ngo.location.lat]},
        }
        for ngo in ngos.values()
    ]

    gap_feature_list = _coverage_gap_features(donors, ngos, radius_km=radius_km, min_beneficiaries=min_ben)
    coverage_fc = {"type": "FeatureCollection", "features": gap_feature_list}

    sw = sum(f["properties"]["weight"] for f in surplus_features)
    dw = sum(f["properties"]["weight"] for f in demand_features)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "city": "Hyderabad",
        "heatmap_gap_radius_km": radius_km,
        "surplus": {"type": "FeatureCollection", "features": surplus_features},
        "demand": {"type": "FeatureCollection", "features": demand_features},
        "coverage_gaps": coverage_fc,
        "stats": {
            "donor_pins": len(surplus_features),
            "ngo_pins": len(demand_features),
            "gap_zones": len(gap_feature_list),
            "surplus_weight_total": sw,
            "demand_weight_total": dw,
        },
        "coverage_gap_summary": [
            {
                "area": g["properties"]["area"],
                "severity": g["properties"]["severity"],
                "reason": g["properties"]["reason"],
                "nearest_donor_km": g["properties"]["nearest_donor_km"],
            }
            for g in gap_feature_list
        ],
    }
