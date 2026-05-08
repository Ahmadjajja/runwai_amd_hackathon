"""
Layer 1 — Weather API client
Fetches METAR data for Toronto Pearson (CYYZ) every 15 minutes.
METAR = Meteorological Aerodrome Report — the standard aviation weather format.
"""
import requests
from typing import Dict, Any

METAR_URL = "https://aviationweather.gov/api/data/metar"
STATION   = "CYYZ"


def fetch_weather(station: str = STATION) -> Dict[str, Any]:
    """Fetch and parse latest METAR for the given station. Falls back to mock on error."""
    try:
        resp = requests.get(
            METAR_URL,
            params={"ids": station, "format": "json", "taf": "false"},
            timeout=10,
        )
        resp.raise_for_status()
        records = resp.json()
        if records:
            return _parse(records[0])
        print("[Weather] Empty response from API. Using mock data.")
    except Exception as e:
        print(f"[Weather] Error: {e}. Using mock data.")
    return _mock_weather()


def _parse(raw: Dict) -> Dict[str, Any]:
    return {
        "station":        raw.get("icaoId", STATION),
        "report_time":    raw.get("reportTime", ""),
        "wind_dir_deg":   raw.get("wdir", 0),
        "wind_speed_kts": raw.get("wspd", 0),
        "wind_gust_kts":  raw.get("wgst"),           # None if no gusts
        "visibility_sm":  raw.get("visib", 10),
        "ceiling_ft":     _ceiling(raw.get("clouds", [])),
        "conditions":     raw.get("wxString", ""),
        "temperature_c":  raw.get("temp"),
        "dewpoint_c":     raw.get("dewp"),
        "altimeter_inhg": raw.get("altim"),
        "raw_metar":      raw.get("rawOb", ""),
        "storm_warning":  _has_storm(raw),
        "low_visibility": _low_vis(raw),
    }


def _ceiling(clouds: list) -> Any:
    """Return the lowest broken/overcast layer base in feet, or None if clear."""
    for layer in (clouds or []):
        if isinstance(layer, dict) and layer.get("cover") in ("BKN", "OVC"):
            return layer.get("base")
    return None


def _has_storm(raw: Dict) -> bool:
    wx = (raw.get("wxString") or "").upper()
    return any(code in wx for code in ["TS", "TSRA", "VCTS", "GR", "SQ", "FC"])


def _low_vis(raw: Dict) -> bool:
    vis = raw.get("visib", 10)
    try:
        return float(vis) < 3
    except (TypeError, ValueError):
        return False


def _mock_weather() -> Dict[str, Any]:
    return {
        "station":        "CYYZ",
        "report_time":    "2026-05-07T17:00:00Z",
        "wind_dir_deg":   280,
        "wind_speed_kts": 12,
        "wind_gust_kts":  18,
        "visibility_sm":  10,
        "ceiling_ft":     3500,
        "conditions":     "",
        "temperature_c":  8,
        "dewpoint_c":     2,
        "altimeter_inhg": 29.98,
        "raw_metar":      "CYYZ 071700Z 28012G18KT 15SM FEW035 BKN090 08/02 A2998",
        "storm_warning":  False,
        "low_visibility": False,
    }
