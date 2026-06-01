"""
Fetch current weather for a lat/lon using OpenWeatherMap (optional API key).
"""

from __future__ import annotations

from datetime import datetime, timezone

import requests

from app.core.config import get_settings
from app.models import WeatherSnapshot

OWM_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"


def fetch_weather_at_listing(lat: float, lon: float) -> WeatherSnapshot | None:
    """
    Returns None if API key is unset, request fails, or response is invalid.
    """
    key = get_settings().openweathermap_api_key
    if not (key and str(key).strip()):
        return None
    try:
        r = requests.get(
            OWM_CURRENT_URL,
            params={"lat": lat, "lon": lon, "appid": str(key).strip(), "units": "metric"},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        print(f"OpenWeatherMap request failed: {exc}")
        return None

    try:
        main = data.get("main") or {}
        wind = data.get("wind") or {}
        w0 = (data.get("weather") or [{}])[0] if isinstance(data.get("weather"), list) else {}
        coord = data.get("coord") or {}
        desc = (w0.get("description") or w0.get("main") or "").strip() or None
        temp = main.get("temp")
        if temp is None:
            return None
        fl = main.get("feels_like")
        hum = main.get("humidity")
        spd = wind.get("speed")
        return WeatherSnapshot(
            fetched_at=datetime.now(timezone.utc),
            temp_c=float(temp),
            feels_like_c=float(fl) if fl is not None else None,
            humidity_percent=int(hum) if hum is not None else None,
            conditions=desc,
            wind_speed_m_s=float(spd) if spd is not None else None,
            lat=float(coord.get("lat", lat)),
            lon=float(coord.get("lon", lon)),
        )
    except Exception as exc:
        print(f"OpenWeatherMap parse failed: {exc}")
        return None
