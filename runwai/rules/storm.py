"""
Rule 2: Storm Avoidance

Trigger: Aircraft projected to enter hazardous weather sector within 60 seconds,
or approaching airport while storm_warning is True.

Note: Uses storm_warning boolean from Layer 1 weather data.
"""

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..preprocessing import Flight, Weather, StormSector, Violation


PROJECTION_SECONDS = 60
AIRPORT_STORM_RADIUS_NM = 20.0


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in nautical miles."""
    R_NM = 3440.065
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad)*math.cos(lat2_rad)*math.sin(dlon/2)**2
    return R_NM * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def project_position(lat: float, lon: float, heading_deg: float, 
                     velocity_kt: float, seconds: float) -> tuple[float, float]:
    """
    Project aircraft position forward in time.
    Returns (new_lat, new_lon).
    """
    distance_nm = (velocity_kt / 3600) * seconds
    
    R_NM = 3440.065
    lat_rad = math.radians(lat)
    heading_rad = math.radians(heading_deg)
    
    angular_dist = distance_nm / R_NM
    
    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(angular_dist) +
        math.cos(lat_rad) * math.sin(angular_dist) * math.cos(heading_rad)
    )
    new_lon_rad = math.radians(lon) + math.atan2(
        math.sin(heading_rad) * math.sin(angular_dist) * math.cos(lat_rad),
        math.cos(angular_dist) - math.sin(lat_rad) * math.sin(new_lat_rad)
    )
    
    return math.degrees(new_lat_rad), math.degrees(new_lon_rad)


def point_in_polygon(lat: float, lon: float, polygon: list[list[float]]) -> bool:
    """
    Ray-casting algorithm for point-in-polygon test.
    Polygon is a list of [lat, lon] pairs.
    """
    n = len(polygon)
    if n < 3:
        return False
    
    inside = False
    j = n - 1
    
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    
    return inside


def compute_severity(confidence: float) -> str:
    if confidence >= 0.7:
        return "red"
    elif confidence >= 0.3:
        return "yellow"
    return "green"


def check_storm_avoidance(
    flights: list["Flight"],
    weather: "Weather",
    storm_sectors: list["StormSector"],
    airport_lat: float = 43.6772,
    airport_lon: float = -79.6306,
) -> list["Violation"]:
    """
    Check if any flights are heading into storm areas.
    
    Only checks airborne aircraft.
    Uses storm_warning boolean from Layer 1 weather.
    """
    from ..preprocessing import Violation
    
    violations = []
    
    # Check if storm conditions exist
    has_storm = weather.storm_warning or len(storm_sectors) > 0
    if not has_storm:
        return violations
    
    # Filter to airborne flights only
    airborne = [f for f in flights if not f.on_ground]
    
    for flight in airborne:
        # Use converted velocity (m/s → knots)
        proj_lat, proj_lon = project_position(
            flight.latitude, flight.longitude,
            flight.heading_deg, flight.velocity_kt,
            PROJECTION_SECONDS
        )
        
        # Check storm sectors first
        for sector in storm_sectors:
            if point_in_polygon(proj_lat, proj_lon, sector.polygon):
                confidence = 1.0 if sector.severity == "severe" else 0.7
                violations.append(Violation(
                    rule="storm_avoidance",
                    flights=[flight.callsign],
                    evidence={
                        "storm_warning": weather.storm_warning,
                        "sector": sector.sector,
                        "sector_severity": sector.severity,
                        "projected_position": [round(proj_lat, 4), round(proj_lon, 4)],
                        "projection_seconds": PROJECTION_SECONDS,
                    },
                    confidence=confidence,
                    severity=compute_severity(confidence),
                ))
                break
        else:
            # No sector polygon hit, but storm_warning is active
            if weather.storm_warning:
                current_dist = haversine_nm(flight.latitude, flight.longitude, airport_lat, airport_lon)
                proj_dist = haversine_nm(proj_lat, proj_lon, airport_lat, airport_lon)
                
                # Flight is approaching airport during storm
                if proj_dist < AIRPORT_STORM_RADIUS_NM and proj_dist < current_dist:
                    confidence = max(0.3, min(1.0, 1 - proj_dist / AIRPORT_STORM_RADIUS_NM))
                    violations.append(Violation(
                        rule="storm_avoidance",
                        flights=[flight.callsign],
                        evidence={
                            "storm_warning": True,
                            "sector": "airport_vicinity",
                            "current_distance_nm": round(current_dist, 2),
                            "projected_distance_nm": round(proj_dist, 2),
                            "storm_radius_nm": AIRPORT_STORM_RADIUS_NM,
                        },
                        confidence=round(confidence, 3),
                        severity=compute_severity(confidence),
                    ))
    
    return violations
