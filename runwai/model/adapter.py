"""
Model adapter — text LLM for Layer 4.

Uses **LangChain** ``ChatOpenAI`` when ``langchain-openai`` is installed (recommended for
hackathon tracks asking for LangChain / CrewAI-style stacks): same OpenAI-compatible
endpoint, **Qwen** or any OSS instruct model served via vLLM, HF Router, Together, etc.

Priority:
  1a. LangChain ``ChatOpenAI`` → OpenAI-compatible ``POST .../v1/chat/completions``
      (disable with ``USE_LANGCHAIN=0``).
  1b. Direct ``httpx`` to the same endpoint if LangChain is off or unavailable.
  2. Hugging Face Inference API (HF_API_KEY, optional HF_MODEL_ID)
  3. JSON stub (no keys / unreachable server)
"""

from __future__ import annotations

from ..env_bootstrap import load_repo_dotenv

load_repo_dotenv()

import json
import os
from typing import Optional

DEFAULT_MODEL_TEMPERATURE = 0.3

from huggingface_hub import InferenceClient

SYSTEM_MESSAGE = (
    "You are RunwAI, an AI air traffic control assistant. Always respond with valid JSON only."
)

HF_API_KEY = os.environ.get("HF_API_KEY")
HF_MODEL_ID = os.environ.get("HF_MODEL_ID", "Qwen/Qwen2.5-72B-Instruct")
MODEL_NAME = os.environ.get("MODEL_NAME", HF_MODEL_ID)

OPENAI_BASE_URL = (os.environ.get("OPENAI_BASE_URL") or os.environ.get("MODEL_BASE_URL") or "").rstrip(
    "/"
)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("MODEL_API_KEY")

USE_LANGCHAIN = os.environ.get("USE_LANGCHAIN", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)

hf_client = InferenceClient(token=HF_API_KEY) if HF_API_KEY else None


def _openai_compatible_api_root(base_url: str) -> str:
    """Normalize ``OPENAI_BASE_URL`` (host-only or already ending in ``/v1``)."""
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _call_langchain_openai_compatible(
    prompt: str, max_tokens: int, debug_print: bool, temperature: float
) -> Optional[str]:
    """
    LangChain ChatOpenAI → same JSON schema as manual httpx path.
    Returns None if LangChain is disabled, not installed, or misconfigured.
    """
    if not USE_LANGCHAIN or not OPENAI_BASE_URL:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    api_root = _openai_compatible_api_root(OPENAI_BASE_URL)
    key = OPENAI_API_KEY or os.environ.get("HF_TOKEN") or "unused"

    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=key,
        base_url=api_root,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=120.0,
    )
    messages = [
        SystemMessage(content=SYSTEM_MESSAGE),
        HumanMessage(content=prompt),
    ]
    try:
        resp = llm.invoke(messages)
        text = getattr(resp, "content", None) or ""
        if isinstance(text, list):
            text = "".join(
                getattr(block, "text", str(block)) for block in text
            )
        text = str(text).strip()
        if debug_print:
            print("\nMODEL RESPONSE (LangChain ChatOpenAI → Qwen/OSS):")
            print("-" * 60)
            print(text)
            print("-" * 60)
        return text or None
    except Exception as e:
        err = str(e)[:200]
        print(f"[Model] LangChain ChatOpenAI error: {err}")
        return None


def _stub(error_reason: str) -> str:
    esc = json.dumps(error_reason[:200])
    return (
        '{"reasoning": '
        + esc
        + ', "recommended_action": null, "model_confidence": 0.0}'
    )


def _call_openai_compatible(
    prompt: str, max_tokens: int, debug_print: bool, temperature: float
) -> Optional[str]:
    if not OPENAI_BASE_URL:
        return None

    out = _call_langchain_openai_compatible(prompt, max_tokens, debug_print, temperature)
    if out is not None:
        return out

    try:
        import httpx
    except ImportError:
        print("[Model] httpx not installed. pip install httpx (required for OPENAI_BASE_URL).")
        return None

    url = f"{_openai_compatible_api_root(OPENAI_BASE_URL)}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        text = data["choices"][0]["message"]["content"]
        if debug_print:
            print("\nMODEL RESPONSE (OpenAI-compatible):")
            print("-" * 60)
            print(text)
            print("-" * 60)
        return text
    except Exception as e:
        err = str(e)[:200]
        print(f"[Model] OpenAI-compatible error: {err}")
        return _stub(f"OpenAI-compatible error: {err}")


def _call_huggingface(
    prompt: str, max_tokens: int, debug_print: bool, temperature: float
) -> Optional[str]:
    if not hf_client:
        return None
    try:
        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": prompt},
        ]
        response = hf_client.chat_completion(
            model=HF_MODEL_ID,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        generated_text = response.choices[0].message.content
        if debug_print:
            print("\nMODEL RESPONSE (Hugging Face):")
            print("-" * 60)
            print(generated_text)
            print("-" * 60)
        return generated_text
    except Exception as e:
        err = str(e)[:200]
        print(f"[Model] Hugging Face error: {err}")
        return _stub(f"Hugging Face error: {err}")


def call_model(
    prompt: str,
    debug_print: bool = False,
    max_tokens: int = 1024,
    temperature: Optional[float] = None,
) -> str:
    """
    Send prompt to the configured backend and return raw assistant text (JSON string expected).

    If ``temperature`` is omitted, ``MODEL_TEMPERATURE`` env (default 0.3) is used.
    """
    if temperature is None:
        try:
            temperature = float(os.environ.get("MODEL_TEMPERATURE", str(DEFAULT_MODEL_TEMPERATURE)))
        except ValueError:
            temperature = DEFAULT_MODEL_TEMPERATURE

    if debug_print:
        print("=" * 60)
        print("PROMPT TO MODEL")
        print("=" * 60)
        print(prompt[:2000] + "..." if len(prompt) > 2000 else prompt)
        print("=" * 60)

    # 1) OpenAI-compatible (vLLM, OpenAI, etc.)
    out = _call_openai_compatible(prompt, max_tokens, debug_print, temperature)
    if out is not None:
        return out

    # 2) Hugging Face Inference API
    out = _call_huggingface(prompt, max_tokens, debug_print, temperature)
    if out is not None:
        return out

    # 3) Stub with setup hints
    print(
        "[Model] No OPENAI_BASE_URL/MODEL_BASE_URL or HF_API_KEY. Using stub. "
        "Set OPENAI_BASE_URL=http://host:port for vLLM/OpenAI-compatible, or HF_API_KEY for Hugging Face."
    )
    return _stub(
        "No model backend configured (OPENAI_BASE_URL or HF_API_KEY). Stub response."
    )


def call_model_stub(prompt: str, debug_print: bool = True) -> str:
    """Stub version for testing without API calls."""
    if debug_print:
        print("=" * 60)
        print("STUB MODE - No API call")
        print("=" * 60)

    return """{
        "reasoning": "[STUB] This is a placeholder response.",
        "recommended_action": null,
        "model_confidence": 0.0
    }"""
