"""
Nexus — ElevenLabs v3 TTS (emotional audio tags, in a live call)

A TTS that drives `eleven_v3` — the only ElevenLabs model that understands inline
emotional Audio Tags ([sighs], [laughs], [warmly], [excited]) — through a live
conversation.

Why this file has to exist
--------------------------
The official livekit-plugins-elevenlabs streams over the **WebSocket** endpoint,
and ElevenLabs does not serve v3 there — it returns a hard 403:

    wss://api.elevenlabs.io/v1/text-to-speech/... -> 403 Invalid response status

That single fact is what makes v3 look impossible for realtime, and it is what
their docs mean by "not for conversational use". But it is a limitation of ONE
transport. Measured against the **HTTP streaming** endpoint from this deployment:

    eleven_flash_v2_5        1083ms TTFB
    eleven_turbo_v2_5        1095ms
    eleven_multilingual_v2   1085ms
    eleven_v3                1209ms   <- with [sighs] tags, and it works

v3 costs roughly 125ms more than Flash over HTTP. So the real trade is not
"emotion or realtime" — it is which transport you use, and about a tenth of a
second.

(Note those HTTP numbers are all ~1s because this deployment is far from the
ElevenLabs edge; the plugin's WebSocket path measures ~271ms for Flash on the
same machine. The comparison between models on the SAME transport is the honest
one, and there v3 is barely behind.)

Design
------
`synthesize()` returns a ChunkedStream that POSTs one sentence to the HTTP
streaming endpoint and forwards PCM as it arrives. Declaring
`streaming=False` and wrapping in `tts.StreamAdapter` lets the framework split
the LLM's token stream into sentences and pipeline them, so audio starts on the
first sentence rather than the last — the same shape as any streaming TTS, just
over HTTP.

Emotion only happens if the LLM actually writes the tags, so the prompt must ask
for them (see llm/sales_prompts.py). Any tag the model invents that v3 does not
recognise is spoken as nothing, not read aloud, so a bad tag is harmless.

Cost: v3 bills more per character than Flash. On a metered plan, keep an eye on
credits when this is the default for a whole call.
"""

from __future__ import annotations

import asyncio

import structlog
from livekit.agents import APIConnectionError, APIStatusError
from livekit.agents import tts as tts_base
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = structlog.get_logger()

V3_MODEL = "eleven_v3"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
API_BASE = "https://api.elevenlabs.io/v1/text-to-speech"

# ── Emotion tag safety ───────────────────────────────────────────────────────
# Only these tags are forwarded to v3. Everything else in [brackets] is stripped.
#
# This is a guard, not decoration. The LLM invents tags — it produced "[smirks]"
# unprompted in testing — and a tag v3 does not recognise is not reliably
# silent: a nonsense tag ("[bananas]") measured ~0.9s longer than the same line
# untagged, consistent with the word being VOCALISED. An agent that says the word
# "bananas" mid-pitch ends a client demo. A whitelist makes that impossible no
# matter what the model writes, and costs nothing when it behaves.
ALLOWED_TAGS = frozenset({
    "sighs", "sigh", "laughs", "laugh", "chuckles", "chuckle",
    "warmly", "thoughtfully", "curious", "surprised", "excited",
    "cheerfully", "sincerely", "whispers", "exhales", "breathes",
})

import re as _re

_ANY_TAG_RE = _re.compile(r"\[([^\]]{1,32})\]")


def sanitize_tags(text: str) -> str:
    """Keep whitelisted emotion tags, strip every other bracketed token."""

    def _keep(match: "_re.Match[str]") -> str:
        inner = match.group(1).strip().lower()
        return match.group(0) if inner in ALLOWED_TAGS else ""

    cleaned = _ANY_TAG_RE.sub(_keep, text)
    return _re.sub(r"\s{2,}", " ", cleaned).strip()


class ElevenV3TTS(tts_base.TTS):
    """ElevenLabs v3 over the HTTP streaming endpoint.

    Declares streaming=False so the framework wraps it in a StreamAdapter and
    feeds it sentence by sentence — v3 has no WebSocket, so per-sentence HTTP is
    the streaming story.
    """

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model: str = V3_MODEL,
        stability: float = 0.4,
        similarity_boost: float = 0.75,
        style: float = 0.35,
        speed: float = 1.0,
        use_speaker_boost: bool = True,
        http_session=None,
    ):
        super().__init__(
            capabilities=tts_base.TTSCapabilities(streaming=False, aligned_transcript=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        if not api_key:
            raise ValueError("ElevenLabs API key is required for v3 TTS")

        self._api_key = api_key
        self._voice_id = voice_id
        self._model = model
        self._session = http_session
        # v3 is already highly expressive from the tags themselves, so the
        # settings stay closer to neutral than the Flash preset — stacking a low
        # stability on top of emotional tags makes it wander mid-sentence.
        self._voice_settings = {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "speed": speed,
            "use_speaker_boost": use_speaker_boost,
        }

    @property
    def voice_id(self) -> str:
        return self._voice_id

    @property
    def model(self) -> str:
        return self._model

    def _ensure_session(self):
        if self._session is None:
            from livekit.agents import utils
            self._session = utils.http_context.http_session()
        return self._session

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> "ElevenV3ChunkedStream":
        return ElevenV3ChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    def prewarm(self) -> None:
        # Nothing to warm: HTTP connections are pooled by the shared session.
        pass

    async def aclose(self) -> None:
        pass


class ElevenV3ChunkedStream(tts_base.ChunkedStream):
    """One sentence -> one HTTP streaming request -> PCM frames."""

    def __init__(self, *, tts: ElevenV3TTS, input_text: str, conn_options: APIConnectOptions):
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._tts: ElevenV3TTS = tts

    async def _run(self, output_emitter: tts_base.AudioEmitter) -> None:
        import aiohttp

        request_id = f"v3-{id(self):x}"
        # stream=False: a ChunkedStream synthesizes ONE sentence, which is one
        # audio segment. (stream=True is for emitters that interleave several
        # segments and then requires an explicit start_segment() first.) PCM is
        # still pushed incrementally as it arrives off the wire — this flag
        # describes the segment structure, not whether we buffer.
        output_emitter.initialize(
            request_id=request_id,
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type="audio/pcm",
            stream=False,
        )

        session = self._tts._ensure_session()
        url = f"{API_BASE}/{self._tts.voice_id}/stream"

        # Drop any tag the model invented that v3 might vocalise. If sanitizing
        # leaves nothing (the whole line was one bad tag), skip the request
        # rather than sending empty text.
        spoken_text = sanitize_tags(self._input_text)
        if not spoken_text:
            output_emitter.flush()
            return

        try:
            async with session.post(
                url,
                headers={"xi-api-key": self._tts._api_key, "Content-Type": "application/json"},
                params={"output_format": "pcm_24000", "model_id": self._tts.model},
                json={
                    "text": spoken_text,
                    "voice_settings": self._tts._voice_settings,
                },
                timeout=aiohttp.ClientTimeout(total=self._conn_options.timeout + 20),
            ) as response:
                if response.status != 200:
                    body = (await response.text())[:300]
                    raise APIStatusError(
                        f"ElevenLabs v3 returned {response.status}: {body}",
                        status_code=response.status,
                        request_id=request_id,
                        body=body,
                    )

                async for chunk in response.content.iter_chunked(4096):
                    if chunk:
                        output_emitter.push(chunk)

                output_emitter.flush()

        except APIStatusError:
            raise
        except asyncio.TimeoutError as e:
            raise APIConnectionError("ElevenLabs v3 timed out") from e
        except Exception as e:
            raise APIConnectionError(f"ElevenLabs v3 request failed: {e}") from e


def create_v3_tts(
    *,
    api_key: str,
    voice_id: str,
    text_pacing: bool = True,
    **kwargs,
) -> tts_base.TTS:
    """Build a v3 TTS ready to drop into an AgentSession.

    Wrapped in StreamAdapter so the framework tokenizes the LLM's output into
    sentences and synthesizes them as they complete — audio starts on sentence
    one instead of waiting for the full turn.
    """
    inner = ElevenV3TTS(api_key=api_key, voice_id=voice_id, **kwargs)
    return tts_base.StreamAdapter(tts=inner, text_pacing=text_pacing)
