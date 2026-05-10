"""
FastAPI bridge between Layer 7 (frontend simulation) and Python layers.

Run (from repository root):
    uvicorn runwai.server:app --reload --host 127.0.0.1 --port 8000

Health:
    GET  http://127.0.0.1:8000/health

Ingest simulation tick (same JSON as frontend getSimulationExport()):
    POST http://127.0.0.1:8000/api/simulation/tick
    Query:
      - run_rules=true|false   (default true)
      - full_pipeline=true|false (default false) — rules + prompt + LLM + Layer 6 decision
      - ml_advisory=true|false (default false) — Qwen natural-language advisories for UI alert cards
      - model_debug=true|false (default false)

Copy ``.env.example`` to ``.env`` and set OPENAI_* / HF_* — see ``runwai/model/adapter.py``.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .env_bootstrap import load_repo_dotenv

load_repo_dotenv()

from .metrics import attach_tick_metrics, get_metrics_summary, record_tick_snapshot
from .pipeline import run_from_simulation_export

app = FastAPI(title="RunwAI Simulation API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "runwai-simulation-api"}


@app.get("/api/model/status")
def model_status() -> dict[str, Any]:
    """Whether a real LLM backend is configured (no secrets returned)."""
    base = (os.environ.get("OPENAI_BASE_URL") or os.environ.get("MODEL_BASE_URL") or "").strip()
    hf = bool(os.environ.get("HF_API_KEY"))
    if base:
        mode = "openai_compatible"
    elif hf:
        mode = "huggingface_inference"
    else:
        mode = "stub"
    return {
        "mode": mode,
        "openai_base_url_configured": bool(base),
        "hf_inference_configured": hf,
        "model_name": os.environ.get("MODEL_NAME") or os.environ.get("HF_MODEL_ID") or "",
        "hint": "Copy .env.example to .env in the repo root for Qwen via HF Router or HF_API_KEY.",
    }


@app.post("/api/simulation/tick")
def simulation_tick(
    payload: dict[str, Any],
    run_rules: bool = Query(True, description="Run Python rules engine"),
    full_pipeline: bool = Query(
        False,
        description="Rules + build_prompt + call_model + DecisionEngine (needs LLM env)",
    ),
    ml_advisory: bool = Query(
        False,
        description="Qwen: conflict/reroute text for alerts (second LLM call; needs model env)",
    ),
    model_debug: bool = Query(False, description="Print prompt/response to server stdout"),
) -> dict[str, Any]:
    return run_from_simulation_export(
        payload,
        run_rules=run_rules,
        full_pipeline=full_pipeline,
        ml_advisory=ml_advisory,
        model_debug=model_debug,
    )


@app.get("/api/simulation/status")
def simulation_status() -> dict[str, Any]:
    """Reserved for future last-tick cache."""
    return {"note": "Use POST /api/simulation/tick response as source of truth."}
