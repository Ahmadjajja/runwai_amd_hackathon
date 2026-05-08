"""
Model Adapter - Interface to the VLM.

Uses HuggingFace Inference Client for serverless inference.
"""

import os
from huggingface_hub import InferenceClient

from ..preprocessing import ModelResponse

# Get API key from environment variable (required)
HF_API_KEY = os.environ.get("HF_API_KEY")

# Initialize client (will be None if no key)
client = InferenceClient(token=HF_API_KEY) if HF_API_KEY else None


def call_model(prompt: str, debug_print: bool = False, max_tokens: int = 1024) -> str:
    """
    Send prompt to model via HuggingFace Inference API.
    
    Args:
        prompt: The assembled prompt string
        debug_print: If True, print the prompt to stdout
        max_tokens: Maximum tokens in response
    
    Returns:
        Raw response text from the model
    """
    if debug_print:
        print("=" * 60)
        print("PROMPT TO MODEL")
        print("=" * 60)
        print(prompt[:2000] + "..." if len(prompt) > 2000 else prompt)
        print("=" * 60)
    
    if not client:
        print("[Model] No HF_API_KEY set. Using stub response.")
        return '{"reasoning": "No API key configured", "recommended_action": null, "model_confidence": 0.0}'
    
    try:
        # Use chat completion which is more widely supported
        messages = [
            {
                "role": "system",
                "content": "You are RunwAI, an AI air traffic control assistant. Always respond with valid JSON only."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ]
        
        response = client.chat_completion(
            model="Qwen/Qwen2.5-72B-Instruct",
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        
        generated_text = response.choices[0].message.content
        
        if debug_print:
            print("\nMODEL RESPONSE:")
            print("-" * 60)
            print(generated_text)
            print("-" * 60)
        
        return generated_text
        
    except Exception as e:
        error_msg = str(e)[:150]
        print(f"[Model] Error: {error_msg}")
        return f'{{"reasoning": "Error: {error_msg}", "recommended_action": null, "model_confidence": 0.0}}'


def call_model_stub(prompt: str, debug_print: bool = True) -> str:
    """Stub version for testing without API calls."""
    if debug_print:
        print("=" * 60)
        print("STUB MODE - No API call")
        print("=" * 60)
    
    return '''{
        "reasoning": "[STUB] This is a placeholder response.",
        "recommended_action": null,
        "model_confidence": 0.0
    }'''
