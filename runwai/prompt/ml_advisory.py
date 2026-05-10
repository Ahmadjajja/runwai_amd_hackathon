"""
ML advisory prompts aligned with rules engine + simulation telemetry.

Produces one advisory row per distinct (rule, flights) finding when possible.
Fallback text is rule-anchored and varies by row so alerts are not generic duplicates.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..preprocessing import TickData, RulesEngineOutput
from .builder import format_tick_data, format_violations

VALID_HOLD_SECTORS = ("A12", "C03", "E05", "B07", "D14")
HOLD_SECTOR_IDS = list(VALID_HOLD_SECTORS)


def _to_int32(x: int) -> int:
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 2**31 else x


def _imul32(a: int, b: int) -> int:
    """Same as JavaScript Math.imul on signed 32-bit operands."""
    prod = (_to_int32(a) * _to_int32(b)) & 0xFFFFFFFF
    return prod - 0x100000000 if prod >= 2**31 else prod


def pick_deterministic_reroute_sector(callsign: str, current_sector: str | None) -> str:
    """Matches frontend/main.js pickDeterministicRerouteSector (Math.imul FNV-style mix)."""
    pool = [s for s in HOLD_SECTOR_IDS if s != (current_sector or "") and s != "—"]
    if not pool:
        return "A12"
    seed = f"{callsign}|{current_sector or ''}"
    h = 2166136261
    for ch in seed:
        h = _imul32(h ^ ord(ch), 16777619)
    return pool[abs(h) % len(pool)]


def _sector_map(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ac in payload.get("aircraft") or []:
        cid = str(ac.get("callsign") or ac.get("id") or "").strip()
        if cid:
            out[cid] = str(ac.get("sector_id") or "?")
    return out


def _pick_vector_flight(flights: list[str]) -> str:
    if not flights:
        return ""
    if len(flights) == 1:
        return flights[0]
    # Prefer adjusting the second listed aircraft (typical coordinator cue); tie-break stable
    return flights[1]


def _severity_from_sim(sev: str | None) -> str:
    s = (sev or "yellow").lower()
    return s if s in ("red", "yellow", "green") else "yellow"


def _make_candidate(
    rule: str,
    flights: list[str],
    severity: str,
    evidence_hint: str,
    sectors_map: dict[str, str],
) -> dict[str, Any]:
    flights = [str(f).strip() for f in flights if f]
    vf = _pick_vector_flight(flights)
    cur_sec = sectors_map.get(vf, "E05")
    tgt = pick_deterministic_reroute_sector(vf, cur_sec)
    sectors_involved = list({sectors_map.get(f, "?") for f in flights})
    return {
        "anchor_rule": rule,
        "flights": flights,
        "sectors_involved": sectors_involved,
        "severity": _severity_from_sim(severity),
        "evidence_hint": evidence_hint[:240],
        "reroute_flight": vf or (flights[0] if flights else ""),
        "reroute_target_sector": tgt,
        "sector_before_reroute": cur_sec,
    }


def build_advisory_candidates(
    tick: TickData,
    rules_output: RulesEngineOutput,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """One candidate row per distinct rules outcome / simulator alert (deduped)."""
    sectors_map = _sector_map(payload)
    seen: set[tuple[str, tuple[str, ...]]] = set()
    out: list[dict[str, Any]] = []

    for v in rules_output.violations:
        key = (v.rule, tuple(sorted(v.flights)))
        if key in seen:
            continue
        seen.add(key)
        hint = ""
        if getattr(v, "evidence", None):
            try:
                hint = json.dumps(v.evidence, default=str)[:400]
            except Exception:
                hint = str(v.evidence)[:400]
        out.append(
            _make_candidate(
                v.rule,
                list(v.flights),
                getattr(v, "severity", "yellow"),
                hint,
                sectors_map,
            )
        )

    for a in payload.get("alerts") or []:
        if not isinstance(a, dict):
            continue
        ru = str(a.get("rule") or "")
        fl = a.get("flights") or []
        if not isinstance(fl, list) or not ru:
            continue
        key = (ru, tuple(sorted(str(x) for x in fl)))
        if key in seen:
            continue
        seen.add(key)
        hint = json.dumps({k: a[k] for k in ("distance", "severity") if k in a}, default=str)[
            :240
        ]
        out.append(
            _make_candidate(
                ru,
                [str(x) for x in fl],
                str(a.get("severity") or "yellow"),
                hint,
                sectors_map,
            )
        )

    return out


def _cause_phrase(rule: str) -> str:
    r = rule.lower()
    if "minimum_separation" in r or r == "separation":
        return "closing spacing below IFR minima"
    if "storm" in r or r == "weather":
        return "weather-driven track convergence toward hazardous convection"
    if "wake" in r:
        return "heavy-aircraft wake spacing"
    if "crossing" in r or "track_crossing" in r:
        return "crossing-track geometry with insufficient vertical separation"
    if "runway" in r or "hold" in r:
        return "runway saturation / extended holding"
    if "crash" in r:
        return "immediate loss of separation"
    return "the flagged rule condition"


def build_fallback_summary(candidate: dict[str, Any], variant_index: int) -> str:
    """Deterministic, varied wording tied to this candidate only."""
    flights = candidate.get("flights") or []
    rule = candidate.get("anchor_rule") or "alert"
    secs = candidate.get("sectors_involved") or []
    s0, s1 = (secs + ["?", "?"])[:2]
    cause = _cause_phrase(rule)

    if len(flights) >= 2:
        f0, f1 = flights[0], flights[1]
        rotating = [
            f"Potential separation conflict detected between {f0} and {f1} due to {cause} near Sector {s0}.",
            f"Conflict risk between flights {f0} and {f1} — {cause} with involvement near sectors {s0} and {s1}.",
            f"Traffic convergence flagged for {f0} and {f1}: {cause}; monitor Sector {s0} airspace.",
            f"Potential separation conflict detected between {f0} and {f1} due to weather-induced convergence near Sector {s0}.",
        ]
        return rotating[variant_index % len(rotating)]
    if len(flights) == 1:
        f0 = flights[0]
        return (
            f"Hazard / spacing advisory for {f0}: {cause} with current assignment near Sector {s0}."
        )
    return f"Rule-backed advisory ({rule}): review sectors {', '.join(secs)}."


def build_fallback_recommendation(candidate: dict[str, Any]) -> str:
    rf = candidate.get("reroute_flight") or ""
    tgt = candidate.get("reroute_target_sector") or "A12"
    rule = (candidate.get("anchor_rule") or "").lower()
    if not rf:
        return f"Assign vectors or altitude crossing consistent with rule {candidate.get('anchor_rule')}."
    if "storm" in rule:
        return (
            f"Recommend rerouting flight {rf} through sector {tgt} to orbit clear of the hazard cell."
        )
    if "wake" in rule:
        return f"Recommend rerouting or staggering flight {rf} via sector {tgt} to increase trail spacing."
    return (
        f"Recommend rerouting flight {rf} through sector {tgt} until spacing and hazards are resolved."
    )


def finalize_advisories(
    candidates: list[dict[str, Any]],
    parsed_model_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Ensure one row per candidate. Prefer model wording only when flights match exactly.
    """
    result: list[dict[str, Any]] = []
    for i, cand in enumerate(candidates):
        fb_summary = build_fallback_summary(cand, i)
        fb_rec = build_fallback_recommendation(cand)
        fb_row = {
            "summary": fb_summary,
            "recommendation": fb_rec,
            "flights": cand["flights"],
            "sectors_involved": cand["sectors_involved"],
            "severity": cand["severity"],
            "anchor_rule": cand["anchor_rule"],
        }
        mrow = parsed_model_rows[i] if i < len(parsed_model_rows) else {}
        mf = mrow.get("flights") if isinstance(mrow.get("flights"), list) else []
        cf = cand["flights"]
        if (
            mrow
            and mrow.get("summary")
            and sorted(str(x) for x in mf) == sorted(str(x) for x in cf)
        ):
            result.append(
                {
                    **fb_row,
                    "summary": str(mrow.get("summary")).strip() or fb_summary,
                    "recommendation": str(mrow.get("recommendation") or "").strip() or fb_rec,
                    "severity": _severity_from_sim(mrow.get("severity")) or fb_row["severity"],
                }
            )
        else:
            result.append(fb_row)
    if not candidates and parsed_model_rows:
        for mrow in parsed_model_rows:
            if isinstance(mrow, dict) and mrow.get("summary"):
                result.append(
                    {
                        "summary": str(mrow.get("summary")),
                        "recommendation": str(mrow.get("recommendation") or ""),
                        "flights": mrow.get("flights") if isinstance(mrow.get("flights"), list) else [],
                        "sectors_involved": mrow.get("sectors_involved")
                        if isinstance(mrow.get("sectors_involved"), list)
                        else [],
                        "severity": _severity_from_sim(mrow.get("severity")),
                        "anchor_rule": "model_only",
                    }
                )
    return result


ADVISORY_JSON_SCHEMA = """Return ONLY valid JSON (no markdown fences) with:

{
  "multimodal_context": "<one sentence — telemetry + implied map context>",
  "advisories": [ ... ],
  "conflict_predictions": [ ... ]
}

Each advisory object MUST include:
  "summary": "<unique sentence; follow examples below>",
  "recommendation": "<cite one flight + one allowed sector ID>",
  "flights": ["CALLSIGN", ...],
  "sectors_involved": ["A12", ...],
  "severity": "red"|"yellow"|"green"

STYLE EXAMPLES (same facts, different flights/sectors — imitate closely):
- Potential separation conflict detected between ACA882 and DAL421 due to weather-induced convergence near Sector A12.
- Potential separation conflict detected between WJA103 and UAL220 due to closing spacing below IFR minima near sectors E05 and C03.

CONSTRAINTS:
- Use ONLY callsigns listed under NUMBERED CANDIDATES.
- Allowed reroute sectors ONLY: """ + ", ".join(
    VALID_HOLD_SECTORS
) + """.
- Emit EXACTLY len(NUMBERED CANDIDATES) advisories, SAME ORDER (index 0 matches candidate 1, etc.).
- Each summary must sound DIFFERENT (vary verbs and cause: separation, wake, storm, crossing, runway hold).
- Each recommendation must target ONE flight from that row and ONE sector from the allowed list.
- Ground truth for WHO conflicts with WHOM is the rules engine + candidates — do not invent aircraft.

ALSO include "conflict_predictions" (can be []): YOUR OWN forward-looking risk rows from numeric telemetry + weather —
pairs that deserve monitoring or possible convergence / wake / wx even if Python rules did not flag them this tick.
Use ONLY callsigns from PER-AIRCRAFT STATE. Max 6 rows. Each object:
  "flights": ["CALLSIGN_A","CALLSIGN_B"],
  "risk": "red"|"yellow",
  "rationale": "<one short sentence — geometry, METAR, or wake spacing>",
  "reroute_hint": "<optional: cite one flight + one allowed sector from the list below>"
Allowed reroute sectors ONLY: """ + ", ".join(VALID_HOLD_SECTORS) + """."""


def build_ml_advisory_prompt(
    tick: TickData,
    rules_output: RulesEngineOutput,
    frontend_payload: dict[str, Any],
) -> str:
    tick_json = format_tick_data(tick)
    rules_text = format_violations(rules_output)

    candidates = build_advisory_candidates(tick, rules_output, frontend_payload)
    numbered = []
    for i, c in enumerate(candidates, start=1):
        numbered.append(
            f"{i}. rule={c['anchor_rule']} | flights={c['flights']} | sectors_now={c['sectors_involved']} "
            f"| vector_priority={c['reroute_flight']} -> suggested_sector={c['reroute_target_sector']} "
            f"| evidence_hint={c['evidence_hint'][:160]}"
        )
    cand_block = "\n".join(numbered) if numbered else "(no candidate rows — return advisories: [])"

    fe_alerts = frontend_payload.get("alerts") or []
    fe_compact = json.dumps(fe_alerts, indent=2)[:6000]
    weather = json.dumps(frontend_payload.get("weather") or {}, indent=2)[:2000]

    roster_lines = []
    for ac in frontend_payload.get("aircraft") or []:
        cid = ac.get("callsign") or ac.get("id")
        roster_lines.append(
            f"- {cid}: sector={ac.get('sector_id')}, phase={ac.get('phase')}, rw={ac.get('runway')}, "
            f"alt_ft={ac.get('altitude_ft')}, hdg={ac.get('heading_deg')}, kts={ac.get('velocity_kts')}"
        )
    roster = "\n".join(roster_lines) if roster_lines else "(no aircraft in payload)"

    return f"""You are RunwAI (Qwen), assisting ATC at CYYZ.

You MUST tie every sentence to the NUMBERED CANDIDATES — those rows are derived from the deterministic rules engine
AND simulator alerts. JSON gives precise numbers; the live map (not sent here) shows geometry — acknowledge that fusion.

{ADVISORY_JSON_SCHEMA}

--- PER-AIRCRAFT STATE (simulation export; authoritative callsigns / sectors) ---
{roster}

--- AIRCRAFT TELEMETRY (numeric, rules preprocessing) ---
{tick_json}

--- PYTHON RULES ENGINE (authoritative violations) ---
{rules_text}

--- NUMBERED CANDIDATES (emit exactly one advisory per line, same order, same flights) ---
{cand_block}

--- FRONTEND SIMULATION ALERTS (same tick; used to build candidates) ---
{fe_compact}

--- WEATHER ENVELOPE ---
{weather}

Return the JSON object now."""


def _roster_callsigns(frontend_payload: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for ac in frontend_payload.get("aircraft") or []:
        cid = str(ac.get("callsign") or ac.get("id") or "").strip()
        if cid:
            out.add(cid)
    return out


def _parse_conflict_predictions(
    data: dict[str, Any], roster: set[str] | None
) -> list[dict[str, Any]]:
    raw = data.get("conflict_predictions")
    if not isinstance(raw, list):
        return []
    preds: list[dict[str, Any]] = []
    for p in raw[:8]:
        if not isinstance(p, dict):
            continue
        fl = p.get("flights")
        if not isinstance(fl, list) or len(fl) < 2:
            continue
        a, b = str(fl[0]).strip(), str(fl[1]).strip()
        if roster is not None and (a not in roster or b not in roster):
            continue
        risk = str(p.get("risk") or "yellow").lower()
        if risk not in ("red", "yellow"):
            risk = "yellow"
        preds.append(
            {
                "flights": [a, b],
                "risk": risk,
                "rationale": str(p.get("rationale") or "").strip()[:400],
                "reroute_hint": str(p.get("reroute_hint") or "").strip()[:400],
            }
        )
    return preds


def _dedupe_predictions_against_advisories(
    predictions: list[dict[str, Any]],
    finalized_advisories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop prediction pairs already covered by a finalized advisory row (same two flights)."""
    covered: set[tuple[str, str]] = set()
    for row in finalized_advisories:
        fs = row.get("flights") if isinstance(row.get("flights"), list) else []
        if len(fs) >= 2:
            covered.add(tuple(sorted([str(fs[0]), str(fs[1])])))
    out: list[dict[str, Any]] = []
    for p in predictions:
        fs = p.get("flights") or []
        if len(fs) < 2:
            continue
        key = tuple(sorted([str(fs[0]), str(fs[1])]))
        if key in covered:
            continue
        out.append(p)
    return out


def parse_ml_advisory_bundle(text: str) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """Parse model JSON once; return (advisories, multimodal_context, conflict_predictions)."""
    raw = (text or "").strip()
    if not raw:
        return [], "", []

    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return (
            [
                {
                    "summary": raw[:400] + ("..." if len(raw) > 400 else ""),
                    "recommendation": "Model returned non-JSON; using rule-based fallback.",
                    "flights": [],
                    "sectors_involved": [],
                    "severity": "yellow",
                }
            ],
            "",
            [],
        )

    mm = data.get("multimodal_context")
    multimodal = str(mm).strip() if mm else ""

    advisories = data.get("advisories")
    if not isinstance(advisories, list):
        advisories = []

    out: list[dict[str, Any]] = []
    for a in advisories:
        if not isinstance(a, dict):
            continue
        out.append(
            {
                "summary": str(a.get("summary", "")).strip() or "Advisory",
                "recommendation": str(a.get("recommendation", "")).strip()
                or "No specific recommendation.",
                "flights": a.get("flights") if isinstance(a.get("flights"), list) else [],
                "sectors_involved": a.get("sectors_involved")
                if isinstance(a.get("sectors_involved"), list)
                else [],
                "severity": str(a.get("severity", "yellow")).lower()
                if a.get("severity")
                else "yellow",
            }
        )

    if not out and data.get("reasoning") is not None and not advisories:
        out.append(
            {
                "summary": "LLM returned legacy schema instead of advisories.",
                "recommendation": str(data.get("reasoning", ""))[:800],
                "flights": [],
                "sectors_involved": [],
                "severity": "yellow",
            }
        )

    preds = _parse_conflict_predictions(data, None)

    return out, multimodal, preds


def _filter_predictions_roster(
    preds: list[dict[str, Any]], roster: set[str]
) -> list[dict[str, Any]]:
    if not roster:
        return []
    out: list[dict[str, Any]] = []
    for p in preds:
        fs = p.get("flights") or []
        if len(fs) < 2:
            continue
        if fs[0] in roster and fs[1] in roster:
            out.append(p)
    return out


def parse_ml_advisory_response(text: str) -> list[dict[str, Any]]:
    adv, _, _ = parse_ml_advisory_bundle(text)
    return adv


def build_and_finalize_advisories(
    tick: TickData,
    rules_output: RulesEngineOutput,
    payload: dict[str, Any],
    raw_model_text: str,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    """Parse model output and merge with rule-anchored candidates (one row per aircraft pair / alert)."""
    roster = _roster_callsigns(payload)
    candidates = build_advisory_candidates(tick, rules_output, payload)
    parsed, mm, preds_loose = parse_ml_advisory_bundle(raw_model_text)
    preds_raw = _filter_predictions_roster(preds_loose, roster)
    finalized = finalize_advisories(candidates, parsed)
    predictions = _dedupe_predictions_against_advisories(preds_raw, finalized)
    return finalized, mm, predictions
