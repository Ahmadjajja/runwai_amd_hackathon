"""
FastAPI bridge between Layer 7 (frontend simulation) and Python layers (rules, optional full pipeline).

Run (from repository root):
    uvicorn runwai.server:app --reload --host 127.0.0.1 --port 8000

Health:
    GET  http://127.0.0.1:8000/health

Ingest simulation tick (same JSON as frontend getSimulationExport()):
    POST http://127.0.0.1:8000/api/simulation/tick
    Content-Type: application/json
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .preprocessing.simulation_adapter import tick_from_frontend_export
from .rules import run_all_rules

app = FastAPI(title="RunwAI Simulation API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_last_tick_summary: dict[str, Any] | None = None


def _violation_to_dict(v: Any) -> dict[str, Any]:
    if hasattr(v, "model_dump"):
        return v.model_dump()
    return v.dict()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "runwai-simulation-api"}


@app.post("/api/simulation/tick")
def simulation_tick(
    payload: dict[str, Any],
    run_rules: bool = Query(True, description="Run Python rules engine on this tick"),
) -> dict[str, Any]:
    """
    Accept full simulation export (aircraft, weather, alerts).
    Optionally runs backend rules and returns violations for comparison / logging.
    """
    global _last_tick_summary
    t0 = time.perf_counter()

    tick = tick_from_frontend_export(payload)
    out: dict[str, Any] = {
        "ok": True,
        "tick_id": tick.tick_id,
        "aircraft_count": len(tick.flights),
        "frontend_alert_count": len(payload.get("alerts") or []),
        "latency_preprocess_ms": round((time.perf_counter() - t0) * 1000, 2),
    }

    if run_rules:
        t1 = time.perf_counter()
        rules_output = run_all_rules(tick)
        out["rules_evaluated"] = rules_output.rules_evaluated
        out["backend_violations"] = len(rules_output.violations)
        out["violations"] = [_violation_to_dict(v) for v in rules_output.violations]
        out["latency_rules_ms"] = round((time.perf_counter() - t1) * 1000, 2)

    out["latency_total_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    _last_tick_summary = {"tick_id": out["tick_id"], "aircraft_count": out["aircraft_count"]}
    return out


@app.get("/api/simulation/status")
def simulation_status() -> dict[str, Any]:
    """Last successfully posted tick metadata (debug)."""
    return {"last": _last_tick_summary}
