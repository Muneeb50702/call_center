"""
Nexus — Google Gemini LLM Client

Creates a LiveKit-compatible LLM instance pointing to Google's Gemini models.

MINIMUM_DEADLINE_SECONDS is not a tuning knob — it is a hard server-side
constraint. Gemini rejects any request whose deadline is under 10s with:

    400 INVALID_ARGUMENT
    "Manually set deadline 5s is too short. Minimum allowed deadline is 10s."

and `retryable=False`, so nothing recovers it. This bit us for real: wrapping
Gemini in `llm.FallbackAdapter`, whose `attempt_timeout` defaults to 5.0s, made
that timeout the request deadline and caused EVERY Gemini call to 400. The agent
transcribed fine and then never spoke. Any code path that sets a deadline on this
client must respect this floor.
"""

from livekit.plugins import google

from config.settings import settings

# Gemini's server-side floor. Requests below this are rejected, not slowed.
MINIMUM_DEADLINE_SECONDS = 10.0


def create_google_llm(
    model_name: str = "",
    temperature: float | None = None,
) -> google.LLM:
    """
    Creates a LiveKit-compatible LLM instance using Google's Gemini API.

    Args:
        model_name: Gemini model ID. Defaults to "gemini-2.5-flash".
        temperature: LLM temperature. Defaults to settings.groq_temperature.

    Returns:
        Configured LLM instance.
    """
    # settings.gemini_model, NOT settings.tier1_model: the tier aliases are
    # provider-agnostic names holding provider-specific values, and TIER1_MODEL
    # is set to a Groq model (llama-3.1-8b-instant) in real .env files here.
    # Resolving Gemini's model through it sends Google a Llama name.
    return google.LLM(
        api_key=settings.gemini_api_key,
        model=model_name or settings.gemini_model,
        temperature=temperature if temperature is not None else settings.groq_temperature,
    )
