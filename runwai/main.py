"""
RunwAI - Main Orchestrator

Usage:
    python -m runwai.main                        # single tick (live data)
    python -m runwai.main --scenario separation  # test scenario
    python -m runwai.main --live --interval 10   # continuous loop
    python -m runwai.main --debug                # verbose output
"""

import argparse
import time
import json
from pathlib import Path

# Layer 1 - Data Ingestion
from .ingestion import (
    fetch_flights, fetch_weather, fetch_enriched_flights, build_enrichment_map,
    get_latest_frame,
)

# Layer 2 - Preprocessing
from .preprocessing import TickData, Flight, Weather
from .preprocessing.formatter import preprocess_tick

# Layer 3 - Prompt Builder
from .prompt import build_prompt

# Layer 4 - Model
from .model import call_model
from .model.adapter import load_frame_b64

# Layer 5 - Rules Engine
from .rules import run_all_rules

# Layer 6 - Decision Making
from .decision import DecisionEngine


def run_single_tick(debug: bool = False) -> dict:
    """
    Execute a single processing tick through all layers.
    Returns a rich dict suitable for the frontend API.
    """
    tick_start_time = time.time()

    print("\n" + "=" * 60)
    print("RunwAI — Processing Tick")
    print("=" * 60)

    # Layer 1: Fetch data
    print("\n[Layer 1] Fetching data...")
    flights_raw   = fetch_flights()
    weather_raw   = fetch_weather()
    enrichment    = fetch_enriched_flights()
    enrichment_map = build_enrichment_map(enrichment)

    print(f"  - Flights:     {len(flights_raw)}")
    print(f"  - Weather:     {weather_raw.get('station', 'CYYZ')}")
    print(f"  - Enrichment:  {len(enrichment_map)} callsigns")

    # Layer 2: Preprocess
    print("\n[Layer 2] Preprocessing...")
    tick = preprocess_tick(flights_raw, weather_raw, enrichment_map)
    print(f"  - Tick ID:     {tick.tick_id}")
    print(f"  - Airborne:    {len([f for f in tick.flights if not f.on_ground])}")

    # Attach latest video frame to tick
    frame_path = get_latest_frame()
    if frame_path:
        tick.frame_path = frame_path
        print(f"  - Frame:       {Path(frame_path).name}")
    else:
        print("  - Frame:       none (run video_processor.py first)")

    # Layer 5: Run rules
    print("\n[Layer 5] Running rules engine...")
    rules_output = run_all_rules(tick)
    print(f"  - Evaluated:   {rules_output.rules_evaluated}")
    print(f"  - Violations:  {len(rules_output.violations)}")
    for v in rules_output.violations:
        print(f"    [{v.severity.upper()}] {v.rule}: {v.flights}")

    # Layer 3: Build prompt
    print("\n[Layer 3] Building prompt...")
    visual_ctx = (
        "Runway frame image attached — use it to confirm aircraft positions and runway state."
        if frame_path else None
    )
    prompt = build_prompt(tick, rules_output, visual_context=visual_ctx)
    if debug:
        print(f"  - Prompt length: {len(prompt)} chars")

    # Layer 4: Call model (multimodal when frame is available)
    print("\n[Layer 4] Calling model...")
    frame_b64 = load_frame_b64(frame_path)
    model_response_text = call_model(prompt, frame_b64=frame_b64, debug_print=debug)
    print(f"  - Response length: {len(model_response_text)} chars")

    # Layer 6: Validate decision
    print("\n[Layer 6] Validating decision...")
    engine   = DecisionEngine()
    decision = engine.process(
        tick=tick,
        rules_output=rules_output,
        model_response_text=model_response_text,
        tick_start_time=tick_start_time,
    )

    print(f"  - Valid:     {decision.action_valid}")
    print(f"  - Notes:     {decision.validation_notes}")
    print(f"  - Sector:    {decision.assigned_sector}")
    print(f"  - Latency:   {decision.latency_ms:.0f} ms")
    if decision.model_response.recommended_action:
        a = decision.model_response.recommended_action
        print(f"  - Action:    {a.target_flight} → {a.type} {a.value}")

    print("\n" + "=" * 60)

    return _build_response(tick, rules_output, decision)


def run_scenario(scenario_name: str) -> dict:
    """Run a test scenario from fixtures."""
    tick_start_time = time.time()
    fixtures_dir = Path(__file__).parent / "fixtures"
    fixture_path = fixtures_dir / f"tick_{scenario_name}.json"

    if not fixture_path.exists():
        print(f"Scenario '{scenario_name}' not found at {fixture_path}")
        return {}

    print(f"\n[Scenario] Loading {scenario_name}...")

    with open(fixture_path) as f:
        data = json.load(f)

    from .preprocessing import Flight, Weather, TickData

    flights = [Flight(**f) for f in data.get("flights", [])]
    weather = Weather(**data.get("weather", {}))
    tick = TickData(
        tick_id=data.get("tick_id", f"scenario-{scenario_name}"),
        timestamp=data.get("timestamp", ""),
        airport=data.get("airport", "CYYZ"),
        flights=flights,
        weather=weather,
    )

    # Attach frame if available
    frame_path = get_latest_frame()
    if frame_path:
        tick.frame_path = frame_path

    rules_output = run_all_rules(tick)

    visual_ctx = (
        "Runway frame image attached." if frame_path else None
    )
    prompt = build_prompt(tick, rules_output, visual_context=visual_ctx)
    frame_b64 = load_frame_b64(frame_path)
    model_response_text = call_model(prompt, frame_b64=frame_b64, debug_print=False)

    engine   = DecisionEngine()
    decision = engine.process(
        tick=tick,
        rules_output=rules_output,
        model_response_text=model_response_text,
        tick_start_time=tick_start_time,
    )

    print(f"\n[Result] {scenario_name}")
    print(f"  Violations:     {len(rules_output.violations)}")
    print(f"  Decision valid: {decision.action_valid}")

    return _build_response(tick, rules_output, decision)


def _build_response(tick: TickData, rules_output, decision) -> dict:
    """Assemble the rich response dict used by the API and CLI."""
    return {
        "tick_id": tick.tick_id,
        "flights": [
            {
                "callsign":         f.callsign,
                "latitude":         f.latitude,
                "longitude":        f.longitude,
                "altitude_ft":      round(f.alt_ft),
                "speed_kt":         round(f.velocity_kt),
                "heading_deg":      f.heading_deg,
                "vertical_rate_fpm": round(f.vertical_rate_fpm),
                "on_ground":        f.on_ground,
                "weight_class":     f.weight_class or "Unknown",
                "aircraft_code":    f.aircraft_code or "UNK",
            }
            for f in tick.flights
        ],
        "weather": {
            "wind_dir_deg":   tick.weather.wind_dir_deg,
            "wind_speed_kts": tick.weather.wind_speed_kts,
            "wind_gust_kts":  tick.weather.wind_gust_kts,
            "storm_warning":  tick.weather.storm_warning,
            "low_visibility": tick.weather.low_visibility,
            "raw_metar":      tick.weather.raw_metar,
        },
        "violations": [
            {
                "rule":       v.rule,
                "flights":    v.flights,
                "severity":   v.severity,
                "evidence":   v.evidence,
                "confidence": v.confidence,
            }
            for v in rules_output.violations
        ],
        "decision": {
            "reasoning":   decision.model_response.reasoning,
            "action":      (
                decision.model_response.recommended_action.model_dump()
                if decision.model_response.recommended_action else None
            ),
            "confidence":  decision.model_response.model_confidence,
            "valid":       decision.action_valid,
            "sector":      decision.assigned_sector,
            "latency_ms":  decision.latency_ms,
            "retry_count": decision.retry_count,
        },
    }


def run_live_loop(interval: int = 10):
    """Continuous processing loop."""
    print(f"\nRunwAI Live Mode — Ctrl+C to stop  (interval: {interval}s)\n")
    tick_count = 0
    try:
        while True:
            tick_count += 1
            print(f"\n{'='*60}\nTick #{tick_count}")
            try:
                result = run_single_tick()
                print(
                    f"Result: {len(result.get('violations', []))} violations, "
                    f"valid={result['decision']['valid']}, "
                    f"latency={result['decision']['latency_ms']:.0f}ms"
                )
            except Exception as e:
                print(f"Error: {e}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n\nStopped after {tick_count} ticks.")


def main():
    parser = argparse.ArgumentParser(description="RunwAI — AI Air Traffic Control")
    parser.add_argument("--live",     action="store_true", help="Run in continuous loop mode")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between ticks (live mode)")
    parser.add_argument("--scenario", type=str, help="Run test scenario: separation | storm | wake | clean")
    parser.add_argument("--debug",    action="store_true", help="Enable verbose output")
    args = parser.parse_args()

    if args.scenario:
        run_scenario(args.scenario)
    elif args.live:
        run_live_loop(args.interval)
    else:
        run_single_tick(debug=args.debug)


if __name__ == "__main__":
    main()
