"""
RunwAI - AI Air Traffic Control System

Layers:
- Layer 1 (ingestion): Data sources (OpenSky, Weather, FR24)
- Layer 2 (preprocessing): JSON formatting, schema validation
- Layer 3 (prompt): Prompt builder for VLM
- Layer 4 (model): VLM adapter (Qwen via HuggingFace)
- Layer 5 (rules): Conflict detection rules engine
- Layer 6 (decision): Decision validation and simulation
- Layer 7 (frontend): Real-time airport simulation UI
"""

__version__ = "1.0.0"
