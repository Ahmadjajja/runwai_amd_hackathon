"""
Layer 2 - JSON Formatter

Converts raw Layer 1 data into validated TickData structures.
Handles:
- OpenSky flight states -> Flight models
- METAR data -> Weather model
- FR24 enrichment -> Weight class/aircraft type
- Storm sector creation
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import uuid

from .schemas import Flight, Weather, StormSector, TickData


def flights_from_opensky(opensky_states: List[Any]) -> List[Flight]:
    """
    Convert OpenSky FlightState objects to Flight models.
    
    Args:
        opensky_states: List of FlightState dataclass instances from opensky_client
    
    Returns:
        List of Flight Pydantic models
    """
    flights = []
    for state in opensky_states:
        try:
            flight = Flight(
                icao24=getattr(state, 'icao24', ''),
                callsign=getattr(state, 'callsign', 'UNKNOWN'),
                latitude=getattr(state, 'latitude', 0.0),
                longitude=getattr(state, 'longitude', 0.0),
                baro_altitude_m=getattr(state, 'baro_altitude_m', 0.0),
                velocity_ms=getattr(state, 'velocity_ms', 0.0),
                true_track_deg=getattr(state, 'true_track_deg', 0.0),
                vertical_rate_ms=getattr(state, 'vertical_rate_ms', 0.0),
                on_ground=getattr(state, 'on_ground', False),
            )
            flights.append(flight)
        except Exception as e:
            print(f"[Formatter] Error parsing flight {state}: {e}")
    
    return flights


def weather_from_metar(metar_data: Dict[str, Any]) -> Weather:
    """
    Convert METAR dict from weather_client to Weather model.
    
    Args:
        metar_data: Dict from weather_client.fetch_weather()
    
    Returns:
        Weather Pydantic model
    """
    return Weather(
        station=metar_data.get('station', 'CYYZ'),
        report_time=metar_data.get('report_time'),
        wind_dir_deg=metar_data.get('wind_dir_deg', 0),
        wind_speed_kts=metar_data.get('wind_speed_kts', 0),
        wind_gust_kts=metar_data.get('wind_gust_kts'),
        visibility_sm=metar_data.get('visibility_sm', 10),
        ceiling_ft=metar_data.get('ceiling_ft'),
        conditions=metar_data.get('conditions'),
        temperature_c=metar_data.get('temperature_c'),
        dewpoint_c=metar_data.get('dewpoint_c'),
        altimeter_inhg=metar_data.get('altimeter_inhg'),
        raw_metar=metar_data.get('raw_metar'),
        storm_warning=metar_data.get('storm_warning', False),
        low_visibility=metar_data.get('low_visibility', False),
    )


def merge_enrichment(flights: List[Flight], enrichment_map: Dict[str, Dict]) -> List[Flight]:
    """
    Merge FR24 enrichment data (aircraft type, weight class) into flights.
    
    Args:
        flights: List of Flight models
        enrichment_map: Dict keyed by callsign with enrichment data
    
    Returns:
        Updated list of Flight models with enrichment fields populated
    """
    for flight in flights:
        extra = enrichment_map.get(flight.callsign, {})
        if extra:
            flight.aircraft_code = extra.get('aircraft_code')
            flight.weight_class = extra.get('weight_class')
            flight.origin_iata = extra.get('origin_iata')
            flight.destination_iata = extra.get('destination_iata')
            flight.airline_iata = extra.get('airline_iata')
    
    return flights


def create_storm_sectors(weather: Weather) -> List[StormSector]:
    """
    Create storm sectors based on weather conditions.
    In production, this would use radar data. For now, we create
    synthetic sectors when storm_warning is True.
    """
    if not weather.storm_warning:
        return []
    
    # Synthetic storm sector near CYYZ approach
    return [
        StormSector(
            sector="B07",
            severity="severe" if weather.conditions and "TS" in weather.conditions else "moderate",
            polygon=[
                [43.65, -79.70],
                [43.65, -79.55],
                [43.75, -79.55],
                [43.75, -79.70],
            ]
        )
    ]


def create_tick_data(
    flights: List[Flight],
    weather: Weather,
    airport: str = "CYYZ",
    tick_id: Optional[str] = None,
) -> TickData:
    """
    Create a complete TickData structure from preprocessed components.
    
    This is the main entry point for Layer 2 - combines all data sources
    into a single validated structure ready for the rules engine.
    
    Args:
        flights: List of Flight models (already enriched)
        weather: Weather model
        airport: Airport ICAO code
        tick_id: Optional tick ID (generated if not provided)
    
    Returns:
        Complete TickData structure
    """
    return TickData(
        tick_id=tick_id or f"tick-{uuid.uuid4().hex[:8]}",
        timestamp=datetime.now(timezone.utc).isoformat(),
        airport=airport,
        flights=flights,
        weather=weather,
        storm_sectors=create_storm_sectors(weather),
    )


def preprocess_tick(
    opensky_states: List[Any],
    metar_data: Dict[str, Any],
    enrichment_map: Optional[Dict[str, Dict]] = None,
    airport: str = "CYYZ",
) -> TickData:
    """
    Complete Layer 2 preprocessing pipeline.
    
    Takes raw data from all Layer 1 sources and produces a validated TickData.
    
    Args:
        opensky_states: Raw FlightState list from opensky_client
        metar_data: Raw METAR dict from weather_client
        enrichment_map: Optional FR24 enrichment data
        airport: Airport ICAO code
    
    Returns:
        Validated TickData ready for rules engine
    """
    # Step 1: Convert raw flights to Flight models
    flights = flights_from_opensky(opensky_states)
    
    # Step 2: Convert METAR to Weather model
    weather = weather_from_metar(metar_data)
    
    # Step 3: Merge enrichment data if available
    if enrichment_map:
        flights = merge_enrichment(flights, enrichment_map)
    
    # Step 4: Create complete TickData
    return create_tick_data(flights, weather, airport)
