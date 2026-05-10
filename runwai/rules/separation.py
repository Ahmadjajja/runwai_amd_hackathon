"""
Rule 1: Minimum Separation

Trigger: Two aircraft are within 5 NM horizontal AND within 1000 ft vertical.
This is the most critical safety rule in ATC.

Note: Uses converted units from Flight properties (alt_ft, velocity_kt).
"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..preprocessing import Flight, Violation


# Thresholds
MIN_HORIZONTAL_SEPARATION_NM = 5.0
MIN_VERTICAL_SEPARATION_FT = 1000.0


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points in nautical miles.
    """
    R_NM = 3440.065  # Earth radius in nautical miles
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R_NM * c


def compute_severity(confidence: float) -> str:
    """Map confidence to severity bucket."""
    if confidence >= 0.7:
        return "red"
    elif confidence >= 0.3:
        return "yellow"
    return "green"


def check_minimum_separation(flights: list["Flight"]) -> list["Violation"]:
    """
    Check all flight pairs for separation violations.
    
    Only checks airborne aircraft (on_ground == False).
    Returns a list of violations, one per pair that violates the rule.
    """
    from ..preprocessing import Violation
    
    violations = []
    
    # Filter to airborne flights only
    airborne = [f for f in flights if not f.on_ground]
    n = len(airborne)
    
    for i in range(n):
        for j in range(i + 1, n):
            flight_a = airborne[i]
            flight_b = airborne[j]
            
            distance_nm = haversine_nm(
                flight_a.latitude, flight_a.longitude,
                flight_b.latitude, flight_b.longitude
            )
            
            # Use converted altitude (meters → feet)
            alt_diff_ft = abs(flight_a.alt_ft - flight_b.alt_ft)
            
            horizontal_violated = distance_nm < MIN_HORIZONTAL_SEPARATION_NM
            vertical_violated = alt_diff_ft < MIN_VERTICAL_SEPARATION_FT
            
            if horizontal_violated and vertical_violated:
                confidence = max(0.0, min(1.0, 1 - distance_nm / MIN_HORIZONTAL_SEPARATION_NM))
                
                violations.append(Violation(
                    rule="minimum_separation",
                    flights=[flight_a.callsign, flight_b.callsign],
                    evidence={
                        "distance_nm": round(distance_nm, 2),
                        "alt_diff_ft": round(alt_diff_ft, 0),
                        "min_required_distance_nm": MIN_HORIZONTAL_SEPARATION_NM,
                        "min_required_alt_diff_ft": MIN_VERTICAL_SEPARATION_FT,
                    },
                    confidence=round(confidence, 3),
                    severity=compute_severity(confidence),
                ))
    
    return violations
