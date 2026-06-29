from livekit.plugins import deepgram

def create_tts() -> deepgram.TTS:
    """
    Creates a Deepgram Aura TTS instance.
    Using 'aura-orion-en' (male) for an authoritative dispatch tone as per requirements.
    """
    return deepgram.TTS(
        model="aura-orion-en",
    )
