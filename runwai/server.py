"""
RunwAI API Server — connects the Python pipeline to the frontend dashboard.

Run:
    python -m runwai.server
    # or
    uvicorn runwai.server:app --host 0.0.0.0 --port 8080 --reload

Endpoints:
    GET /api/tick                  — run one live tick and return JSON
    GET /api/scenario/{name}       — run a fixture scenario (separation|storm|wake|clean)
    GET /api/status                — health check
    GET /                          — serves the frontend dashboard
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

app = FastAPI(title="RunwAI", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_SCENARIOS = {"separation", "storm", "wake", "clean"}


@app.get("/api/status")
def status():
    return {"status": "ok", "service": "RunwAI"}


@app.get("/api/tick")
def tick_endpoint():
    """Run one full pipeline tick with live data."""
    try:
        from .main import run_single_tick
        result = run_single_tick()
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scenario/{name}")
def scenario_endpoint(name: str):
    """Run a fixture scenario by name."""
    if name not in VALID_SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario '{name}'. Valid: {sorted(VALID_SCENARIOS)}",
        )
    try:
        from .main import run_scenario
        result = run_scenario(name)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve the static frontend — mount last so API routes take priority
_frontend_dir = Path(__file__).parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("runwai.server:app", host="0.0.0.0", port=port, reload=True)
