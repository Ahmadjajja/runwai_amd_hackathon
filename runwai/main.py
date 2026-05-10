"""
RunwAI - Main Orchestrator

This is the main entry point that ties all layers together:
1. Fetch data from Layer 1 (ingestion)
2. Preprocess into TickData (Layer 2)
3. Run rules engine (Layer 5)
4. Build prompt (Layer 3)
5. Call model (Layer 4)
6. Validate decision (Layer 6)

Usage:
    python -m runwai.main              # Run once
    python -m runwai.main --live       # Continuous loop
    python -m runwai.main --scenario separation  # Run test scenario
"""

from .env_bootstrap import load_repo_dotenv

load_repo_dotenv()

import argparse
import time
import json
from pathlib import Path

# Layer 1 - Data Ingestion
from .ingestion import fetch_flights, fetch_weather, fetch_enriched_flights, build_enrichment_map

# Layer 2 - Preprocessing
from .preprocessing import preprocess_tick, TickData, Flight, Weather

# Layer 3 - Prompt Builder
from .prompt import build_prompt

# Layer 4 - Model
from .model import call_model

# Layer 5 - Rules Engine
from .rules import run_all_rules

# Layer 6 - Decision Making
from .decision import DecisionEngine


def run_single_tick(use_mock: bool = False, debug: bool = False) -> dict:
    """
    Execute a single processing tick through all layers.
    
    Returns:
        Dict with tick results including decision
    """
    tick_start = time.time()

    print("\n" + "="*60)
    print("RunwAI - Processing Tick")
    print("="*60)
    
    # Layer 1: Fetch data
    print("\n[Layer 1] Fetching data...")
    flights_raw = fetch_flights()
    weather_raw = fetch_weather()
    enrichment = fetch_enriched_flights()
    enrichment_map = build_enrichment_map(enrichment)
    
    print(f"  - Flights: {len(flights_raw)}")
    print(f"  - Weather: {weather_raw.get('station', 'CYYZ')}")
    print(f"  - Enrichment: {len(enrichment_map)} callsigns")
    
    # Layer 2: Preprocess
    print("\n[Layer 2] Preprocessing...")
    tick = preprocess_tick(flights_raw, weather_raw, enrichment_map)
    print(f"  - Tick ID: {tick.tick_id}")
    print(f"  - Airborne: {len([f for f in tick.flights if not f.on_ground])}")
    
    # Layer 5: Run rules
    print("\n[Layer 5] Running rules engine...")
    rules_output = run_all_rules(tick)
    print(f"  - Rules evaluated: {rules_output.rules_evaluated}")
    print(f"  - Violations: {len(rules_output.violations)}")
    
    for v in rules_output.violations:
        print(f"    [{v.severity.upper()}] {v.rule}: {v.flights}")
    
    # Layer 3: Build prompt
    print("\n[Layer 3] Building prompt...")
    prompt = build_prompt(tick, rules_output)
    if debug:
        print(f"  - Prompt length: {len(prompt)} chars")
    
    # Layer 4: Call model
    print("\n[Layer 4] Calling model...")
    model_response_text = call_model(prompt, debug_print=debug)
    print(f"  - Response length: {len(model_response_text)} chars")
    
    # Layer 6: Validate decision
    print("\n[Layer 6] Validating decision...")
    engine = DecisionEngine()

    decision = engine.process(
        tick=tick,
        rules_output=rules_output,
        model_response_text=model_response_text,
        tick_start_time=tick_start,
    )
    
    print(f"  - Valid: {decision.action_valid}")
    print(f"  - Notes: {decision.validation_notes}")
    print(f"  - Sector: {decision.assigned_sector}")
    print(f"  - Latency: {decision.latency_ms:.0f}ms")
    
    if decision.model_response.recommended_action:
        action = decision.model_response.recommended_action
        print(f"  - Action: {action.target_flight} -> {action.type} {action.value}")
    
    print("\n" + "="*60)
    
    return {
        "tick_id": tick.tick_id,
        "violations": len(rules_output.violations),
        "decision_valid": decision.action_valid,
        "action": decision.model_response.recommended_action,
    }


def run_scenario(scenario_name: str) -> dict:
    """
    Run a test scenario from fixtures.
    """
    fixtures_dir = Path(__file__).parent / "fixtures"
    fixture_path = fixtures_dir / f"tick_{scenario_name}.json"
    
    if not fixture_path.exists():
        print(f"Scenario '{scenario_name}' not found at {fixture_path}")
        return {}
    
    print(f"\n[Scenario] Loading {scenario_name}...")
    
    with open(fixture_path) as f:
        data = json.load(f)
    
    # Build TickData from fixture
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
    
    # Run through layers 5, 3, 4, 6
    rules_output = run_all_rules(tick)
    prompt = build_prompt(tick, rules_output)
    tick_start = time.time()
    model_response_text = call_model(prompt, debug_print=False)

    engine = DecisionEngine()
    decision = engine.process(tick, rules_output, model_response_text, tick_start)
    
    print(f"\n[Result] {scenario_name}")
    print(f"  Violations: {len(rules_output.violations)}")
    print(f"  Decision valid: {decision.action_valid}")
    
    return {
        "scenario": scenario_name,
        "violations": len(rules_output.violations),
        "decision_valid": decision.action_valid,
    }


def run_live_loop(interval: int = 10):
    """
    Continuous processing loop.
    """
    print("\nRunwAI Live Mode - Press Ctrl+C to stop")
    print(f"Processing every {interval} seconds\n")
    
    tick_count = 0
    try:
        while True:
            tick_count += 1
            print(f"\n{'='*60}")
            print(f"Tick #{tick_count}")
            
            try:
                result = run_single_tick()
                print(f"Result: {result['violations']} violations, valid={result['decision_valid']}")
            except Exception as e:
                print(f"Error: {e}")
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print(f"\n\nStopped after {tick_count} ticks.")


def main():
    parser = argparse.ArgumentParser(description="RunwAI - AI Air Traffic Control")
    parser.add_argument("--live", action="store_true", help="Run in continuous loop mode")
    parser.add_argument("--interval", type=int, default=10, help="Seconds between ticks in live mode")
    parser.add_argument("--scenario", type=str, help="Run a test scenario (separation, storm, wake, clean)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    if args.scenario:
        run_scenario(args.scenario)
    elif args.live:
        run_live_loop(args.interval)
    else:
        run_single_tick(debug=args.debug)


if __name__ == "__main__":
    main()
