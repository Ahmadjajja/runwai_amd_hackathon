"""
Layer 6 — Model Response Parser

Parses the VLM's JSON response into a structured ModelResponse.
Handles common edge cases:
- Markdown-wrapped JSON (```json ... ```)
- Extra text before/after JSON
- Malformed JSON
"""

import json
import re
from typing import Tuple, Optional

from ..preprocessing import ModelResponse, RecommendedAction


class ParseError(Exception):
    """Raised when model response cannot be parsed."""
    pass


def extract_json_from_text(text: str) -> str:
    """
    Extract JSON object from text that may contain markdown or extra content.
    """
    text = text.strip()
    
    # Try to extract from markdown code block
    md_pattern = r'```(?:json)?\s*(\{[\s\S]*?\})\s*```'
    md_match = re.search(md_pattern, text)
    if md_match:
        return md_match.group(1)
    
    # Try to find JSON object directly
    # Look for outermost { ... }
    brace_start = text.find('{')
    if brace_start == -1:
        raise ParseError("No JSON object found in response")
    
    # Find matching closing brace
    depth = 0
    for i, char in enumerate(text[brace_start:], start=brace_start):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[brace_start:i+1]
    
    raise ParseError("Unbalanced braces in JSON")


def parse_model_response(response_text: str) -> Tuple[Optional[ModelResponse], Optional[str]]:
    """
    Parse model response text into ModelResponse object.
    
    Args:
        response_text: Raw text from the model
        
    Returns:
        (ModelResponse, None) on success
        (None, error_message) on failure
    """
    if not response_text or not response_text.strip():
        return None, "Empty response from model"
    
    try:
        json_str = extract_json_from_text(response_text)
        data = json.loads(json_str)
    except ParseError as e:
        return None, f"Failed to extract JSON: {e}"
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"
    
    # Validate required fields
    if "reasoning" not in data:
        return None, "Missing required field: reasoning"
    
    if "model_confidence" not in data:
        return None, "Missing required field: model_confidence"
    
    # Parse recommended_action if present
    action = None
    if data.get("recommended_action"):
        action_data = data["recommended_action"]
        
        if "target_flight" not in action_data:
            return None, "recommended_action missing target_flight"
        if "type" not in action_data:
            return None, "recommended_action missing type"
        
        valid_types = {"heading_change", "altitude_change", "speed_change", "hold"}
        if action_data["type"] not in valid_types:
            return None, f"Invalid action type: {action_data['type']}. Must be one of {valid_types}"
        
        action = RecommendedAction(
            target_flight=action_data["target_flight"],
            type=action_data["type"],
            value=action_data.get("value"),
        )
    
    # Build ModelResponse
    try:
        confidence = float(data["model_confidence"])
        if not 0.0 <= confidence <= 1.0:
            return None, f"model_confidence must be 0.0-1.0, got {confidence}"
    except (TypeError, ValueError):
        return None, f"Invalid model_confidence: {data['model_confidence']}"
    
    response = ModelResponse(
        reasoning=str(data["reasoning"]),
        recommended_action=action,
        model_confidence=confidence,
    )
    
    return response, None
