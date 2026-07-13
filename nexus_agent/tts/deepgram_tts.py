"""
Nexus Dispatch — Deepgram TTS (Text-to-Speech)

Configurable voice model per tenant. The voice is the "brand" of the dispatch AI —
some clients want an authoritative male dispatcher, others prefer a female voice.

Upgraded to Deepgram Aura-2 (model format: ``aura-2-<voice>-en``), which is
lower-latency and more natural than Aura-1. 40+ English voices are available;
see https://developers.deepgram.com/docs/tts-models.
- aura-2-apollo-en: Male, confident & professional (default — great for dispatch)
- aura-2-atlas-en:  Male, enthusiastic, confident, professional
- aura-2-orion-en:  Male, approachable, warm
- aura-2-hera-en:   Female, confident, professional
- aura-2-athena-en: Female, calm, professional
- aura-2-luna-en:   Female, warm, conversational
"""

from livekit.plugins import deepgram


# Default voice for dispatch — confident, professional male (Aura-2)
DEFAULT_VOICE = "aura-2-apollo-en"


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
