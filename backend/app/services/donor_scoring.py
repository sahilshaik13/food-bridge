from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from app.models import Donation, DonationStatus, Donor, DonorScore


def trust_tier_for_score(score: int) -> Literal["bronze", "silver", "gold", "platinum"]:
    if score >= 85:
        return "platinum"
    if score >= 65:
        return "gold"
    if score >= 40:
        return "silver"
    return "bronze"


def raw_donor_score_and_factors(donor: Donor, donations: list[Donation]) -> tuple[int, list[str]]:
    score = 20
    factors: list[str] = ["base_registration:+20"]

    if donor.fssai_license:
        score += 20
        factors.append("fssai_license:+20")

    if donor.verification_status == "verified":
        score += 10
        factors.append("verified_profile:+10")
    elif donor.verification_status == "suspended":
        score -= 20
        factors.append("suspended_profile:-20")

    donor_donations = [item for item in donations if item.donor_id == donor.id]
    completed = [item for item in donor_donations if item.status == DonationStatus.completed]
    rejected = [
        item
        for item in donor_donations
        if item.status in {DonationStatus.declined, DonationStatus.expired, DonationStatus.wasted}
    ]
    review_flagged = [item for item in donor_donations if item.status == DonationStatus.needs_review]

    completion_bonus = min(30, len(completed) * 2)
    if completion_bonus:
        score += completion_bonus
        factors.append(f"completed_donations:+{completion_bonus}")

    rejected_penalty = min(30, len(rejected) * 5)
    if rejected_penalty:
        score -= rejected_penalty
        factors.append(f"terminal_rejections:-{rejected_penalty}")

    review_penalty = min(15, len(review_flagged) * 3)
    if review_penalty:
        score -= review_penalty
        factors.append(f"manual_review_flags:-{review_penalty}")

    score = max(0, min(100, score))
    return score, factors


def compute_donor_score(donor: Donor, donations: list[Donation]) -> DonorScore:
    """Raw behavioural score + tier for one donor (no network calibration)."""
    raw, factors = raw_donor_score_and_factors(donor, donations)
    return DonorScore(
        trust_score=raw,
        trust_tier=trust_tier_for_score(raw),
        factors=factors,
        updated_at=datetime.now(timezone.utc),
    )


def _donor_jitter(donor_id: str, span: int) -> int:
    digest = hashlib.md5(donor_id.encode(), usedforsecurity=False).hexdigest()
    return int(digest[:8], 16) % span


def _resolve_trust_score_collisions(scores: dict[str, DonorScore]) -> dict[str, DonorScore]:
    used: set[int] = set()
    out: dict[str, DonorScore] = {}
    for did in sorted(scores.keys()):
        ds = scores[did]
        cand = ds.trust_score
        if cand not in used:
            used.add(cand)
            out[did] = ds.model_copy(
                update={
                    "trust_score": cand,
                    "trust_tier": trust_tier_for_score(cand),
                }
            )
            continue
        placed = cand
        for delta in range(1, 101):
            up = cand + delta
            if up <= 100 and up not in used:
                placed = up
                break
            down = cand - delta
            if down >= 0 and down not in used:
                placed = down
                break
        used.add(placed)
        out[did] = ds.model_copy(
            update={
                "trust_score": placed,
                "trust_tier": trust_tier_for_score(placed),
            }
        )
    return out


def calibrate_trust_scores_network(
    ranked_entries: list[tuple[str, int, list[str]]],
) -> dict[str, DonorScore]:
    """
    ranked_entries: donors sorted by raw score descending (best first).
    Assigns two distinct leader scores, three distinct trailing scores when possible,
    and spreads everyone else across the mid band with per-donor variation.
    """
    if not ranked_entries:
        return {}

    n = len(ranked_entries)
    now = datetime.now(timezone.utc)

    if n == 1:
        did, raw, factors = ranked_entries[0]
        raw_clamped = max(0, min(100, raw))
        return {
            did: DonorScore(
                trust_score=raw_clamped,
                trust_tier=trust_tier_for_score(raw_clamped),
                factors=factors,
                updated_at=now,
            )
        }

    assigned: dict[str, tuple[int, list[str]]] = {}

    num_top = min(2, n)
    num_bottom = min(3, max(0, n - num_top))
    middle_n = n - num_top - num_bottom

    top_scores_preset = [97, 93][:num_top]
    bottom_targets = [26, 32, 38][:num_bottom]

    for i in range(num_top):
        did, _raw, factors = ranked_entries[i]
        assigned[did] = (top_scores_preset[i], factors)

    bottom_slice = ranked_entries[n - num_bottom :] if num_bottom else []
    bottom_ordered = sorted(bottom_slice, key=lambda x: (x[1], x[0]))
    for i, (did, _raw, factors) in enumerate(bottom_ordered):
        assigned[did] = (bottom_targets[i], factors)

    middle_slice = ranked_entries[num_top : n - num_bottom] if middle_n else []
    if middle_n == 1:
        did, _r, fac = middle_slice[0]
        jitter = _donor_jitter(did, 7) - 3
        assigned[did] = (56 + jitter, fac)
    elif middle_n > 1:
        for j, (did, _raw, factors) in enumerate(middle_slice):
            span_lo, span_hi = 45, 76
            t = j / (middle_n - 1)
            base = span_lo + int(round(t * (span_hi - span_lo)))
            jitter = _donor_jitter(did, 11) - 5
            s = base + jitter
            s = max(41, min(82, s))
            assigned[did] = (s, factors)

    result: dict[str, DonorScore] = {}
    for did, (ts, fac) in assigned.items():
        ts_c = max(0, min(100, int(ts)))
        result[did] = DonorScore(
            trust_score=ts_c,
            trust_tier=trust_tier_for_score(ts_c),
            factors=fac,
            updated_at=now,
        )

    return _resolve_trust_score_collisions(result)


def recompute_all_donor_scores(donors: list[Donor], donations: list[Donation]) -> dict[str, DonorScore]:
    entries = [(d.id, *raw_donor_score_and_factors(d, donations)) for d in donors]
    entries.sort(key=lambda x: (-x[1], x[0]))
    return calibrate_trust_scores_network(entries)
