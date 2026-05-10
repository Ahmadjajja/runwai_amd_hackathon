"""
Rule 3: Wake Turbulence

Trigger: A light or medium aircraft is following a heavy aircraft
within 6 NM and at or below the heavy's altitude (within 1000 ft below).

Note: Uses weight_class from FR24 enrichment ("Heavy"/"Medium"/"Light").
"""

import math
from typing import TYPE_CHECKING

from .wake_lookup import get_weight_class

if TYPE_CHECKING:
    from ..preprocessing import Flight, Violation


MIN_TRAIL_DISTANCE_NM = 6.0
MAX_ALT_BELOW_FT = 1000.0
BEARING_TOLERANCE_DEG = 30.0


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in nautical miles."""
    R_NM = 3440.065
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad)*math.cos(lat2_rad)*math.sin(dlon/2)**2
    return R_NM * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate initial bearing from point 1 to point 2 in degrees (0-360).
    """
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    dlon_rad = math.radians(lon2 - lon1)
    
    x = math.sin(dlon_rad) * math.cos(lat2_rad)
    y = (math.cos(lat1_rad) * math.sin(lat2_rad) -
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad))
    
    bearing = math.atan2(x, y)
    return (math.degrees(bearing) + 360) % 360


def normalize_angle(angle: float) -> float:
    """Normalize angle to -180 to 180 range."""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def is_following(leader: "Flight", follower: "Flight") -> bool:
    """
    Check if follower is roughly behind leader (in the wake zone).
    
    Follower must be within ±30° of directly behind the leader's heading.
    """
    bearing_leader_to_follower = bearing_deg(
        leader.latitude, leader.longitude,
        follower.latitude, follower.longitude
    )
    
    behind_bearing = (leader.heading_deg + 180) % 360
    
    angle_diff = abs(normalize_angle(bearing_leader_to_follower - behind_bearing))
    
    return angle_diff <= BEARING_TOLERANCE_DEG


def compute_severity(confidence: float) -> str:
    if confidence >= 0.7:
        return "red"
    elif confidence >= 0.3:
        return "yellow"
    return "green"


def check_wake_turbulence(flights: list["Flight"]) -> list["Violation"]:
    """
    Check all flight pairs for wake turbulence violations.
    
    Only checks airborne aircraft.
    
    A violation occurs when:
    1. Leader is Heavy
    2. Follower is Medium or Light
    3. Follower is behind leader (within bearing tolerance)
    4. Trail distance < 6 NM
    5. Follower is at or below leader's altitude (within 1000 ft)
    """
    from ..preprocessing import Violation
    
    violations = []
    
    # Filter to airborne flights only
    airborne = [f for f in flights if not f.on_ground]
    
    for leader in airborne:
        # Get weight class from enrichment or lookup from aircraft_code
        leader_weight = leader.weight_class or get_weight_class(leader.aircraft_code)
        
        if leader_weight != "Heavy":
            continue
        
        for follower in airborne:
            if follower.callsign == leader.callsign:
                continue
            
            follower_weight = follower.weight_class or get_weight_class(follower.aircraft_code)
            
            if follower_weight not in ("Medium", "Light"):
                continue
            
            if not is_following(leader, follower):
                continue
            
            trail_distance = haversine_nm(
                leader.latitude, leader.longitude,
                follower.latitude, follower.longitude
            )
            
            if trail_distance >= MIN_TRAIL_DISTANCE_NM:
                continue
            
            # Use converted altitudes (meters → feet)
            alt_below = leader.alt_ft - follower.alt_ft
            
            if not (0 <= alt_below <= MAX_ALT_BELOW_FT):
                continue
            
            confidence = max(0.0, min(1.0, 1 - trail_distance / MIN_TRAIL_DISTANCE_NM))
            
            # Light aircraft at higher risk
            if follower_weight == "Light":
                confidence = min(1.0, confidence + 0.2)
            
            violations.append(Violation(
                rule="wake_turbulence",
                flights=[leader.callsign, follower.callsign],
                evidence={
                    "leader_weight_class": leader_weight,
                    "follower_weight_class": follower_weight,
                    "trail_distance_nm": round(trail_distance, 2),
                    "alt_below_ft": round(alt_below, 0),
                    "min_required_distance_nm": MIN_TRAIL_DISTANCE_NM,
                },
                confidence=round(confidence, 3),
                severity=compute_severity(confidence),
            ))
    
    return violations
