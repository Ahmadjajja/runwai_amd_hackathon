"""
Convert Layer 7 (browser) simulation export JSON into TickData for the Python rules engine.

Units in export (frontend): ft, kt, fpm, deg — converted to OpenSky-style Flight fields (m, m/s).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from .schemas import Flight, Weather, TickData, METERS_TO_FEET, MS_TO_KNOTS, MS_TO_FPM
from .formatter import create_tick_data


def _icao24_stub(callsign: str) -> str:
    """Stable 6-char hex id for simulation flights (no real ICAO24)."""
    return hashlib.md5(callsign.strip().encode("utf-8"), usedforsecurity=False).hexdigest()[:6]


def _flight_from_sim_export(row: dict[str, Any]) -> Flight:
    callsign = str(row.get("callsign") or row.get("id") or "UNK").strip() or "UNK"
    alt_ft = float(row.get("altitude_ft") or 0)
    v_kts = float(row.get("velocity_kts") or 0)
    vs_fpm = float(row.get("vertical_speed_fpm") or 0)
    phase = str(row.get("phase") or "")
    baro_m = alt_ft / METERS_TO_FEET
    v_ms = v_kts / MS_TO_KNOTS
    vr_ms = vs_fpm / MS_TO_FPM
    on_ground = phase.upper() == "TAXI" or alt_ft < 80

    wc = row.get("weight_class")
    if wc not in ("Heavy", "Medium", "Light", "Unknown"):
        wc = None

    return Flight(
        icao24=_icao24_stub(callsign),
        callsign=callsign,
        latitude=float(row.get("lat") or 0),
        longitude=float(row.get("lon") or 0),
        baro_altitude_m=baro_m,
        velocity_ms=v_ms,
        true_track_deg=float(row.get("heading_deg") or 0),
        vertical_rate_ms=vr_ms,
        on_ground=on_ground,
        aircraft_code=row.get("aircraft_code"),
        weight_class=wc,
    )


def weather_from_sim_export(w: dict[str, Any]) -> Weather:
    storm_sectors = w.get("storm_sectors") or []
    phenomenon = w.get("phenomenon")
    storm_warning = bool(storm_sectors) or bool(phenomenon)
    ceiling = w.get("ceiling_ft")
    return Weather(
        station="CYYZ",
        report_time=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
        wind_dir_deg=float(w.get("wind_dir_deg") or 0),
        wind_speed_kts=float(w.get("wind_speed_kts") or 0),
        wind_gust_kts=w.get("wind_gust_kts"),
        visibility_sm=float(w.get("visibility_sm") or 10),
        ceiling_ft=float(ceiling) if ceiling is not None else None,
        storm_warning=storm_warning,
        low_visibility=float(w.get("visibility_sm") or 10) < 3,
        conditions=str(phenomenon) if phenomenon else None,
    )


def tick_from_frontend_export(data: dict[str, Any]) -> TickData:
    """
    Build TickData from getSimulationExport() / window.__runwaiTrainingExport JSON shape.
    """
    raw_flights = data.get("aircraft") or []
    flights = [_flight_from_sim_export(f) for f in raw_flights]

    wx_raw = data.get("weather") or {}
    weather = weather_from_sim_export(wx_raw)

    tick_id = f"sim-{data.get('exported_at_ms') or uuid.uuid4().hex[:12]}"

    return create_tick_data(flights, weather, airport="CYYZ", tick_id=tick_id)
