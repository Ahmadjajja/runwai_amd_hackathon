"""
Layer 6 — Decision Engine

Orchestrates the full decision pipeline:
1. Parse model response
2. Validate the action
3. Simulate to check for new conflicts
4. Assign sector
5. Compute latency
6. Emit final decision

Includes retry loop for invalid/conflicting actions.
"""

import time
from typing import Optional, Callable

from ..preprocessing import (
    TickData, 
    RulesEngineOutput, 
    ModelResponse, 
    ValidatedDecision,
    Violation,
)
from .parser import parse_model_response
from .validator import validate_action
from .simulator import simulate_action
from .sector import assign_sector


class DecisionEngine:
    """
    Layer 6 Decision Engine.
    
    Validates model suggestions and produces final decisions.
    """
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def process(
        self,
        tick: TickData,
        rules_output: RulesEngineOutput,
        model_response_text: str,
        tick_start_time: float,
        retry_callback: Optional[Callable[[str, str], str]] = None,
    ) -> ValidatedDecision:
        """
        Process a model response and produce a validated decision.
        
        Args:
            tick: Current tick data
            rules_output: Output from rules engine
            model_response_text: Raw text from the model
            tick_start_time: time.time() when tick processing began
            retry_callback: Optional function to call model again on failure.
                           Signature: (original_prompt, feedback) -> new_response_text
        
        Returns:
            ValidatedDecision with all validation results
        """
        original_violation = rules_output.violations[0] if rules_output.violations else None
        
        for attempt in range(self.max_retries + 1):
            # Step 1: Parse model response
            response, parse_error = parse_model_response(model_response_text)
            
            if parse_error:
                if attempt < self.max_retries and retry_callback:
                    feedback = f"PARSE ERROR: {parse_error}. Return valid JSON."
                    model_response_text = retry_callback("", feedback)
                    continue
                else:
                    return self._error_decision(
                        tick, original_violation, tick_start_time,
                        f"Parse failed after {attempt + 1} attempts: {parse_error}",
                        attempt
                    )
            
            # Step 2: Validate the action
            valid, validation_notes = validate_action(response, tick, rules_output)
            
            if not valid:
                if attempt < self.max_retries and retry_callback:
                    feedback = f"VALIDATION ERROR: {validation_notes}. Fix and retry."
                    model_response_text = retry_callback("", feedback)
                    continue
                else:
                    return self._error_decision(
                        tick, original_violation, tick_start_time,
                        f"Validation failed: {validation_notes}",
                        attempt,
                        response
                    )
            
            # Step 3: Simulate action (only if action exists)
            if response.recommended_action:
                creates_conflict, new_violations, sim_notes = simulate_action(
                    tick, 
                    response.recommended_action,
                    rules_output.violations
                )
                
                if creates_conflict:
                    if attempt < self.max_retries and retry_callback:
                        conflict_flights = ", ".join(
                            v.flights[0] for v in new_violations[:2]
                        )
                        feedback = (
                            f"SIMULATION ERROR: Your suggestion creates new conflict "
                            f"with {conflict_flights}. Suggest different action."
                        )
                        model_response_text = retry_callback("", feedback)
                        continue
                    else:
                        return self._error_decision(
                            tick, original_violation, tick_start_time,
                            f"Action creates new conflict: {sim_notes}",
                            attempt,
                            response
                        )
                
                validation_notes += f" | Simulation: {sim_notes}"
            
            # Step 4: Assign sector
            sector = None
            if response.recommended_action:
                target = next(
                    (f for f in tick.flights if f.callsign == response.recommended_action.target_flight),
                    None
                )
                if target:
                    sector = assign_sector(target)
            
            # Step 5: Compute latency
            latency_ms = (time.time() - tick_start_time) * 1000
            
            # Step 6: Build final decision
            return ValidatedDecision(
                tick_id=tick.tick_id,
                original_violation=original_violation,
                model_response=response,
                action_valid=True,
                validation_notes=validation_notes,
                assigned_sector=sector,
                latency_ms=round(latency_ms, 2),
                retry_count=attempt,
            )
        
        # Should not reach here
        return self._error_decision(
            tick, original_violation, tick_start_time,
            "Max retries exceeded",
            self.max_retries
        )
    
    def _error_decision(
        self,
        tick: TickData,
        original_violation: Optional[Violation],
        tick_start_time: float,
        error_message: str,
        retry_count: int,
        response: Optional[ModelResponse] = None,
    ) -> ValidatedDecision:
        """Build an error decision when processing fails."""
        latency_ms = (time.time() - tick_start_time) * 1000
        
        return ValidatedDecision(
            tick_id=tick.tick_id,
            original_violation=original_violation,
            model_response=response or ModelResponse(
                reasoning=f"[ERROR] {error_message}",
                recommended_action=None,
                model_confidence=0.0,
            ),
            action_valid=False,
            validation_notes=error_message,
            assigned_sector=None,
            latency_ms=round(latency_ms, 2),
            retry_count=retry_count,
        )


def process_decision(
    tick: TickData,
    rules_output: RulesEngineOutput,
    model_response_text: str,
    tick_start_time: Optional[float] = None,
) -> ValidatedDecision:
    """
    Convenience function to process a decision without instantiating engine.
    """
    engine = DecisionEngine()
    start = tick_start_time or time.time()
    return engine.process(tick, rules_output, model_response_text, start)
