"""
Nexus Dispatch — Groq LLM Client

Creates a LiveKit-compatible LLM instance pointing to Groq's fast inference.
Supports per-tenant model and temperature configuration.
"""

from livekit.plugins import openai
from config.settings import settings


def create_groq_llm(
    model_name: str = "",
    temperature: float | None = None,
) -> openai.LLM:
    """
    Creates a LiveKit-compatible LLM instance using Groq's OpenAI-compatible API.
    
    Groq provides sub-100ms TTFT (Time-To-First-Token) for real-time
    conversational latency that feels natural to callers.
    
    Args:
        model_name: Groq model ID. Defaults to settings.tier1_model.
        temperature: LLM temperature. Defaults to settings.groq_temperature.
    
    Returns:
        Configured LLM instance.
    """
    return openai.LLM(
        base_url="https://api.groq.com/openai/v1",
        api_key=settings.groq_api_key,
        model=model_name or settings.tier1_model,
        temperature=temperature if temperature is not None else settings.groq_temperature,
    )
