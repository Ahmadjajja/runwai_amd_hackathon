"""
Layer 1 — OpenSky API client
Polls live flight positions around Toronto Pearson (CYYZ) every few seconds.
"""
import requests
from dataclasses import dataclass
from typing import List, Optional

# Bounding box around Toronto Pearson (CYYZ) — roughly 80km radius
CYYZ_BOUNDS = {
    "lamin": 43.2,
    "lomin": -80.5,
    "lamax": 44.4,
    "lomax": -78.8,
}

OPENSKY_URL = "https://opensky-network.org/api/states/all"

# State vector field indices from OpenSky API docs
IDX_ICAO24          = 0
IDX_CALLSIGN        = 1
IDX_LONGITUDE       = 5
IDX_LATITUDE        = 6
IDX_BARO_ALT_M      = 7
IDX_ON_GROUND       = 8
IDX_VELOCITY_MS     = 9
IDX_TRUE_TRACK_DEG  = 10
IDX_VERTICAL_RATE   = 11


@dataclass
class FlightState:
    icao24: str
    callsign: str
    latitude: float
    longitude: float
    baro_altitude_m: float
    velocity_ms: float
    true_track_deg: float
    vertical_rate_ms: float
    on_ground: bool


def fetch_flights(bounds: dict = CYYZ_BOUNDS) -> List[FlightState]:
    """Fetch current flight states from OpenSky. Falls back to mock data on error."""
    try:
        resp = requests.get(OPENSKY_URL, params=bounds, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return _parse_states(data.get("states") or [])
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            print("[OpenSky] Rate limited (429). Using mock data.")
        else:
            print(f"[OpenSky] HTTP error: {e}. Using mock data.")
    except Exception as e:
        print(f"[OpenSky] Error: {e}. Using mock data.")
    return _mock_flights()


def _parse_states(states: list) -> List[FlightState]:
    flights = []
    for s in states:
        # Skip aircraft with no position fix
        if s[IDX_LONGITUDE] is None or s[IDX_LATITUDE] is None:
            continue
        flights.append(FlightState(
            icao24=s[IDX_ICAO24] or "",
            callsign=(s[IDX_CALLSIGN] or "UNKNOWN").strip(),
            longitude=s[IDX_LONGITUDE],
            latitude=s[IDX_LATITUDE],
            baro_altitude_m=s[IDX_BARO_ALT_M] or 0.0,
            on_ground=bool(s[IDX_ON_GROUND]),
            velocity_ms=s[IDX_VELOCITY_MS] or 0.0,
            true_track_deg=s[IDX_TRUE_TRACK_DEG] or 0.0,
            vertical_rate_ms=s[IDX_VERTICAL_RATE] or 0.0,
        ))
    return flights


def _mock_flights() -> List[FlightState]:
    """Realistic mock flights around CYYZ for testing when API is unavailable."""
    return [
        FlightState("c05120", "AC101",  43.680, -79.630, 914.4,  128.6, 270.0, -5.1, False),
        FlightState("c06a3b", "WJA202", 43.720, -79.580, 609.6,  154.3, 180.0, -8.2, False),
        FlightState("a3f2c1", "UAL303", 43.650, -79.710, 304.8,   77.2,  90.0, -3.5, False),
        FlightState("c07d5e", "DAL404", 43.610, -79.550, 1524.0, 205.1, 355.0,  0.0, False),
        FlightState("c04891", "ACA521", 43.760, -79.620, 1219.2, 180.5, 200.0, -6.0, False),
        FlightState("c09f12", "TOM678", 43.640, -79.680,  457.2,  92.0, 350.0,  2.0, False),
    ]
