# RunwAI - AI Air Traffic Control System

Real-time conflict detection and resolution for air traffic control using AI.

## Architecture

```
runwai/
├── ingestion/          # Layer 1 - Data Sources
│   ├── opensky_client.py    # Live flight positions
│   ├── weather_client.py    # METAR weather data
│   └── flightradar_client.py # Aircraft enrichment
│
├── preprocessing/      # Layer 2 - JSON Formatting
│   ├── schemas.py          # Pydantic models
│   └── formatter.py        # Data conversion
│
├── prompt/             # Layer 3 - Prompt Builder
│   ├── builder.py          # Assembles VLM prompt
│   └── templates.py        # System role, rules, output schema
│
├── model/              # Layer 4 - Model Adapter
│   └── adapter.py          # HuggingFace API (Qwen)
│
├── rules/              # Layer 5 - Rules Engine
│   ├── engine.py           # Orchestrator
│   ├── separation.py       # 5NM/1000ft rule
│   ├── storm.py            # Weather avoidance
│   └── wake_turbulence.py  # Heavy->Light spacing
│
├── decision/           # Layer 6 - Decision Making
│   ├── engine.py           # Validation orchestrator
│   ├── parser.py           # Parse model JSON
│   ├── validator.py        # Sanity checks
│   ├── simulator.py        # Re-run rules on projected state
│   └── sector.py           # A12/B07/C03 assignment
│
├── frontend/           # Layer 7 - Visualization
│   ├── index.html          # Airport simulation UI
│   ├── main.js             # Canvas rendering
│   ├── styles.css          # Dark theme
│   └── mockScenarios.js    # Test scenarios
│
├── fixtures/           # Test Data
│   ├── tick_separation.json
│   ├── tick_storm.json
│   ├── tick_wake.json
│   └── tick_clean.json
│
└── main.py             # Main orchestrator
```

## Usage

### Run Single Tick
```bash
cd runwai
python -m runwai.main
```

### Run Test Scenario
```bash
python -m runwai.main --scenario separation
python -m runwai.main --scenario storm
python -m runwai.main --scenario wake
```

### Live Mode (Continuous)
```bash
python -m runwai.main --live --interval 10
```

### Frontend Simulation
```bash
cd runwai/frontend
python -m http.server 8080
# Open http://localhost:8080
```

### FastAPI bridge (frontend ↔ Python rules)

Terminal 1 — API server (from **repository root**, after `pip install -r requirements.txt`):

```bash
uvicorn runwai.server:app --reload --host 127.0.0.1 --port 8000
```

- `GET http://127.0.0.1:8000/health` — health check  
- `POST http://127.0.0.1:8000/api/simulation/tick` — body = JSON from the frontend (`getSimulationExport()` shape: aircraft, weather, alerts)

The browser sends this package **every 2 seconds** by default (`CONFIG.API_PUSH_INTERVAL_MS` in `frontend/main.js`). Override base URL before load: `window.__RUNWAI_API__ = 'http://127.0.0.1:8000'` or set `CONFIG.API_BASE_URL` to `''` to disable pushes.

## Data Flow

```
OpenSky API ─┐
Weather API ─┼─→ Layer 2 (Preprocessing) ─→ Layer 5 (Rules) ─┐
FR24 API ────┘                                               │
                                                             v
                              ┌─────────────────────────────────────┐
                              │         Layer 3 (Prompt)            │
                              │   [Tick Data + Violations + Rules]  │
                              └─────────────────────────────────────┘
                                             │
                                             v
                              ┌─────────────────────────────────────┐
                              │         Layer 4 (Model)             │
                              │      Qwen via HuggingFace API       │
                              └─────────────────────────────────────┘
                                             │
                                             v
                              ┌─────────────────────────────────────┐
                              │        Layer 6 (Decision)           │
                              │  Parse → Validate → Simulate → OK?  │
                              └─────────────────────────────────────┘
                                             │
                                             v
                              ┌─────────────────────────────────────┐
                              │        Layer 7 (Frontend)           │
                              │     Airport Surface Simulation      │
                              └─────────────────────────────────────┘
```

## Rules

1. **Minimum Separation**: Aircraft must maintain 5 NM horizontal OR 1000 ft vertical
2. **Storm Avoidance**: Aircraft projected into hazardous weather within 60s
3. **Wake Turbulence**: Light aircraft following Heavy need 6 NM spacing

## Environment Variables

```bash
HF_API_KEY=hf_xxxxxxxxxxxxx  # HuggingFace API key for Qwen model
```

## Requirements

```bash
pip install -r requirements.txt
```
