"""
Layer 6 — Sector Assignment

Assigns aircraft to CYYZ sectors based on position and altitude:
- A12: North sector (departures heading north)
- B07: East corridor
- C03: Landing approach (active conflict zone, low altitude)

CYYZ center: 43.6772°N, 79.6306°W
"""

from typing import Optional
from ..preprocessing import Flight


# CYYZ reference point
CYYZ_LAT = 43.6772
CYYZ_LON = -79.6306

# Sector boundaries (simplified)
# A12: North of 43.80°N (departures)
# B07: East of -79.40°W, between 43.60-43.80°N
# C03: Within approach corridor, altitude < 5000ft


def assign_sector(flight: Flight) -> str:
    """
    Assign a flight to its current sector based on position and altitude.
    
    Sectors:
        A12 - North departure sector (lat > 43.80)
        B07 - East corridor (lon > -79.40, 43.60 < lat < 43.80)
        C03 - Approach/landing zone (low altitude near airport)
    
    Returns:
        Sector code: "A12", "B07", "C03", or "UNKNOWN"
    """
    lat = flight.latitude
    lon = flight.longitude
    alt_ft = flight.alt_ft
    
    # A12: North sector - departures heading north
    if lat > 43.80:
        return "A12"
    
    # B07: East corridor
    if lon > -79.40 and 43.60 < lat < 43.80:
        return "B07"
    
    # C03: Approach zone - low altitude near airport
    if alt_ft < 5000 and 43.60 < lat < 43.75 and -79.70 < lon < -79.50:
        return "C03"
    
    # Default for aircraft not in defined sectors
    return "UNKNOWN"


def get_sector_info(sector: str) -> dict:
    """
    Get metadata about a sector.
    """
    sectors = {
        "A12": {
            "name": "North Departure",
            "description": "Departures heading north",
            "altitude_range": "5000-15000 ft",
            "traffic_type": "departures",
        },
        "B07": {
            "name": "East Corridor",
            "description": "East-bound traffic corridor",
            "altitude_range": "8000-12000 ft",
            "traffic_type": "transit",
        },
        "C03": {
            "name": "Approach Zone",
            "description": "Final approach and landing",
            "altitude_range": "0-5000 ft",
            "traffic_type": "arrivals",
            "conflict_risk": "high",
        },
        "UNKNOWN": {
            "name": "Unassigned",
            "description": "Outside defined sectors",
            "altitude_range": "varies",
            "traffic_type": "unknown",
        },
    }
    return sectors.get(sector, sectors["UNKNOWN"])
