"""
Nexus Dispatch — Google Gemini LLM Client

Creates a LiveKit-compatible LLM instance pointing to Google's Gemini models.
Provides a generous free tier for testing.
"""

from livekit.plugins import google
from config.settings import settings


def create_google_llm(
    model_name: str = "",
    temperature: float | None = None,
) -> google.LLM:
    """
    Creates a LiveKit-compatible LLM instance using Google's Gemini API.
    
    Gemini 1.5 Flash provides fast inference and a large free tier suitable
    for testing Voice AI agents without rate limits.
    
    Args:
        model_name: Gemini model ID. Defaults to "gemini-1.5-flash".
        temperature: LLM temperature. Defaults to settings.groq_temperature.
    
    Returns:
        Configured LLM instance.
    """
    return google.LLM(
        api_key=settings.gemini_api_key,
        model=model_name or "gemini-2.5-flash",
        temperature=temperature if temperature is not None else settings.groq_temperature,
    )
