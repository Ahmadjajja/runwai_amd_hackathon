"""
Wake Turbulence Category Lookup Table

Maps ICAO aircraft type codes to weight class strings matching Layer 1 format:
- "Heavy" (B747, B777, B787, A330, A340, A350, A380)
- "Medium" (A320, B737, B757, CRJ, E-Jets)
- "Light" (C172, C152, PA28, small GA)

This matches the weight_class field from layer1/flightradar_client.py
"""

from typing import Literal

WeightClass = Literal["Heavy", "Medium", "Light", "Unknown"]

WEIGHT_CLASS_MAP: dict[str, WeightClass] = {
    # Heavy
    "B744": "Heavy", "B747": "Heavy", "B748": "Heavy",
    "B77L": "Heavy", "B77W": "Heavy", "B772": "Heavy", "B773": "Heavy", "B777": "Heavy",
    "B788": "Heavy", "B789": "Heavy", "B78X": "Heavy", "B787": "Heavy",
    "A124": "Heavy", "A225": "Heavy",
    "A388": "Heavy", "A380": "Heavy",
    "A332": "Heavy", "A333": "Heavy", "A330": "Heavy", "A339": "Heavy",
    "A343": "Heavy", "A345": "Heavy", "A346": "Heavy", "A340": "Heavy",
    "A359": "Heavy", "A35K": "Heavy", "A350": "Heavy",
    "MD11": "Heavy", "DC10": "Heavy",
    "IL76": "Heavy", "IL96": "Heavy",
    "B763": "Heavy", "B764": "Heavy", "B767": "Heavy",
    "B762": "Heavy",
    "C5": "Heavy",
    
    # Medium
    "A318": "Medium", "A319": "Medium", "A320": "Medium", "A321": "Medium",
    "A20N": "Medium", "A21N": "Medium",
    "B731": "Medium", "B732": "Medium", "B733": "Medium", "B734": "Medium",
    "B735": "Medium", "B736": "Medium", "B737": "Medium", "B738": "Medium",
    "B739": "Medium", "B37M": "Medium", "B38M": "Medium", "B39M": "Medium",
    "B752": "Medium", "B753": "Medium", "B757": "Medium",
    "E170": "Medium", "E175": "Medium", "E190": "Medium", "E195": "Medium",
    "E75L": "Medium", "E75S": "Medium",
    "CRJ1": "Medium", "CRJ2": "Medium", "CRJ7": "Medium", "CRJ9": "Medium", "CRJX": "Medium",
    "DH8A": "Medium", "DH8B": "Medium", "DH8C": "Medium", "DH8D": "Medium",
    "AT43": "Medium", "AT45": "Medium", "AT72": "Medium", "AT75": "Medium", "AT76": "Medium",
    "SF34": "Medium",
    "MD80": "Medium", "MD81": "Medium", "MD82": "Medium", "MD83": "Medium",
    "MD87": "Medium", "MD88": "Medium", "MD90": "Medium",
    "B712": "Medium",
    "F100": "Medium", "F70": "Medium",
    
    # Light
    "C172": "Light", "C152": "Light", "C182": "Light", "C206": "Light",
    "C208": "Light", "C210": "Light", "C310": "Light", "C340": "Light",
    "C402": "Light", "C404": "Light", "C414": "Light", "C421": "Light",
    "C425": "Light", "C441": "Light",
    "C500": "Light", "C510": "Light", "C525": "Light", "C550": "Light", "C560": "Light",
    "PA28": "Light", "P28A": "Light", "PA32": "Light", "PA34": "Light",
    "PA44": "Light", "PA46": "Light",
    "BE33": "Light", "BE35": "Light", "BE36": "Light", "BE55": "Light",
    "BE58": "Light", "BE76": "Light", "BE9L": "Light", "BE20": "Light", "BE30": "Light",
    "PC12": "Light",
    "TBM7": "Light", "TBM8": "Light", "TBM9": "Light",
    "SR20": "Light", "SR22": "Light",
    "DA40": "Light", "DA42": "Light",
}


def get_weight_class(aircraft_code: str | None, fallback: WeightClass | None = None) -> WeightClass:
    """
    Get weight class for an aircraft type code.
    
    Args:
        aircraft_code: ICAO aircraft type code (e.g., "B77W", "A320")
        fallback: Class to use if type is not in lookup table.
                  If None, defaults to "Unknown".
    
    Returns:
        Weight class: "Heavy", "Medium", "Light", or "Unknown"
    """
    if aircraft_code is None:
        return fallback or "Unknown"
    
    normalized = aircraft_code.upper().strip()
    return WEIGHT_CLASS_MAP.get(normalized, fallback or "Unknown")
