from livekit.plugins import openai
from config.settings import settings

def create_groq_llm(model_name: str = None) -> openai.LLM:
    """
    Creates a LiveKit-compatible LLM instance pointing to Groq's fast inference endpoint.
    Using Llama-3 8B by default for sub-100ms TTFT.
    """
    return openai.LLM(
        base_url="https://api.groq.com/openai/v1",
        api_key=settings.groq_api_key,
        model=model_name or settings.tier1_model,
        temperature=settings.groq_temperature
    )
