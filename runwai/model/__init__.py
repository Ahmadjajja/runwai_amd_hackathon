"""
Layer 4 — Model adapter

Qwen (or other OSS instruct models) via **LangChain** ``ChatOpenAI`` when configured,
with Hugging Face Inference API or httpx fallbacks (see ``adapter.py``).
"""

from .adapter import call_model

__all__ = ["call_model"]
