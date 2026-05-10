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
│   └── adapter.py          # LangChain ChatOpenAI → Qwen (OSS) + HF / httpx fallbacks
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
- `GET http://127.0.0.1:8000/api/model/status` — whether Qwen/HF is configured (**stub** vs **openai_compatible** / **huggingface_inference**; no secrets)
- `POST http://127.0.0.1:8000/api/simulation/tick` — body = JSON from the frontend (`getSimulationExport()` shape: aircraft, weather, alerts)

Query parameters:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `run_rules` | `true` | Run Python `run_all_rules` on the tick |
| `full_pipeline` | `false` | Also run prompt → `call_model` → Layer 6 `DecisionEngine` (needs LLM env vars below) |
| `ml_advisory` | `false` | Second LLM call: Qwen-style JSON → human-readable conflict/reroute lines (`ml_advisories`, `multimodal_context`) for the UI |
| `model_debug` | `false` | Log prompt/response on server stdout |

The frontend enables **`ml_advisory`** by default (`CONFIG.API_ML_ADVISORY` in `frontend/main.js`). Cards labeled **QWEN** show model text; **QWEN-PRED** rows are **model-only pair risks** from telemetry (`model_conflict_predictions`). Python rules still compute deterministic violations; Qwen augments with forward-looking narrative + optional extra pairs.

The browser sends this package **every 2 seconds** by default (`CONFIG.API_PUSH_INTERVAL_MS` in `frontend/main.js`). Override base URL before load: `window.__RUNWAI_API__ = 'http://127.0.0.1:8000'` or set `CONFIG.API_BASE_URL` to `''` to disable pushes.

For **full stack on GPU** (vLLM / OpenAI-compatible server on AMD MI300X or similar), point the adapter at your inference URL — same JSON body, add `?full_pipeline=true` when posting from curl/tests (the default frontend push stays lightweight with rules-only unless you extend `main.js`).

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
                              │   HF API or OpenAI-compatible API   │
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

Copy **`.env.example`** to **`.env`** in the **repository root** (same folder as `requirements.txt`). Values load automatically via `python-dotenv` before the model adapter reads configuration.

Layer 5 rules compute **conflicts / predictions** from simulation geometry; **Qwen** turns those findings into **natural-language advisories** and reroute wording (`ml_advisory`). Layer 4 (`runwai/model/adapter.py`) uses **LangChain** [`ChatOpenAI`](https://python.langchain.com/) for OpenAI-compatible endpoints. It falls back to raw `httpx`, then Hugging Face `InferenceClient`, then a stub.

```bash
# 1) OpenAI-compatible API — LangChain routes here first (set USE_LANGCHAIN=0 to skip)
OPENAI_BASE_URL=https://router.huggingface.co   # or http://127.0.0.1:8000/v1 — see note below
MODEL_NAME=Qwen/Qwen2.5-7B-Instruct:together    # Qwen on HF Router / your vLLM model id
OPENAI_API_KEY=hf_xxx                           # or MODEL_API_KEY / HF token for router

# Same token name many notebooks use (HF Router); adapter also reads HF_TOKEN if OPENAI_API_KEY unset
# HF_TOKEN=hf_xxx

# Optional
USE_LANGCHAIN=1          # default on; set 0 to force direct httpx only
MODEL_TEMPERATURE=0.3
MODEL_MAX_TOKENS=1024    # main pipeline LLM (full_pipeline=true)
ML_ADVISORY_TEMPERATURE=0.42
ML_ADVISORY_MAX_TOKENS=2048   # second call — longer JSON for multiple flight pairs

# 2) Hugging Face Inference API (fallback if no OPENAI_BASE_URL)
HF_API_KEY=hf_xxxxxxxxxxxxx
HF_MODEL_ID=Qwen/Qwen2.5-72B-Instruct
```

**URL shape:** pass the API **origin** without `/chat/completions`. If you already use `https://host/v1` in other tools, that still works — the adapter normalizes to `.../v1/chat/completions`.

**CrewAI / AutoGen:** this repo uses LangChain as the thin LLM layer; you can wrap `call_model` or add agents that call the same env-backed stack without changing the adapter.

## Requirements

```bash
pip install -r requirements.txt
```
