"""
Layer 6 — Action Validator

Sanity-checks the model's recommended action:
1. Target flight exists
2. Target flight is airborne
3. Action type makes sense for the violation
4. Value is parseable and within sane bounds
"""

import re
from typing import Tuple, Optional

from ..preprocessing import TickData, RulesEngineOutput, ModelResponse


def parse_action_value(value: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Parse action value string like "+15deg", "-1000ft", "+20kt".
    
    Returns:
        (unit, numeric_value, error) - error is None on success
    """
    if value is None:
        return None, None, None
    
    value = value.strip().lower()
    
    patterns = [
        (r'^([+-]?\d+(?:\.\d+)?)\s*deg(?:rees)?$', 'deg'),
        (r'^([+-]?\d+(?:\.\d+)?)\s*ft$', 'ft'),
        (r'^([+-]?\d+(?:\.\d+)?)\s*kt(?:s)?$', 'kt'),
    ]
    
    for pattern, unit in patterns:
        match = re.match(pattern, value)
        if match:
            return unit, float(match.group(1)), None
    
    return None, None, f"Cannot parse value: {value}"


def validate_action(
    response: ModelResponse,
    tick: TickData,
    rules_output: RulesEngineOutput,
) -> Tuple[bool, str]:
    """
    Validate the model's recommended action.
    
    Returns:
        (True, "Valid") on success
        (False, "reason") on failure
    """
    # No action recommended - valid for no-violation scenarios
    if response.recommended_action is None:
        if rules_output.violations:
            return False, "Model recommended no action but violations exist"
        return True, "No action needed - no violations"
    
    action = response.recommended_action
    
    # Check 1: Target flight exists
    flight_callsigns = {f.callsign for f in tick.flights}
    if action.target_flight not in flight_callsigns:
        return False, f"Target flight '{action.target_flight}' not found. Available: {flight_callsigns}"
    
    # Check 2: Target flight is airborne
    target = next(f for f in tick.flights if f.callsign == action.target_flight)
    if target.on_ground:
        return False, f"Target flight '{action.target_flight}' is on ground - cannot issue airborne instruction"
    
    # Check 3: Action type relevance (soft check - warn but don't reject)
    notes = []
    if rules_output.violations:
        top_violation = rules_output.violations[0]
        
        if top_violation.rule == "wake_turbulence":
            # For wake turbulence, follower should change, not leader
            if action.target_flight == top_violation.flights[0]:  # Leader
                notes.append("Warning: Targeting leader aircraft for wake turbulence - typically follower should maneuver")
        
        if top_violation.rule == "storm_avoidance" and action.type == "altitude_change":
            notes.append("Warning: Altitude change may not resolve storm avoidance - consider heading change")
    
    # Check 4: Parse and validate value bounds
    if action.value:
        unit, num_val, err = parse_action_value(action.value)
        if err:
            return False, err
        
        if unit == 'deg' and num_val is not None:
            if abs(num_val) > 90:
                return False, f"Heading change {num_val}° exceeds safe limit of ±90°"
        
        if unit == 'ft' and num_val is not None:
            if abs(num_val) > 5000:
                return False, f"Altitude change {num_val}ft exceeds safe limit of ±5000ft"
        
        if unit == 'kt' and num_val is not None:
            if abs(num_val) > 100:
                return False, f"Speed change {num_val}kt exceeds safe limit of ±100kt"
    
    # Check 5: Hold action shouldn't have a value
    if action.type == "hold" and action.value:
        notes.append("Note: Hold action has value specified - value will be ignored")
    
    result_msg = "Valid"
    if notes:
        result_msg += " - " + "; ".join(notes)
    
    return True, result_msg
