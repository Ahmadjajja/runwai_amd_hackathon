"""
Layer 1 - Data Ingestion

Data sources:
- OpenSky Network: Live flight positions
- Aviation Weather: METAR data
- FlightRadar24: Aircraft type enrichment
"""

from .opensky_client import fetch_flights, FlightState, CYYZ_BOUNDS
from .weather_client import fetch_weather
from .flightradar_client import (
    fetch_enriched_flights,
    build_enrichment_map,
    get_weight_class,
    WEIGHT_CLASS,
)
from .video_processor import get_latest_frame, download_youtube, ingest_youtube_stream

__all__ = [
    "fetch_flights",
    "FlightState",
    "CYYZ_BOUNDS",
    "fetch_weather",
    "fetch_enriched_flights",
    "build_enrichment_map",
    "get_weight_class",
    "WEIGHT_CLASS",
    "get_latest_frame",
    "download_youtube",
    "ingest_youtube_stream",
]
