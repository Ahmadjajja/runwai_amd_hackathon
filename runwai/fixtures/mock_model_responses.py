"""
Mock model responses for testing Layer 6.

These simulate what the VLM would return for different scenarios.
"""

# Good response for separation violation
RESPONSE_SEPARATION_GOOD = '''{
  "reasoning": "ACA456 and WJA123 are only 2.61 NM apart with 500 ft vertical separation, violating the 5 NM / 1000 ft minimum. Recommending WJA123 turn right to increase lateral separation while maintaining approach sequence.",
  "recommended_action": {
    "target_flight": "WJA123",
    "type": "heading_change",
    "value": "+15deg"
  },
  "model_confidence": 0.85
}'''

# Good response for storm avoidance
RESPONSE_STORM_GOOD = '''{
  "reasoning": "ACA789 is projected to enter severe storm sector B07 within 60 seconds. Immediate heading change required to vector around the cell.",
  "recommended_action": {
    "target_flight": "ACA789",
    "type": "heading_change",
    "value": "+45deg"
  },
  "model_confidence": 0.92
}'''

# Good response for wake turbulence
RESPONSE_WAKE_GOOD = '''{
  "reasoning": "Light aircraft CGG999 (C172) is trailing heavy ACA001 (B777) at only 1.77 NM and 500 ft below - severe wake turbulence risk. Instructing CGG999 to climb above the wake vortices.",
  "recommended_action": {
    "target_flight": "CGG999",
    "type": "altitude_change",
    "value": "+1000ft"
  },
  "model_confidence": 0.88
}'''

# Good response for no violations
RESPONSE_CLEAN = '''{
  "reasoning": "No safety violations detected. All aircraft are maintaining proper separation and avoiding hazardous weather.",
  "recommended_action": null,
  "model_confidence": 1.0
}'''

# Bad response - nonexistent flight
RESPONSE_BAD_FLIGHT = '''{
  "reasoning": "There's a conflict, let me fix it.",
  "recommended_action": {
    "target_flight": "FAKE123",
    "type": "heading_change",
    "value": "+20deg"
  },
  "model_confidence": 0.75
}'''

# Bad response - invalid action type
RESPONSE_BAD_ACTION_TYPE = '''{
  "reasoning": "Aircraft needs to move.",
  "recommended_action": {
    "target_flight": "ACA456",
    "type": "barrel_roll",
    "value": "360deg"
  },
  "model_confidence": 0.50
}'''

# Bad response - extreme value
RESPONSE_BAD_VALUE = '''{
  "reasoning": "Turn hard to avoid.",
  "recommended_action": {
    "target_flight": "WJA123",
    "type": "heading_change",
    "value": "+180deg"
  },
  "model_confidence": 0.60
}'''

# Bad response - not JSON
RESPONSE_NOT_JSON = '''
I think the aircraft should turn right about 15 degrees to avoid the conflict.
The situation looks dangerous and immediate action is needed.
'''

# Response wrapped in markdown
RESPONSE_MARKDOWN_WRAPPED = '''Here's my analysis:

```json
{
  "reasoning": "Separation violation detected. Recommending heading change.",
  "recommended_action": {
    "target_flight": "WJA123",
    "type": "heading_change",
    "value": "+20deg"
  },
  "model_confidence": 0.80
}
```

Let me know if you need anything else.'''

# Response missing fields
RESPONSE_MISSING_FIELDS = '''{
  "reasoning": "There's a problem here."
}'''
