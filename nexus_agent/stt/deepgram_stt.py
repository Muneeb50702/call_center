from livekit.plugins import deepgram

def create_stt() -> deepgram.STT:
    """
    Creates a Deepgram STT instance optimized for voice AI.
    Nova-3 is highly accurate and low latency.
    """
    return deepgram.STT(
        model="nova-3",
        language="en-US",
        smart_format=True,
        filler_words=False,
    )
