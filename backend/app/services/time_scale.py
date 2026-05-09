from __future__ import annotations

from datetime import timedelta

from app.core.config import get_settings


def scaled_minutes(minutes: float) -> float:
    acceleration = max(1.0, float(get_settings().timer_acceleration or 1.0))
    return float(minutes) / acceleration


def scaled_timedelta_minutes(minutes: float) -> timedelta:
    return timedelta(minutes=scaled_minutes(minutes))


def logical_minutes_from_timedelta(delta_seconds: float) -> int:
    acceleration = max(1.0, float(get_settings().timer_acceleration or 1.0))
    return max(0, int((delta_seconds / 60.0) * acceleration))
