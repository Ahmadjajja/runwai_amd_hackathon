"""
Model Adapter — Interface to the VLM.

Priority:
  1. AMD MI300X via vLLM (OpenAI-compatible) — set VLLM_API_URL + VLLM_MODEL
  2. HuggingFace Inference API (fallback)     — set HF_API_KEY

Both paths support multimodal (text + image frame).
"""

import os
import base64
from pathlib import Path
from typing import Optional

# AMD vLLM endpoint (primary — set this when running on MI300X)
VLLM_API_URL = os.environ.get("VLLM_API_URL")            # e.g. http://localhost:8000/v1
VLLM_MODEL   = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-VL-72B-Instruct")

# HuggingFace fallback
HF_API_KEY = (os.environ.get("HF_API_KEY") or "").strip() or None
HF_MODEL   = "Qwen/Qwen2.5-72B-Instruct"                # reliable HF Inference API model

STUB_RESPONSE = (
    '{"reasoning": "No model configured — set VLLM_API_URL or HF_API_KEY.", '
    '"recommended_action": null, "model_confidence": 0.0}'
)


def load_frame_b64(frame_path: Optional[str]) -> Optional[str]:
    """Load a JPEG frame from disk and return base64-encoded string."""
    if not frame_path:
        return None
    p = Path(frame_path)
    if not p.exists():
        print(f"[Model] Frame not found: {frame_path}")
        return None
    return base64.b64encode(p.read_bytes()).decode()


def _build_messages(prompt: str, frame_b64: Optional[str]) -> list:
    """Build OpenAI-style messages, with image content when frame is available."""
    if frame_b64:
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"}},
            {"type": "text", "text": prompt},
        ]
    else:
        user_content = prompt

    return [
        {
            "role": "system",
            "content": (
                "You are RunwAI, an AI air traffic control assistant. "
                "Always respond with valid JSON only."
            ),
        },
        {"role": "user", "content": user_content},
    ]


def call_model(
    prompt: str,
    frame_b64: Optional[str] = None,
    debug_print: bool = False,
    max_tokens: int = 1024,
) -> str:
    """
    Send prompt (+ optional runway frame) to the vision-language model.

    Returns raw response text (expected to be JSON).
    """
    if debug_print:
        print("=" * 60)
        print("PROMPT TO MODEL")
        print("=" * 60)
        print(prompt[:2000] + "..." if len(prompt) > 2000 else prompt)
        if frame_b64:
            print(f"[Frame attached: {len(frame_b64)} base64 chars]")
        print("=" * 60)

    if VLLM_API_URL:
        print(f"[Model] AMD vLLM  → {VLLM_MODEL}  ({VLLM_API_URL})")
        return _call_vllm(prompt, frame_b64, debug_print, max_tokens)

    if HF_API_KEY:
        print(f"[Model] HuggingFace → {HF_MODEL}")
        return _call_hf(prompt, frame_b64, debug_print, max_tokens)

    print("[Model] No VLLM_API_URL or HF_API_KEY set — using stub response.")
    return STUB_RESPONSE


def _call_vllm(
    prompt: str,
    frame_b64: Optional[str],
    debug_print: bool,
    max_tokens: int,
) -> str:
    try:
        from openai import OpenAI

        client = OpenAI(base_url=VLLM_API_URL, api_key="EMPTY")
        messages = _build_messages(prompt, frame_b64)
        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        text = response.choices[0].message.content
        if debug_print:
            print("\nMODEL RESPONSE:\n" + "-" * 60)
            print(text)
        return text
    except Exception as e:
        err = str(e)[:150]
        print(f"[Model] vLLM error: {err}")
        return f'{{"reasoning": "vLLM error: {err}", "recommended_action": null, "model_confidence": 0.0}}'


def _call_hf(
    prompt: str,
    frame_b64: Optional[str],
    debug_print: bool,
    max_tokens: int,
) -> str:
    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(token=HF_API_KEY)
        messages = _build_messages(prompt, frame_b64)
        response = client.chat_completion(
            model=HF_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        text = response.choices[0].message.content
        if debug_print:
            print("\nMODEL RESPONSE:\n" + "-" * 60)
            print(text)
        return text
    except Exception as e:
        import traceback
        err = str(e)[:300]
        print(f"[Model] HuggingFace error: {err}")
        traceback.print_exc()
        return f'{{"reasoning": "HF error: {err}", "recommended_action": null, "model_confidence": 0.0}}'


def call_model_stub(prompt: str, debug_print: bool = True) -> str:
    """Stub for testing without making API calls."""
    if debug_print:
        print("STUB MODE — no API call")
    return (
        '{"reasoning": "[STUB] Placeholder response. No API call made.", '
        '"recommended_action": null, "model_confidence": 0.0}'
    )
