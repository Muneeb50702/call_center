from livekit.plugins import silero

def create_vad() -> silero.VAD:
    """
    Creates a Silero VAD instance.
    Thresholds are tuned aggressively for fast barge-in detection.
    """
    return silero.VAD.load(
        min_speech_duration=0.4,
        min_silence_duration=0.8,
        activation_threshold=0.8
    )
