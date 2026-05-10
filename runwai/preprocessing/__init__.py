"""
Layer 2 - Preprocessing / JSON Formatting

This module handles:
- Converting raw data from Layer 1 into validated Pydantic models
- Unit conversions (meters -> feet, m/s -> knots)
- Merging flight data with enrichment data
- Creating the TickData structure for downstream processing
"""

from .schemas import (
    Flight,
    Weather,
    StormSector,
    RunwayStatus,
    TickData,
    Violation,
    RulesEngineOutput,
    RecommendedAction,
    ModelResponse,
    ValidatedDecision,
    METERS_TO_FEET,
    MS_TO_KNOTS,
    MS_TO_FPM,
)

from .formatter import (
    create_tick_data,
    flights_from_opensky,
    weather_from_metar,
    merge_enrichment,
)

from .simulation_adapter import tick_from_frontend_export

__all__ = [
    # Schemas
    "Flight",
    "Weather", 
    "StormSector",
    "RunwayStatus",
    "TickData",
    "Violation",
    "RulesEngineOutput",
    "RecommendedAction",
    "ModelResponse",
    "ValidatedDecision",
    # Constants
    "METERS_TO_FEET",
    "MS_TO_KNOTS",
    "MS_TO_FPM",
    # Functions
    "create_tick_data",
    "flights_from_opensky",
    "weather_from_metar",
    "merge_enrichment",
    "tick_from_frontend_export",
]
