"""
Layer 3 - Prompt Builder

Assembles the final prompt for the VLM by combining:
- Tick data (flights, weather)
- Rules engine output (violations)
- Visual context (placeholder)
"""

from .builder import build_prompt, format_tick_data, format_violations
from .templates import SYSTEM_ROLE, RULE_DEFINITIONS, OUTPUT_SCHEMA

__all__ = [
    "build_prompt",
    "format_tick_data", 
    "format_violations",
    "SYSTEM_ROLE",
    "RULE_DEFINITIONS",
    "OUTPUT_SCHEMA",
]
