"""
Shared pipeline: simulation export → TickData → rules → prompt → model → decision.

Used by FastAPI (`server.py`) and can be imported by tests.
"""

from __future__ import annotations

import os
import time
from typing import Any


def _ml_advisory_temperature() -> float:
    try:
        return float(os.environ.get("ML_ADVISORY_TEMPERATURE", "0.42"))
    except ValueError:
        return 0.42


def _ml_advisory_max_tokens() -> int:
    try:
        return int(os.environ.get("ML_ADVISORY_MAX_TOKENS", "2048"))
    except ValueError:
        return 2048


def _main_model_max_tokens() -> int:
    try:
        return int(os.environ.get("MODEL_MAX_TOKENS", "1024"))
    except ValueError:
        return 1024

from .decision import DecisionEngine
from .model import call_model
from .preprocessing.simulation_adapter import tick_from_frontend_export
from .prompt import build_prompt
from .prompt.ml_advisory import (
    build_ml_advisory_prompt,
    build_and_finalize_advisories,
)
from .rules import run_all_rules


def _violation_to_dict(v: Any) -> dict[str, Any]:
    if hasattr(v, "model_dump"):
        return v.model_dump()
    return v.dict()


def _decision_to_dict(d: Any) -> dict[str, Any]:
    if hasattr(d, "model_dump"):
        return d.model_dump(mode="json")
    return d.dict()


def run_from_simulation_export(
    payload: dict[str, Any],
    *,
    run_rules: bool = True,
    full_pipeline: bool = False,
    ml_advisory: bool = False,
    model_debug: bool = False,
) -> dict[str, Any]:
    """
    Args:
        payload: Same JSON as frontend getSimulationExport().
        run_rules: If False, only parse payload to TickData (no rule violations).
        full_pipeline: If True, run prompt + LLM + Layer 6 (implies run_rules).
        model_debug: Forward to call_model debug_print.
        ml_advisory: Second LLM call — natural-language conflict/reroute lines for the UI.

    Returns:
        Unified dict for API / logging.
    """
    if full_pipeline or ml_advisory:
        run_rules = True

    t0 = time.perf_counter()
    tick = tick_from_frontend_export(payload)

    if not run_rules:
        return {
            "ok": True,
            "tick_id": tick.tick_id,
            "aircraft_count": len(tick.flights),
            "frontend_alert_count": len(payload.get("alerts") or []),
            "latency_total_ms": round((time.perf_counter() - t0) * 1000, 3),
        }

    t_rules = time.perf_counter()
    rules_output = run_all_rules(tick)

    out: dict[str, Any] = {
        "ok": True,
        "tick_id": tick.tick_id,
        "aircraft_count": len(tick.flights),
        "frontend_alert_count": len(payload.get("alerts") or []),
        "rules_evaluated": rules_output.rules_evaluated,
        "backend_violations": len(rules_output.violations),
        "violations": [_violation_to_dict(v) for v in rules_output.violations],
        "latency_rules_ms": round((time.perf_counter() - t_rules) * 1000, 3),
    }

    if ml_advisory:
        t_ml = time.perf_counter()
        adv_prompt = build_ml_advisory_prompt(tick, rules_output, payload)
        raw_adv = call_model(
            adv_prompt,
            debug_print=model_debug,
            temperature=_ml_advisory_temperature(),
        )
        adv_list, mm_note, conflict_predictions = build_and_finalize_advisories(
            tick, rules_output, payload, raw_adv
        )
        out["ml_advisories"] = adv_list
        out["model_conflict_predictions"] = conflict_predictions
        out["multimodal_context"] = mm_note or None
        out["ml_advisory_raw_preview"] = raw_adv[:600] + ("..." if len(raw_adv) > 600 else "")
        out["latency_ml_advisory_ms"] = round((time.perf_counter() - t_ml) * 1000, 3)

    if not full_pipeline:
        out["latency_total_ms"] = round((time.perf_counter() - t0) * 1000, 3)
        return out

    prompt = build_prompt(tick, rules_output)
    out["prompt_chars"] = len(prompt)

    t_model_start = time.perf_counter()
    model_response_text = call_model(
        prompt,
        debug_print=model_debug,
        max_tokens=_main_model_max_tokens(),
    )
    out["latency_model_ms"] = round((time.perf_counter() - t_model_start) * 1000, 3)
    out["model_response_preview"] = model_response_text[:500] + (
        "..." if len(model_response_text) > 500 else ""
    )

    engine = DecisionEngine()
    decision = engine.process(
        tick,
        rules_output,
        model_response_text,
        t0,
    )
    out["decision"] = _decision_to_dict(decision)
    out["decision_valid"] = decision.action_valid
    out["latency_total_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    return out
