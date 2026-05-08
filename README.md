# RunwAI — Real-time ATC Conflict Detection

AMD Developer Hackathon · Track 3: Vision & Multimodal AI · Airport: Toronto Pearson (CYYZ)

---

## What's built — Layer 1 (Data Inputs)

Layer 1 is complete. All 4 live data sources are wired up and tested.

### Files

```
layer1/
  opensky_client.py       Live flight positions around CYYZ via OpenSky ADS-B API
  weather_client.py       Live METAR weather for CYYZ via aviationweather.gov
  runway_status.py        Maps on-ground aircraft to runway centerlines (haversine geometry)
  flightradar_client.py   FR24 enrichment — aircraft type, weight class (Heavy/Medium/Light), route
  video_processor.py      Extracts frames (1 every 10s) from ATC tower video using OpenCV
  transcript_parser.py    Parses timestamped ATC transcript, pairs each frame with its segment
demo.py                   Runs all 4 sources together and prints a live summary
```

### Data sources

| Source | What it gives us | API |
|--------|-----------------|-----|
| OpenSky Network | Live callsign, lat/lon, altitude, speed, heading, vertical rate | `opensky-network.org/api/states/all` |
| METAR (aviationweather.gov) | Wind, visibility, ceiling, storm warnings | `aviationweather.gov/api/data/metar` |
| FlightRadar24 | Aircraft type (B789, A321…), weight class, origin→destination | Unofficial FR24 API |
| ATC tower video + transcript | Visual runway state, spoken ATC instructions timestamped | Local MP4 + `transcript.txt` |

All clients have mock fallbacks — they work offline / when APIs are rate-limited.

### Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python demo.py
```

### Output produced by Layer 1

```
output/
  frames/                          743 JPEG frames extracted from ATC video
  transcript_segments.json         Parsed ATC segments with timestamps
  frames_with_transcript.json      Each frame paired with its ATC segment + weather snapshot
```

---

## What comes next — Layers 2–7 (not built yet)

| Layer | What | Owner |
|-------|------|-------|
| 2 | JSON formatter — FlightState + weather → structured per-aircraft payload | TBD |
| 3 | Prompt builder — JSON + video frame → multimodal VLM prompt | TBD |
| 4 | AMD inference — Qwen3-VL on MI300X via ROCm + vLLM | Person 2 |
| 5 | Conflict detector — 5nm separation, storm avoidance, wake turbulence rules | TBD |
| 6 | Decision output — conflict risk %, rerouting recommendations, latency | TBD |
| 7 | Live dashboard — Leaflet flight map + conflict panel + metrics | TBD |

Layer 4 (AMD MI300X setup) is the critical path. Layers 2–3 and 5–7 can be built locally without AMD hardware.

---

## Key data structures

**FlightState** (from `opensky_client.py`)
```python
@dataclass
class FlightState:
    icao24: str
    callsign: str
    latitude: float
    longitude: float
    baro_altitude_m: float
    velocity_ms: float
    true_track_deg: float
    vertical_rate_ms: float
    on_ground: bool
```

**Weather dict** (from `weather_client.py`)
```python
{
    "station": "CYYZ",
    "wind_dir_deg": 280,
    "wind_speed_kts": 12,
    "wind_gust_kts": 18,
    "visibility_sm": 10,
    "ceiling_ft": 3500,
    "storm_warning": False,
    "low_visibility": False,
    "raw_metar": "CYYZ 071700Z 28012G18KT 15SM FEW035 BKN090 08/02 A2998"
}
```

**Paired frame entry** (from `frames_with_transcript.json`)
```python
{
    "timestamp_s": 300,
    "timestamp_fmt": "00:05:00",
    "frame_path": "output/frames/scope_atc_tower_chatter_t00300.jpg",
    "atc_transcript": "Delta 961 land 9 left Mike 2 line for weight traffic downfield...",
    "atc_context": "...[prev segment] [current] [next segment]...",
    "segment_id": 30,
    "weather": { "storm_warning": false, "wind_speed_kts": 12, ... }
}
```

---

## CYYZ Sectors (for Layer 5 conflict detection)

- **A12** — North sector (departures heading north)
- **B07** — East corridor
- **C03** — Landing approach (active conflict zone, aircraft <5000ft)

CYYZ center: `43.6772°N, 79.6306°W`
