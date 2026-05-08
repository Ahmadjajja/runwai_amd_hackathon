"""
Layer 1 — CYYZ Runway Status Monitor
Uses live OpenSky ADS-B data to map every on-ground aircraft to its runway
and show which runways are FREE vs OCCUPIED in real time.
"""
import math
import time
import os
from datetime import datetime, timezone
from typing import List, Dict, Tuple

from layer1.opensky_client import fetch_flights, FlightState

# ── Tight airport footprint (just CYYZ, not greater Toronto) ─────────────────
AIRPORT_BOUNDS = {
    "lamin": 43.640, "lamax": 43.715,
    "lomin": -79.660, "lomax": -79.565,
}

# ── CYYZ runway centerline endpoints (approximate, public chart data) ─────────
# Heading 06x/24x ≈ 065°/245° (NE-SW parallel pair)
# Heading 15x/33x ≈ 152°/332° (NW-SE cross pair)
RUNWAYS = [
    {"id": "06L/24R", "start": (43.6590, -79.6470), "end": (43.6970, -79.5890)},
    {"id": "06R/24L", "start": (43.6480, -79.6300), "end": (43.6840, -79.5745)},
    {"id": "15R/33L", "start": (43.7050, -79.6385), "end": (43.6570, -79.5985)},
    {"id": "15L/33R", "start": (43.6980, -79.6220), "end": (43.6540, -79.5830)},
]

THRESHOLD_M = 300   # aircraft within 300m of a runway centreline → on that runway

# ── ASCII map dimensions ──────────────────────────────────────────────────────
_LAT_MIN, _LAT_MAX = 43.640, 43.715
_LON_MIN, _LON_MAX = -79.660, -79.565
_MAP_W, _MAP_H     = 64, 22


# ── Geometry ──────────────────────────────────────────────────────────────────

def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((φ2 - φ1) / 2) ** 2
         + math.cos(φ1) * math.cos(φ2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _dist_to_segment(lat, lon, p1, p2) -> float:
    """Perpendicular distance (metres) from point to line segment, flat-earth approx."""
    R       = 6_371_000
    cos_lat = math.cos(math.radians((p1[0] + p2[0]) / 2))

    def xy(la, lo):
        return math.radians(lo) * R * cos_lat, math.radians(la) * R

    px, py = xy(lat, lon)
    ax, ay = xy(*p1)
    bx, by = xy(*p2)
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq == 0:
        return _haversine(lat, lon, p1[0], p1[1])
    t  = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    cx, cy = ax + t * dx, ay + t * dy
    return math.sqrt((px - cx) ** 2 + (py - cy) ** 2)


# ── Core classification ───────────────────────────────────────────────────────

def classify_aircraft(flights: List[FlightState]) -> Dict[str, list]:
    """
    Assign each on-ground aircraft to its nearest runway (or taxiway/apron).
    Returns  { runway_id: [(FlightState, dist_m), ...], "taxiway/apron": [...] }
    """
    buckets: Dict[str, list] = {r["id"]: [] for r in RUNWAYS}
    buckets["taxiway/apron"] = []

    for f in flights:
        if not f.on_ground or not f.latitude or not f.longitude:
            continue
        best_rwy, best_d = None, float("inf")
        for rwy in RUNWAYS:
            d = _dist_to_segment(f.latitude, f.longitude, rwy["start"], rwy["end"])
            if d < best_d:
                best_d, best_rwy = d, rwy["id"]
        key = best_rwy if best_d <= THRESHOLD_M else "taxiway/apron"
        buckets[key].append((f, round(best_d)))

    return buckets


def runway_status(flights: List[FlightState]) -> Dict[str, dict]:
    """
    Returns a clean status dict for use by Layer 2 / Layer 3.
    { "06L/24R": {"free": False, "aircraft": [{"callsign": ..., "dist_m": ...}]}, ... }
    """
    occ = classify_aircraft(flights)
    return {
        rwy["id"]: {
            "free":     len(occ[rwy["id"]]) == 0,
            "aircraft": [{"callsign": f.callsign,
                          "lat": f.latitude, "lon": f.longitude,
                          "speed_kts": round(f.velocity_ms * 1.944),
                          "dist_m": d}
                         for f, d in occ[rwy["id"]]],
        }
        for rwy in RUNWAYS
    }


# ── ASCII visualiser ──────────────────────────────────────────────────────────

def _to_rc(lat, lon):
    r = int((_LAT_MAX - lat) / (_LAT_MAX - _LAT_MIN) * (_MAP_H - 1))
    c = int((lon - _LON_MIN) / (_LON_MAX - _LON_MIN) * (_MAP_W - 1))
    return r, c


def _bresenham(r0, c0, r1, c1):
    dr, dc = abs(r1 - r0), abs(c1 - c0)
    sr, sc = (1 if r0 < r1 else -1), (1 if c0 < c1 else -1)
    err = dr - dc
    while True:
        yield r0, c0
        if r0 == r1 and c0 == c1:
            break
        e2 = 2 * err
        if e2 > -dc:
            err -= dc; r0 += sr
        if e2 < dr:
            err += dc; c0 += sc


def _draw(flights: List[FlightState], buckets: dict, status: dict, tick: int) -> None:
    os.system("clear")
    now       = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    on_ground = [f for f in flights if f.on_ground]
    airborne  = [f for f in flights if not f.on_ground]

    # ── Build grid ────────────────────────────────────────────────────────────
    grid = [['·'] * _MAP_W for _ in range(_MAP_H)]

    # Draw runway centrelines
    rwy_char = {"06L/24R": "═", "06R/24L": "═", "15R/33L": "/", "15L/33R": "/"}
    for rwy in RUNWAYS:
        r0, c0 = _to_rc(*rwy["start"])
        r1, c1 = _to_rc(*rwy["end"])
        ch     = rwy_char[rwy["id"]]
        for r, c in _bresenham(r0, c0, r1, c1):
            if 0 <= r < _MAP_H and 0 <= c < _MAP_W:
                grid[r][c] = ch

    # Airport centre / terminal area marker
    tr, tc = _to_rc(43.6800, -79.6180)
    if 0 <= tr < _MAP_H and 0 <= tc < _MAP_W:
        grid[tr][tc] = "T"

    # On-ground aircraft  (G = ground)
    for f in on_ground:
        if f.latitude and f.longitude:
            r, c = _to_rc(f.latitude, f.longitude)
            if 0 <= r < _MAP_H and 0 <= c < _MAP_W:
                grid[r][c] = "G"

    # Airborne aircraft in the airport box  (^ = airborne)
    for f in airborne:
        if f.latitude and f.longitude:
            r, c = _to_rc(f.latitude, f.longitude)
            if 0 <= r < _MAP_H and 0 <= c < _MAP_W and grid[r][c] == "·":
                grid[r][c] = "^"

    # ── Print map ─────────────────────────────────────────────────────────────
    W2 = _MAP_W + 2
    border = "═" * W2
    print(f"╔{border}╗")
    title = f"  RunwAI — CYYZ Runway Status  |  Tick #{tick}  |  {now}"
    print(f"║ {title:<{W2-1}}║")
    print(f"╠{border}╣")
    for row in grid:
        print(f"║ {''.join(row)} ║")
    print(f"╠{border}╣")
    legend = "  ═=06x parallel  /=15x cross  G=on-ground  ^=airborne  T=terminal"
    print(f"║{legend:<{W2}}║")
    print(f"╚{border}╝")

    # ── Runway status table ───────────────────────────────────────────────────
    print()
    print(f"  {'RUNWAY':<10} {'STATUS':<14} {'AIRCRAFT (callsign  dist)'}")
    print(f"  {'─'*10} {'─'*14} {'─'*40}")
    for rwy in RUNWAYS:
        info    = status[rwy["id"]]
        ac_list = info["aircraft"]
        if ac_list:
            ac_str  = "  ".join(f"{a['callsign']}({a['dist_m']}m)" for a in ac_list[:4])
            tag     = "OCCUPIED  ⚠"
        else:
            ac_str = "—"
            tag    = "FREE  ✓"
        print(f"  {rwy['id']:<10} {tag:<14} {ac_str}")

    # ── Taxiway / apron ───────────────────────────────────────────────────────
    apron = buckets["taxiway/apron"]
    if apron:
        print(f"\n  Taxiway / Apron — {len(apron)} aircraft:")
        for f, d in apron[:10]:
            print(f"    {f.callsign:<10}  {f.latitude:.4f}°N  {f.longitude:.4f}°W  "
                  f"spd={round(f.velocity_ms*1.944):>3}kts  ({d}m from nearest rwy)")

    # ── Summary footer ────────────────────────────────────────────────────────
    free_count = sum(1 for rwy in RUNWAYS if status[rwy["id"]]["free"])
    print(f"\n  Runways FREE: {free_count}/4  |  "
          f"On-ground: {len(on_ground)}  |  Airborne in box: {len(airborne)}")
    print(f"  Press Ctrl+C to stop  (refreshes every 10s — OpenSky update rate)")


# ── Live monitor loop ─────────────────────────────────────────────────────────

def run_monitor(interval: int = 10) -> None:
    """Refresh runway occupancy every interval seconds."""
    print("RunwAI — CYYZ runway monitor starting...")
    tick = 0
    try:
        while True:
            flights = fetch_flights(AIRPORT_BOUNDS)
            buckets = classify_aircraft(flights)
            status  = runway_status(flights)
            tick   += 1
            _draw(flights, buckets, status, tick)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_monitor()
