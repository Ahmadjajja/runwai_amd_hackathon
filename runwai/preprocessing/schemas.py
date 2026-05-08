"""
Pydantic models for RunwAI data structures.

These schemas match the Layer 1 output format from opensky_client.py and weather_client.py.

Units from Layer 1 (OpenSky):
- Altitude: meters (baro_altitude_m)
- Velocity: m/s (velocity_ms)
- Heading: degrees (true_track_deg)
- Vertical rate: m/s (vertical_rate_ms)

Units for rules engine (converted internally):
- Distance: nautical miles (NM)
- Altitude: feet (ft)
- Speed: knots (kt)
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


# === Conversion constants ===
METERS_TO_FEET = 3.28084
MS_TO_KNOTS = 1.94384
MS_TO_FPM = 196.85  # m/s to feet per minute


# === Input Data Models (matching Layer 1 output) ===

class Flight(BaseModel):
    """
    Single aircraft state vector.
    Matches FlightState from layer1/opensky_client.py
    """
    icao24: str
    callsign: str
    latitude: float
    longitude: float
    baro_altitude_m: float  # altitude in METERS (OpenSky native)
    velocity_ms: float  # speed in m/s (OpenSky native)
    true_track_deg: float  # heading in degrees
    vertical_rate_ms: float = 0.0  # vertical rate in m/s
    on_ground: bool = False
    
    # Enrichment fields from FR24 (optional)
    aircraft_code: Optional[str] = None  # e.g., "B789", "A320"
    weight_class: Optional[Literal["Heavy", "Medium", "Light", "Unknown"]] = None
    origin_iata: Optional[str] = None
    destination_iata: Optional[str] = None
    airline_iata: Optional[str] = None

    @property
    def alt_ft(self) -> float:
        """Altitude converted to feet for rules engine."""
        return self.baro_altitude_m * METERS_TO_FEET

    @property
    def velocity_kt(self) -> float:
        """Velocity converted to knots for rules engine."""
        return self.velocity_ms * MS_TO_KNOTS

    @property
    def heading_deg(self) -> float:
        """Alias for true_track_deg."""
        return self.true_track_deg

    @property
    def vertical_rate_fpm(self) -> float:
        """Vertical rate converted to feet per minute."""
        return self.vertical_rate_ms * MS_TO_FPM


class Weather(BaseModel):
    """
    Weather data from METAR.
    Matches output from layer1/weather_client.py
    """
    station: str = "CYYZ"
    report_time: Optional[str] = None
    wind_dir_deg: float = 0
    wind_speed_kts: float = 0  # Note: Layer 1 uses kts for wind
    wind_gust_kts: Optional[float] = None
    visibility_sm: float = 10
    ceiling_ft: Optional[float] = None
    conditions: Optional[str] = None
    temperature_c: Optional[float] = None
    dewpoint_c: Optional[float] = None
    altimeter_inhg: Optional[float] = None
    raw_metar: Optional[str] = None
    storm_warning: bool = False  # Layer 1 computes this from phenomena
    low_visibility: bool = False


class StormSector(BaseModel):
    """Hazardous weather sector."""
    sector: str
    severity: Literal["light", "moderate", "severe"]
    polygon: list[list[float]]  # [[lat, lon], ...]


class RunwayStatus(BaseModel):
    """Status of a single runway."""
    free: bool
    aircraft: list[dict] = Field(default_factory=list)


class TickData(BaseModel):
    """
    Combined input for one processing tick.
    This is what the data layer hands to the rules engine.
    """
    tick_id: str
    timestamp: str
    airport: str = "CYYZ"
    flights: list[Flight]
    weather: Weather
    storm_sectors: list[StormSector] = Field(default_factory=list)
    runway_status: Optional[dict[str, RunwayStatus]] = None
    
    # Optional: frame data for video context
    frame_path: Optional[str] = None
    atc_transcript: Optional[str] = None


# === Rule Output Models ===

class Violation(BaseModel):
    """Single rule violation output."""
    rule: str
    flights: list[str]  # callsigns involved
    evidence: dict
    confidence: float = Field(ge=0.0, le=1.0)
    severity: Literal["red", "yellow", "green"]


class RulesEngineOutput(BaseModel):
    """Complete output from the rules engine."""
    tick_id: str
    violations: list[Violation]
    rules_evaluated: list[str]


# === Model Response Models ===

class RecommendedAction(BaseModel):
    """Action recommended by the model."""
    target_flight: str
    type: Literal["heading_change", "altitude_change", "speed_change", "hold"]
    value: Optional[str] = None  # e.g., "+15deg", "+1000ft", "-20kt"


class ModelResponse(BaseModel):
    """Expected response format from the VLM."""
    reasoning: str
    recommended_action: Optional[RecommendedAction] = None
    model_confidence: float = Field(ge=0.0, le=1.0)


# === Layer 6 Decision Models ===

class ValidatedDecision(BaseModel):
    """Final decision after Layer 6 validation."""
    tick_id: str
    original_violation: Optional[Violation] = None  # None if no violations
    model_response: ModelResponse
    action_valid: bool
    validation_notes: str
    assigned_sector: Optional[str] = None  # A12 / B07 / C03
    latency_ms: float
    retry_count: int = 0
