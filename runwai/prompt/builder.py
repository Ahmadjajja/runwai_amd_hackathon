"""
Prompt Builder - Assembles the final prompt for the VLM.

Takes:
- Tick data (flights, weather)
- Rules engine output (violations)
- Visual context (placeholder for now)

Returns:
- A single formatted string ready to send to the model
"""

import json
from ..preprocessing import TickData, RulesEngineOutput
from .templates import (
    SYSTEM_ROLE,
    RULE_DEFINITIONS,
    OUTPUT_SCHEMA,
    VISUAL_CONTEXT_PLACEHOLDER,
)


def format_tick_data(tick: TickData) -> str:
    """Format tick data as readable JSON with converted units for clarity."""
    data = {
        "tick_id": tick.tick_id,
        "timestamp": tick.timestamp,
        "airport": tick.airport,
        "flights": [
            {
                "callsign": f.callsign,
                "position": {"lat": f.latitude, "lon": f.longitude},
                "altitude_ft": round(f.alt_ft, 0),  # converted from meters
                "speed_kt": round(f.velocity_kt, 0),  # converted from m/s
                "heading_deg": f.heading_deg,
                "vertical_rate_fpm": round(f.vertical_rate_fpm, 0),
                "on_ground": f.on_ground,
                "aircraft_code": f.aircraft_code,
                "weight_class": f.weight_class,
            }
            for f in tick.flights
        ],
        "weather": {
            "station": tick.weather.station,
            "raw_metar": tick.weather.raw_metar,
            "wind": f"{tick.weather.wind_speed_kts}kt @ {tick.weather.wind_dir_deg}°",
            "visibility_sm": tick.weather.visibility_sm,
            "ceiling_ft": tick.weather.ceiling_ft,
            "storm_warning": tick.weather.storm_warning,
            "low_visibility": tick.weather.low_visibility,
        },
    }
    return json.dumps(data, indent=2)


def format_violations(rules_output: RulesEngineOutput) -> str:
    """Format rules engine output as readable text."""
    if not rules_output.violations:
        return "No violations detected. All aircraft are maintaining safe separation and avoiding hazards."
    
    lines = [f"{len(rules_output.violations)} violation(s) detected:\n"]
    
    for i, v in enumerate(rules_output.violations, 1):
        lines.append(f"{i}. [{v.severity.upper()}] {v.rule}")
        lines.append(f"   Aircraft involved: {', '.join(v.flights)}")
        lines.append(f"   Evidence:")
        for key, value in v.evidence.items():
            lines.append(f"     - {key}: {value}")
        lines.append(f"   Confidence: {v.confidence:.1%}")
        lines.append("")
    
    return "\n".join(lines)


def build_prompt(
    tick: TickData,
    rules_output: RulesEngineOutput,
    visual_context: str | None = None,
) -> str:
    """
    Assemble the complete prompt for the VLM.
    
    Args:
        tick: Current tick data
        rules_output: Output from the rules engine
        visual_context: Description of the video frame (placeholder if None)
    
    Returns:
        Complete formatted prompt string
    """
    sections = [
        ("SYSTEM ROLE", SYSTEM_ROLE),
        ("RULE DEFINITIONS", RULE_DEFINITIONS),
        ("CURRENT TICK DATA", format_tick_data(tick)),
        ("RULES ENGINE OUTPUT", format_violations(rules_output)),
        ("VISUAL CONTEXT", visual_context or VISUAL_CONTEXT_PLACEHOLDER),
        ("OUTPUT FORMAT", OUTPUT_SCHEMA),
    ]
    
    prompt_parts = []
    for section_name, section_content in sections:
        prompt_parts.append(f"=== {section_name} ===\n{section_content.strip()}\n")
    
    return "\n".join(prompt_parts)
