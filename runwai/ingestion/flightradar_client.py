"""
Layer 1 — FlightRadar24 client (supplementary)
Enriches OpenSky data with aircraft type, origin, destination, and airline.
Uses the unofficial FlightRadarAPI library (pip install FlightRadarAPI).

IMPORTANT: This is a standalone enrichment file.
           It does NOT replace OpenSky — use alongside it.
           Primary use: get aircraft weight class for wake turbulence detection.
"""
from typing import Dict, List

try:
    from FlightRadar24 import FlightRadar24API
    FR24_AVAILABLE = True
except ImportError:
    FR24_AVAILABLE = False
    print("[FR24] FlightRadarAPI not installed. Run: pip install FlightRadarAPI")

# Toronto Pearson centre point and radius
CYYZ_LAT    = 43.6772
CYYZ_LON    = -79.6306
RADIUS_KM   = 200

# ICAO aircraft type → weight class mapping
# Heavy = wake turbulence risk to following aircraft
WEIGHT_CLASS: Dict[str, str] = {
    # Heavy
    "B744": "Heavy", "B748": "Heavy", "B77L": "Heavy", "B77W": "Heavy",
    "B788": "Heavy", "B789": "Heavy", "B78X": "Heavy",
    "A124": "Heavy", "A225": "Heavy", "A388": "Heavy", "A380": "Heavy",
    "A332": "Heavy", "A333": "Heavy", "A343": "Heavy", "A345": "Heavy",
    "A346": "Heavy", "A359": "Heavy", "A35K": "Heavy",
    "C5":   "Heavy", "IL76": "Heavy",
    # Medium
    "B737": "Medium", "B738": "Medium", "B739": "Medium", "B38M": "Medium",
    "B736": "Medium", "B733": "Medium", "B734": "Medium", "B735": "Medium",
    "A319": "Medium", "A320": "Medium", "A321": "Medium", "A20N": "Medium",
    "A21N": "Medium", "A318": "Medium",
    "B752": "Medium", "B753": "Medium", "B762": "Medium", "B763": "Medium",
    "B764": "Medium",
    "E170": "Medium", "E175": "Medium", "E190": "Medium", "E195": "Medium",
    "CRJ7": "Medium", "CRJ9": "Medium", "CRJX": "Medium",
    "DH8D": "Medium", "DH8C": "Medium",
    "AT72": "Medium", "AT75": "Medium",
    # Light
    "C172": "Light", "C152": "Light", "C182": "Light", "C208": "Light",
    "P28A": "Light", "PA28": "Light", "PA44": "Light",
    "BE36": "Light", "BE58": "Light", "BE20": "Light",
    "SR22": "Light", "DA40": "Light", "DA42": "Light",
    "PC12": "Light", "TBM9": "Light", "TBM7": "Light",
}


def get_weight_class(aircraft_code: str) -> str:
    """Return Heavy / Medium / Light for a given ICAO aircraft type code."""
    return WEIGHT_CLASS.get(aircraft_code.upper(), "Unknown")


def fetch_enriched_flights() -> List[Dict]:
    """
    Fetch flights around CYYZ from FlightRadar24.
    Returns a list of dicts with type, origin, destination, and weight class.
    Falls back to mock data if library not installed or API fails.
    """
    if not FR24_AVAILABLE:
        print("[FR24] Using mock enrichment data.")
        return _mock_enriched()

    try:
        api    = FlightRadar24API()
        # get_bounds expects: tl_y (north lat), tl_x (west lon), br_y (south lat), br_x (east lon)
        bounds = api.get_bounds({"tl_y": 44.4, "tl_x": -80.5, "br_y": 43.2, "br_x": -78.8})
        raw    = api.get_flights(bounds=bounds)

        enriched = []
        for f in raw:
            code = getattr(f, "aircraft_code", "") or ""
            enriched.append({
                "callsign":         (getattr(f, "callsign", "") or "").strip(),
                "aircraft_code":    code.upper(),
                "weight_class":     get_weight_class(code),
                "airline_iata":     getattr(f, "airline_iata", "") or "",
                "airline_icao":     getattr(f, "airline_icao", "") or "",
                "origin_iata":      getattr(f, "origin_airport_iata", "") or "",
                "destination_iata": getattr(f, "destination_airport_iata", "") or "",
                "latitude":         getattr(f, "latitude", None),
                "longitude":        getattr(f, "longitude", None),
            })
        print(f"[FR24] Fetched {len(enriched)} flights.")
        return enriched

    except Exception as e:
        print(f"[FR24] API error: {e}. Using mock data.")
        return _mock_enriched()


def build_enrichment_map(enriched_flights: List[Dict]) -> Dict[str, Dict]:
    """
    Returns a dict keyed by callsign for fast lookup when merging with OpenSky data.
    Example: enrichment_map["AC101"] → { aircraft_code, weight_class, origin, ... }
    """
    return {
        f["callsign"]: f
        for f in enriched_flights
        if f["callsign"]
    }


def enrich_aircraft(aircraft_list: List[Dict], enrichment_map: Dict[str, Dict]) -> List[Dict]:
    """
    Merge FR24 enrichment into formatted aircraft list from json_formatter.
    Adds: aircraft_code, weight_class, origin_iata, destination_iata, airline_iata.
    Non-destructive — only adds fields, never overwrites existing ones.
    """
    for aircraft in aircraft_list:
        callsign = aircraft.get("callsign", "")
        extra    = enrichment_map.get(callsign, {})
        aircraft["aircraft_code"]    = extra.get("aircraft_code", "UNKNOWN")
        aircraft["weight_class"]     = extra.get("weight_class", "Unknown")
        aircraft["origin_iata"]      = extra.get("origin_iata", "")
        aircraft["destination_iata"] = extra.get("destination_iata", "")
        aircraft["airline_iata"]     = extra.get("airline_iata", "")
    return aircraft_list


def _mock_enriched() -> List[Dict]:
    return [
        {"callsign": "AC101",   "aircraft_code": "B789", "weight_class": "Heavy",  "airline_iata": "AC", "origin_iata": "YVR", "destination_iata": "YYZ", "latitude": 43.68, "longitude": -79.63},
        {"callsign": "WJA202",  "aircraft_code": "B738", "weight_class": "Medium", "airline_iata": "WS", "origin_iata": "YYC", "destination_iata": "YYZ", "latitude": 43.72, "longitude": -79.58},
        {"callsign": "UAL303",  "aircraft_code": "B763", "weight_class": "Heavy",  "airline_iata": "UA", "origin_iata": "ORD", "destination_iata": "YYZ", "latitude": 43.65, "longitude": -79.71},
        {"callsign": "DAL404",  "aircraft_code": "A321", "weight_class": "Medium", "airline_iata": "DL", "origin_iata": "ATL", "destination_iata": "YYZ", "latitude": 43.61, "longitude": -79.55},
        {"callsign": "ACA521",  "aircraft_code": "A333", "weight_class": "Heavy",  "airline_iata": "AC", "origin_iata": "LHR", "destination_iata": "YYZ", "latitude": 43.76, "longitude": -79.62},
        {"callsign": "TOM678",  "aircraft_code": "C172", "weight_class": "Light",  "airline_iata": "",   "origin_iata": "YKZ", "destination_iata": "YYZ", "latitude": 43.64, "longitude": -79.68},
    ]


# ── Visualizer ───────────────────────────────────────────────────────────────

# Map bounds — same as CYYZ bounding box
_LAT_MIN, _LAT_MAX = 43.2, 44.4
_LON_MIN, _LON_MAX = -80.5, -78.8
_MAP_W, _MAP_H     = 80, 28
_CYYZ_LAT          = 43.6772
_CYYZ_LON          = -79.6306


def _to_row(lat: float) -> int:
    return int((_LAT_MAX - lat) / (_LAT_MAX - _LAT_MIN) * (_MAP_H - 1))


def _to_col(lon: float) -> int:
    return int((lon - _LON_MIN) / (_LON_MAX - _LON_MIN) * (_MAP_W - 1))


# Symbol per weight class (uppercase=airborne, lowercase=on_ground)
_SYM = {"Heavy": "H", "Medium": "M", "Light": "L", "Unknown": "?"}


def _draw(flights: List[Dict], tick: int, prev: Dict[str, Dict]) -> None:
    import os
    from datetime import datetime, timezone
    os.system("clear")

    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    heavy   = sum(1 for f in flights if f["weight_class"] == "Heavy")
    medium  = sum(1 for f in flights if f["weight_class"] == "Medium")
    light   = sum(1 for f in flights if f["weight_class"] == "Light")
    unknown = sum(1 for f in flights if f["weight_class"] == "Unknown")

    # Build grid
    grid = [['·'] * _MAP_W for _ in range(_MAP_H)]

    for c in range(_MAP_W):
        r = _to_row(43.80)
        if 0 <= r < _MAP_H:
            grid[r][c] = '-'
    for r in range(_MAP_H):
        c = _to_col(-79.40)
        if 0 <= c < _MAP_W:
            grid[r][c] = '+' if grid[r][c] == '-' else '|'

    ar, ac = _to_row(_CYYZ_LAT), _to_col(_CYYZ_LON)
    if 0 <= ar < _MAP_H and 0 <= ac < _MAP_W:
        grid[ar][ac] = '*'

    for f in flights:
        lat, lon = f.get("latitude"), f.get("longitude")
        if lat is None or lon is None:
            continue
        r, c = _to_row(lat), _to_col(lon)
        if 0 <= r < _MAP_H and 0 <= c < _MAP_W and grid[r][c] not in ('*', '+'):
            sym = _SYM.get(f["weight_class"], "?")
            grid[r][c] = sym

    # Print map
    border = "═" * (_MAP_W + 2)
    print(f"╔{border}╗")
    title = f"  RunwAI — FR24 Live Map  |  CYYZ  |  Tick #{tick}  |  {now}  |  {len(flights)} aircraft"
    print(f"║ {title:<{_MAP_W}} ║")
    print(f"╠{border}╣")

    sector_labels = {
        _to_row(44.1): " ← A12 Departure",
        _to_row(43.6): " ← C03 Approach",
        _to_row(43.3): " ← B07 East",
    }
    for i, row in enumerate(grid):
        label = sector_labels.get(i, "")
        line  = "".join(row)
        print(f"║ {line} {label}║" if not label else f"║ {line}{label:<1}║")

    print(f"╠{border}╣")
    stats = [
        f"  H Heavy={heavy}  M Medium={medium}  L Light={light}  ?=Unknown  * =CYYZ airport",
        f"  H=Boeing777/787/A380  M=Boeing737/A320  L=Cessna/small props",
    ]
    for s in stats:
        print(f"║{s:<{_MAP_W + 2}}║")
    print(f"╚{border}╝")

    # ── Live data table — shows exact numbers changing in real time ───────────
    print()
    print(f"  {'CALLSIGN':<10} {'TYPE':<6} {'CLASS':<7} {'LAT':>8} {'LON':>9} {'SPD':>5} {'ROUTE':<15} CHANGE")
    print(f"  {'─'*10} {'─'*6} {'─'*7} {'─'*8} {'─'*9} {'─'*5} {'─'*15} {'─'*10}")

    # Sort by weight class: Heavy first
    order = {"Heavy": 0, "Medium": 1, "Light": 2, "Unknown": 3}
    sorted_flights = sorted(
        [f for f in flights if f.get("latitude")],
        key=lambda x: order.get(x["weight_class"], 3)
    )

    for f in sorted_flights[:15]:
        cs    = f["callsign"]
        lat   = f.get("latitude", 0)
        lon   = f.get("longitude", 0)
        spd   = f.get("ground_speed", 0) or 0
        route = f"{f['origin_iata'] or '???'} → {f['destination_iata'] or '???'}"

        # Detect position change from previous tick
        p = prev.get(cs)
        if p:
            dlat = lat - p.get("latitude", lat)
            dlon = lon - p.get("longitude", lon)
            if abs(dlat) > 0.0001 or abs(dlon) > 0.0001:
                change = f"↑ MOVED ({dlat:+.4f}, {dlon:+.4f})"
            else:
                change = "· same"
        else:
            change = "· new"

        cls_tag = f"[{f['weight_class']}]"
        print(f"  {cs:<10} {f['aircraft_code']:<6} {cls_tag:<7} {lat:>8.4f} {lon:>9.4f} {int(spd):>5} {route:<15} {change}")

    print(f"\n  Press Ctrl+C to stop.")


def run_visualizer(interval: int = 5) -> None:
    import time
    print("RunwAI FR24 visualizer starting...")
    tick = 0
    prev: Dict[str, Dict] = {}
    try:
        while True:
            flights = fetch_enriched_flights()
            tick   += 1
            _draw(flights, tick, prev)
            # Save current positions for next tick comparison
            prev = {
                f["callsign"]: {"latitude": f.get("latitude"), "longitude": f.get("longitude")}
                for f in flights if f.get("callsign")
            }
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nVisualizer stopped.")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_visualizer()
