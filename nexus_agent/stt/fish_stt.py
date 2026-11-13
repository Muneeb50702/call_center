"""
Nexus — Fish Audio STT (/v1/asr)

The listening half of an all-Fish voice path. Off by default; set `FISH_STT=1`
to use it in place of Deepgram.

Two things to understand before switching it on
-----------------------------------------------

1. **It needs paid API credit.** Fish bills API credit separately from platform
   credit. On a key with none, `/v1/asr` returns 402 for every request — unlike
   TTS, there is no free tier for ASR (`s2.1-pro-free` covers synthesis only).
   `probe()` below reports this cheaply so startup can fall back with a clear
   log line instead of failing every turn of a live call.

2. **It is batch, not streaming.** Fish exposes one-shot file transcription;
   there is no realtime ASR socket. Deepgram's plugin streams with
   `interim_results=True`, `no_delay=True` and `endpointing_ms=25`, and this
   agent leans on that: the semantic turn detector and preemptive generation
   both consume transcript text BEFORE the turn is final. Batch ASR cannot
   produce interims, so those optimisations go quiet and the agent waits for
   VAD to close a segment before it has any text at all.

   Concretely: expect turn latency to rise by roughly the length of the
   trailing silence VAD needs to declare end-of-speech, and expect the agent to
   be worse at knowing when a caller has merely paused to think. Deepgram
   remains the better choice for a live phone call. Fish STT is here so the
   pipeline CAN be single-vendor when that matters more than latency.

`StreamAdapter` bridges the gap: it runs VAD locally, cuts speech into
utterances, and calls `_recognize_impl` once per utterance.
"""

from __future__ import annotations

import asyncio
import io
import os
import wave

import structlog
from livekit import rtc
from livekit.agents import APIConnectionError, APIStatusError
from livekit.agents import stt as stt_base
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = structlog.get_logger()

ASR_URL = "https://api.fish.audio/v1/asr"


def enabled() -> bool:
    """Whether the operator asked for Fish STT at all."""
    return os.getenv("FISH_STT", "").strip().lower() in {"1", "true", "yes", "on"}


def probe(api_key: str, *, timeout: float = 8.0) -> tuple[bool, str]:
    """Cheaply check whether Fish ASR will actually serve this key.

    Returns (usable, reason). Sends a fraction of a second of silence — enough
    for the API to authorise and bill-check the request without costing
    meaningful credit. Called once at startup so a 402 surfaces as one clear log
    line rather than as a failure on every caller utterance.
    """
    import requests

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)  # 0.1s of silence

    try:
        r = requests.post(
            ASR_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files={"audio": ("probe.wav", buf.getvalue(), "audio/wav")},
            data={"language": "en", "ignore_timestamps": "true"},
            timeout=timeout,
        )
    except Exception as e:
        return False, f"unreachable: {e}"

    if r.status_code == 200:
        return True, "ok"
    if r.status_code == 402:
        return False, ("no API credit — Fish bills API credit separately from "
                       "platform credit (fish.audio/app/developers)")
    if r.status_code in (401, 403):
        return False, "FISH_API_KEY rejected"
    return False, f"HTTP {r.status_code}: {r.text[:120]}"


def _to_wav(frame: rtc.AudioFrame) -> bytes:
    """Frame a LiveKit audio buffer as a WAV for upload."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(frame.num_channels)
        w.setsampwidth(2)  # LiveKit delivers 16-bit PCM
        w.setframerate(frame.sample_rate)
        w.writeframes(frame.data.tobytes() if hasattr(frame.data, "tobytes") else bytes(frame.data))
    return buf.getvalue()


class FishSTT(stt_base.STT):
    """Fish Audio batch ASR behind the LiveKit STT interface.

    Declares streaming=False and interim_results=False — both are honest: this
    endpoint gives one final transcript per utterance and nothing before it.
    Use `create_stt` to get one wrapped in a VAD StreamAdapter.
    """

    def __init__(self, *, api_key: str, language: str = "en", http_session=None):
        super().__init__(
            capabilities=stt_base.STTCapabilities(streaming=False, interim_results=False)
        )
        if not api_key:
            raise ValueError("FISH_API_KEY is required for Fish Audio STT")
        self._api_key = api_key
        self._language = language
        self._session = http_session

    def _ensure_session(self):
        if self._session is None:
            from livekit.agents import utils
            self._session = utils.http_context.http_session()
        return self._session

    async def _recognize_impl(
        self,
        buffer: stt_base.utils.AudioBuffer,
        *,
        language: str | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt_base.SpeechEvent:
        import aiohttp
        from livekit.agents import utils

        frame = utils.audio.combine_frames(buffer)
        wav = _to_wav(frame)

        form = aiohttp.FormData()
        form.add_field("audio", wav, filename="turn.wav", content_type="audio/wav")
        form.add_field("language", language or self._language)
        form.add_field("ignore_timestamps", "true")

        try:
            async with self._ensure_session().post(
                ASR_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                data=form,
                timeout=aiohttp.ClientTimeout(total=conn_options.timeout + 20),
            ) as response:
                if response.status != 200:
                    body = (await response.text())[:300]
                    if response.status == 402:
                        logger.error(
                            "fish_stt_no_credit",
                            hint="Fish ASR has no free tier; top up API credit at "
                                 "fish.audio/app/developers or unset FISH_STT",
                        )
                    raise APIStatusError(
                        f"Fish Audio ASR returned {response.status}: {body}",
                        status_code=response.status,
                        body=body,
                    )
                payload = await response.json()

        except APIStatusError:
            raise
        except asyncio.TimeoutError as e:
            raise APIConnectionError("Fish Audio ASR timed out") from e
        except Exception as e:
            raise APIConnectionError(f"Fish Audio ASR request failed: {e}") from e

        text = (payload.get("text") or "").strip()
        return stt_base.SpeechEvent(
            type=stt_base.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt_base.SpeechData(
                    language=language or self._language,
                    text=text,
                    # Fish returns no per-utterance confidence. Reporting None
                    # rather than a made-up 1.0 matters: NexusAgent.stt_node
                    # raises the exception score on low confidence, and a
                    # fabricated high value would silently disable that signal.
                    confidence=None,
                )
            ],
        )


def create_stt(vad=None, *, language: str = "en") -> stt_base.STT:
    """Fish ASR wrapped in a VAD StreamAdapter, so it satisfies the streaming
    STT interface the AgentSession expects.

    `vad` is required in practice — without local VAD there is nothing to decide
    where one utterance ends and the next begins.
    """
    inner = FishSTT(api_key=os.getenv("FISH_API_KEY", ""), language=language)
    if vad is None:
        logger.warning(
            "fish_stt_without_vad",
            hint="pass the session VAD; batch ASR needs it to segment utterances",
        )
        return inner
    return stt_base.StreamAdapter(stt=inner, vad=vad)
