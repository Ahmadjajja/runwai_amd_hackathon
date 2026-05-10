"""
Rolling latency + SLA stats for demos / portfolio (in-memory, single-process).

Use GET /api/metrics/summary after exercising POST /api/simulation/tick.
"""

from __future__ import annotations

import os
import threading
from collections import deque
from typing import Any

_lock = threading.Lock()

_WINDOW = max(10, int(os.environ.get("METRICS_WINDOW", "500")))
_SLA_MS = max(1, int(os.environ.get("METRICS_SLA_MS", "1000")))

_rules_ms: deque[float] = deque(maxlen=_WINDOW)
_total_ms: deque[float] = deque(maxlen=_WINDOW)
_ml_ms: deque[float] = deque(maxlen=_WINDOW)

_ticks_recorded = 0
_ticks_rules_under_sla = 0
_ticks_total_under_sla = 0
_ticks_with_violation = 0
_ticks_with_ml = 0


def _pctl(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def sla_threshold_ms() -> int:
    return _SLA_MS


def record_tick_snapshot(result: dict[str, Any]) -> None:
    """Call after each successful tick response."""
    global _ticks_recorded, _ticks_rules_under_sla, _ticks_total_under_sla
    global _ticks_with_violation, _ticks_with_ml

    if not result.get("ok", True):
        return

    lr = result.get("latency_rules_ms")
    lt = result.get("latency_total_ms")
    lm = result.get("latency_ml_advisory_ms")
    bv = int(result.get("backend_violations") or 0)

    with _lock:
        _ticks_recorded += 1
        if bv > 0:
            _ticks_with_violation += 1
        if lr is not None:
            x = float(lr)
            _rules_ms.append(x)
            if x <= _SLA_MS:
                _ticks_rules_under_sla += 1
        if lt is not None:
            x = float(lt)
            _total_ms.append(x)
            if x <= _SLA_MS:
                _ticks_total_under_sla += 1
        if lm is not None:
            _ticks_with_ml += 1
            _ml_ms.append(float(lm))


def attach_tick_metrics(result: dict[str, Any]) -> None:
    """Augment one response with SLA booleans (mutates dict)."""
    lr = result.get("latency_rules_ms")
    lt = result.get("latency_total_ms")
    result["metrics"] = {
        "sla_threshold_ms": _SLA_MS,
        "latency_rules_ms": lr,
        "latency_total_ms": lt,
        "latency_ml_advisory_ms": result.get("latency_ml_advisory_ms"),
        "latency_model_ms": result.get("latency_model_ms"),
        "rules_completed_within_sla": lr is not None and float(lr) <= _SLA_MS,
        "full_tick_completed_within_sla": lt is not None and float(lt) <= _SLA_MS,
        "backend_violations": result.get("backend_violations"),
        "notes": (
            "latency_rules_ms = deterministic Python conflict checks only. "
            "latency_total_ms includes optional Qwen (ml_advisory / full_pipeline)."
        ),
    }


def _bucket(latencies: deque[float]) -> dict[str, Any]:
    if not latencies:
        return {"samples": 0}
    s = sorted(latencies)
    n = len(s)
    under = sum(1 for x in s if x <= _SLA_MS)
    return {
        "samples": n,
        "avg_ms": round(sum(s) / n, 3),
        "min_ms": round(s[0], 3),
        "max_ms": round(s[-1], 3),
        "p50_ms": round(_pctl(s, 0.50) or 0, 3),
        "p95_ms": round(_pctl(s, 0.95) or 0, 3),
        f"pct_under_{_SLA_MS}ms": round(100.0 * under / n, 2),
        f"ticks_under_{_SLA_MS}ms": under,
    }


def get_metrics_summary() -> dict[str, Any]:
    """Aggregate since server start (or last reset)."""
    with _lock:
        tr = _ticks_recorded
        tw = _ticks_with_violation
        rs = _ticks_rules_under_sla
        ts = _ticks_total_under_sla
        rules_n = len(_rules_ms)
        total_n = len(_total_ms)
        ml_n = len(_ml_ms)

        summary = {
            "sla_threshold_ms": _SLA_MS,
            "window_max_samples": _WINDOW,
            "ticks_recorded": tr,
            "ticks_with_backend_violation": tw,
            "pct_ticks_with_conflict": round(100.0 * tw / tr, 2) if tr else 0.0,
            "deterministic_rules_latency_ms": _bucket(_rules_ms),
            "full_tick_latency_ms": _bucket(_total_ms),
            "interpretation": {
                "rules_row": (
                    f"Python rules engine: {_pct_line(rs, rules_n)} of sampled ticks "
                    f"finished conflict checks within {_SLA_MS} ms."
                ),
                "total_row": (
                    f"End-to-end POST handler: {_pct_line(ts, total_n)} of sampled ticks "
                    f"completed within {_SLA_MS} ms (includes network stack + optional LLM)."
                ),
            },
        }
        if ml_n:
            summary["ml_advisory_latency_ms"] = _bucket(_ml_ms)
            summary["ticks_that_included_ml_advisory"] = _ticks_with_ml
        return summary


def _pct_line(under: int, denom: int) -> str:
    if not denom:
        return "n/a (no samples yet)"
    pct = 100.0 * under / denom
    return f"{pct:.1f}% ({under}/{denom})"


def reset_metrics() -> None:
    """Clear rolling buffers (for staged demos)."""
    global _ticks_recorded, _ticks_rules_under_sla, _ticks_total_under_sla
    global _ticks_with_violation, _ticks_with_ml
    with _lock:
        _rules_ms.clear()
        _total_ms.clear()
        _ml_ms.clear()
        _ticks_recorded = 0
        _ticks_rules_under_sla = 0
        _ticks_total_under_sla = 0
        _ticks_with_violation = 0
        _ticks_with_ml = 0
