"""
Nexus — Pre-rendered expressive opener (ElevenLabs v3)

The one place the demo can use ElevenLabs v3's emotional Audio Tags
([sighs], [breathes], [cheerfully], [warmly]) despite v3 being unusable for live
conversation.

Why this works when live v3 does not
------------------------------------
v3 produces the most expressive speech ElevenLabs makes, but its TTS WebSocket
endpoint does not support it and its ~2.5s generation is too slow to stream a
turn. That kills it for the back-and-forth of a call — EXCEPT for the one line
that is identical on every call and known before the human says anything: the
opener.

So the opener is rendered ONCE, up front, over plain REST (no streaming needed),
during the second or two while the browser is connecting and the person is still
reaching for "hello". That hides the 2.5s completely. The result is played as the
agent's first utterance via `AgentSession.say(text, audio=...)`. Every turn after
it streams on Flash v2.5 as normal.

Net effect: the first thing the prospect hears is full v3 emotion — a real breath,
genuine warmth, energy — and they never learn the rest of the call is a different,
faster model. That first impression is the entire point of the demo.

Grounding note: the opener text is fixed campaign copy (who we are, that it's a
cold call, the one reason, the time ask). It states no company fact that needs
retrieval, so pre-rendering it does not bypass the knowledge base or the verifier
— those still govern every live turn.
"""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger()

# v3 renders at 24kHz PCM, matching the pipeline's SAMPLE_RATE so the frames drop
# straight onto the audio path with no resampling.
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
# 20ms frames. Small enough to interleave smoothly, large enough to avoid churn.
SAMPLES_PER_FRAME = SAMPLE_RATE // 50  # 480

ELEVEN_V3_MODEL = "eleven_v3"
ELEVEN_FLASH_MODEL = "eleven_flash_v2_5"

# Matches [tag] audio-tag syntax, so tags can be stripped for the models that do
# not understand them (everything except v3 speaks them literally).
import re as _re

_TAG_RE = _re.compile(r"\[[^\]]*\]")


def strip_tags(text: str) -> str:
    """Remove v3 audio tags and collapse the whitespace they leave behind."""
    return _re.sub(r"\s{2,}", " ", _TAG_RE.sub("", text)).strip()


async def render_pcm(text: str, voice_id: str, api_key: str, *,
                     model: str = ELEVEN_V3_MODEL, timeout: float = 40.0) -> bytes | None:
    """Render `text` to raw 24kHz mono PCM over REST for the given model.

    Returns None on failure so the caller can try a different model or degrade.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                params={"output_format": "pcm_24000", "model_id": model},
                json={"text": text},
            )
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.warning("opener_render_failed", model=model, error=str(e)[:160])
        return None


async def render_opener(tagged_text: str, voice_id: str, api_key: str) -> tuple[bytes, str] | None:
    """Render the opener as fixed audio, preferring v3's emotion.

    Tries v3 with the audio tags first. If v3 is unavailable, retries the SAME
    line on Flash with the tags stripped — a clean, fast, consistent read rather
    than an LLM-improvised greeting. Either way the opener is deterministic audio,
    which is the whole point: it plays the same every call and never routes through
    the grounding verifier (that only sees model-generated turns), so it can never
    be replaced by the "let me pull that up" hedge.

    Returns (pcm, model_used) or None if even Flash fails.
    """
    if not api_key or not voice_id:
        return None

    pcm = await render_pcm(tagged_text, voice_id, api_key, model=ELEVEN_V3_MODEL)
    if pcm:
        return pcm, ELEVEN_V3_MODEL

    logger.warning("opener_v3_unavailable_falling_back_to_flash")
    pcm = await render_pcm(strip_tags(tagged_text), voice_id, api_key, model=ELEVEN_FLASH_MODEL)
    if pcm:
        return pcm, ELEVEN_FLASH_MODEL

    return None


def pcm_to_frames(pcm: bytes):
    """Slice raw PCM16 into an async iterator of rtc.AudioFrames for say()."""
    from livekit import rtc

    bytes_per_frame = SAMPLES_PER_FRAME * 2  # 16-bit mono

    async def _gen():
        for offset in range(0, len(pcm), bytes_per_frame):
            chunk = pcm[offset:offset + bytes_per_frame]
            if len(chunk) < bytes_per_frame:
                # Zero-pad the final short frame so playback does not click.
                chunk = chunk + b"\x00" * (bytes_per_frame - len(chunk))
            yield rtc.AudioFrame(
                data=chunk,
                sample_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
                samples_per_channel=SAMPLES_PER_FRAME,
            )
            # Yield control so the frames stream out rather than landing in one
            # blocking burst.
            await asyncio.sleep(0)

    return _gen()


async def prerender_opener(text: str, voice_id: str, api_key: str) -> tuple[bytes, str] | None:
    """Render the fixed opener as audio, v3 first then Flash, logging the outcome.

    Call this during connection setup, before the greeting, and hold the returned
    PCM until the session is ready to speak. Returns (pcm, model) or None.
    """
    result = await render_opener(text, voice_id, api_key)
    if result:
        pcm, model = result
        logger.info(
            "opener_rendered",
            model=model,
            bytes=len(pcm),
            seconds=round(len(pcm) / (SAMPLE_RATE * 2), 2),
        )
    return result
