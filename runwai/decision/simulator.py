"""
Layer 6 — Action Simulator

Simulates applying an action to an aircraft and checks if it creates new conflicts.
Projects all aircraft forward in time, applies the action, re-runs rules engine.
"""

import copy
import math
from typing import Tuple, List

from ..preprocessing import TickData, Flight, RecommendedAction, Violation, RulesEngineOutput
from ..rules import run_all_rules
from .validator import parse_action_value


PROJECTION_SECONDS = 60  # How far to project aircraft


def apply_action_to_flight(flight: Flight, action: RecommendedAction) -> Flight:
    """
    Apply the recommended action to a flight, returning a modified copy.
    """
    # Create a dict copy of the flight data
    flight_dict = flight.model_dump()
    
    if action.type == "heading_change":
        _, delta, _ = parse_action_value(action.value)
        if delta is not None:
            flight_dict["true_track_deg"] = (flight.true_track_deg + delta) % 360
    
    elif action.type == "altitude_change":
        _, delta_ft, _ = parse_action_value(action.value)
        if delta_ft is not None:
            # Convert delta from feet to meters (Layer 1 uses meters)
            delta_m = delta_ft / 3.28084
            flight_dict["baro_altitude_m"] = flight.baro_altitude_m + delta_m
            # Adjust vertical rate to reflect climb/descent
            if delta_ft > 0:
                flight_dict["vertical_rate_ms"] = 5.0  # ~1000 fpm climb
            elif delta_ft < 0:
                flight_dict["vertical_rate_ms"] = -5.0  # ~1000 fpm descent
    
    elif action.type == "speed_change":
        _, delta_kt, _ = parse_action_value(action.value)
        if delta_kt is not None:
            # Convert delta from knots to m/s
            delta_ms = delta_kt / 1.94384
            new_vel = max(50 / 1.94384, flight.velocity_ms + delta_ms)  # Min 50kt
            flight_dict["velocity_ms"] = new_vel
    
    elif action.type == "hold":
        # For hold, significantly reduce speed (orbit pattern)
        flight_dict["velocity_ms"] = flight.velocity_ms * 0.5
    
    return Flight(**flight_dict)


def project_flight(flight: Flight, seconds: float) -> Flight:
    """
    Project a flight forward in time based on current heading/speed/vertical rate.
    """
    flight_dict = flight.model_dump()
    
    # Distance traveled in nautical miles
    distance_nm = (flight.velocity_kt / 3600) * seconds
    
    # Earth radius in NM
    R_NM = 3440.065
    
    # Project position
    lat_rad = math.radians(flight.latitude)
    heading_rad = math.radians(flight.heading_deg)
    angular_dist = distance_nm / R_NM
    
    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(angular_dist) +
        math.cos(lat_rad) * math.sin(angular_dist) * math.cos(heading_rad)
    )
    new_lon_rad = math.radians(flight.longitude) + math.atan2(
        math.sin(heading_rad) * math.sin(angular_dist) * math.cos(lat_rad),
        math.cos(angular_dist) - math.sin(lat_rad) * math.sin(new_lat_rad)
    )
    
    flight_dict["latitude"] = math.degrees(new_lat_rad)
    flight_dict["longitude"] = math.degrees(new_lon_rad)
    
    # Project altitude
    alt_change_m = flight.vertical_rate_ms * seconds
    flight_dict["baro_altitude_m"] = max(0, flight.baro_altitude_m + alt_change_m)
    
    return Flight(**flight_dict)


def simulate_action(
    tick: TickData,
    action: RecommendedAction,
    original_violations: List[Violation],
    projection_seconds: float = PROJECTION_SECONDS,
) -> Tuple[bool, List[Violation], str]:
    """
    Simulate applying an action and check for new conflicts.
    
    Args:
        tick: Current tick data
        action: The action to simulate
        original_violations: Violations from current state
        projection_seconds: How far to project (default 60s)
    
    Returns:
        (creates_new_conflict, new_violations, notes)
    """
    # Deep copy tick data
    projected_tick = TickData(
        tick_id=tick.tick_id + "_projected",
        timestamp=tick.timestamp,
        airport=tick.airport,
        flights=[],
        weather=tick.weather,
        storm_sectors=tick.storm_sectors,
    )
    
    # Project all flights forward
    for flight in tick.flights:
        if flight.callsign == action.target_flight:
            # Apply action first, then project
            modified = apply_action_to_flight(flight, action)
            projected = project_flight(modified, projection_seconds)
        else:
            # Just project
            projected = project_flight(flight, projection_seconds)
        
        projected_tick.flights.append(projected)
    
    # Run rules on projected state
    projected_rules_output = run_all_rules(projected_tick)
    
    # Find NEW violations (not in original)
    original_pairs = {
        (v.rule, tuple(sorted(v.flights)))
        for v in original_violations
    }
    
    new_violations = [
        v for v in projected_rules_output.violations
        if (v.rule, tuple(sorted(v.flights))) not in original_pairs
    ]
    
    if new_violations:
        conflict_desc = "; ".join(
            f"{v.rule} involving {', '.join(v.flights)}"
            for v in new_violations
        )
        return True, new_violations, f"Action creates new conflict: {conflict_desc}"
    
    # Check if original violations are resolved
    resolved_count = len(original_violations) - len([
        v for v in projected_rules_output.violations
        if (v.rule, tuple(sorted(v.flights))) in original_pairs
    ])
    
    notes = f"Projected {projection_seconds}s forward. "
    if resolved_count > 0:
        notes += f"{resolved_count} violation(s) would be resolved."
    else:
        notes += "Violations would persist but not worsen."
    
    return False, [], notes
