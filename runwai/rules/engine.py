"""
Rules Engine - Orchestrates all rule checks.

This is the main entry point for Layer 5. It:
1. Takes a TickData object
2. Runs all rules against it
3. Returns a RulesEngineOutput with all violations sorted by confidence
"""

from ..preprocessing import TickData, RulesEngineOutput, Violation
from .separation import check_minimum_separation
from .storm import check_storm_avoidance
from .wake_turbulence import check_wake_turbulence


RULES_REGISTRY = [
    "minimum_separation",
    "storm_avoidance",
    "wake_turbulence",
]


def run_all_rules(tick: TickData) -> RulesEngineOutput:
    """
    Execute all rules against the current tick data.
    
    Args:
        tick: The combined tick data (flights, weather, storm sectors)
    
    Returns:
        RulesEngineOutput containing all violations sorted by confidence (highest first)
    """
    all_violations: list[Violation] = []
    
    separation_violations = check_minimum_separation(tick.flights)
    all_violations.extend(separation_violations)
    
    storm_violations = check_storm_avoidance(
        tick.flights,
        tick.weather,
        tick.storm_sectors,
    )
    all_violations.extend(storm_violations)
    
    wake_violations = check_wake_turbulence(tick.flights)
    all_violations.extend(wake_violations)
    
    all_violations.sort(key=lambda v: v.confidence, reverse=True)
    
    return RulesEngineOutput(
        tick_id=tick.tick_id,
        violations=all_violations,
        rules_evaluated=RULES_REGISTRY,
    )
