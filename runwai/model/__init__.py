"""
Layer 4 - Model Adapter

Interface to the VLM (Qwen) via HuggingFace Inference API.
"""

from .adapter import call_model

__all__ = ["call_model"]
