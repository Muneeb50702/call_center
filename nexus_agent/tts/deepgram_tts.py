"""
Nexus Dispatch — Deepgram TTS (Text-to-Speech)

Configurable voice model per tenant. The voice is the "brand" of the dispatch AI —
some clients want an authoritative male dispatcher, others prefer a female voice.

Available Deepgram Aura voices:
- aura-orion-en: Male, authoritative (default — great for dispatch)
- aura-asteria-en: Female, professional
- aura-luna-en: Female, warm
- aura-arcas-en: Male, deep
- aura-zeus-en: Male, commanding
"""

from livekit.plugins import deepgram


# Default voice for dispatch — authoritative male
DEFAULT_VOICE = "aura-orion-en"


def create_tts(voice_model: str = "") -> deepgram.TTS:
    """
    Creates a Deepgram Aura TTS instance.
    
    Args:
        voice_model: Deepgram voice model ID. Uses DEFAULT_VOICE if not specified.
    
    Returns:
        Configured Deepgram TTS instance.
    """
    model = voice_model or DEFAULT_VOICE
    return deepgram.TTS(
        model=model,
    )
