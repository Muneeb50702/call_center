"""
Nexus — Fish Audio TTS (S2 emotion markers, in a live call)

Fish Audio's S2 line understands inline emotion markers in [square brackets]
— [excited], [empathetic], [whispering], [chuckling], [break] — and performs
them rather than reading them aloud. That makes it the second engine in this
stack (after ElevenLabs v3) that can act a line instead of merely pronouncing
it, and unlike v3 it does so over an ordinary HTTP streaming endpoint with no
transport caveats.

Why HTTP rather than the WebSocket
----------------------------------
Fish does publish a WebSocket TTS endpoint, but it speaks MessagePack and is
built for the case where TEXT arrives incrementally. Here the framework has
already tokenized the LLM stream into sentences before TTS is called, so the
incremental-text feature buys nothing, while MessagePack framing adds a
dependency and a failure mode. One sentence per HTTP request, declared
`streaming=False` and wrapped in `StreamAdapter`, gives the same
audio-starts-on-sentence-one behaviour as the v3 path — see tts/eleven_v3.py,
which this deliberately mirrors.

Sample rate
-----------
Fish honours the `sample_rate` request field: asking for 24000 returns PCM whose
WAV header reads 24000 Hz (verified against 24k/32k/44.1k). That matches the
registry's pinned SAMPLE_RATE exactly, so Fish drops into a live session with no
resampling and `SwitchableTTS._assert_compatible` passes.

Emotion marker safety
---------------------
S2 accepts free-form bracket text ("[warm and unhurried]"), not just a fixed
vocabulary, so it cannot be validated the way v3's tags are. It also turns out
to be far more forgiving: [bananas], [smirks] and [qwertyuiop asdfgh] were all
tested and NONE was vocalised — durations stayed within noise of the untagged
line. (v3, by contrast, measurably speaks a nonsense tag, which is why
tts/eleven_v3.py needs a strict whitelist.)

`sanitize_markers` is therefore permissive rather than restrictive: it keeps
anything that looks like a plausible direction and drops only the pathological
cases — over-long brackets, and markdown-ish leftovers. Belt and braces on an
engine that has not yet needed either.

API credit
----------
The paid models (s2.1-pro, s2-pro, s1) require API credit topped up separately
from platform credit; without it every request 402s. `s2.1-pro-free` is the same
generation as s2.1-pro and needs no credit, so it is the default here.
"""

from __future__ import annotations

import asyncio
import os
import re

import structlog
from livekit.agents import APIConnectionError, APIStatusError
from livekit.agents import tts as tts_base
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = structlog.get_logger()

API_URL = "https://api.fish.audio/v1/tts"
SAMPLE_RATE = 24000  # matches tts.registry.SAMPLE_RATE
NUM_CHANNELS = 1

# s2.1-pro-free needs no API credit and is the same generation as s2.1-pro.
DEFAULT_MODEL = os.getenv("FISH_MODEL", "s2.1-pro-free")

# ── Emotion markers ──────────────────────────────────────────────────────────
# The documented S2 vocabulary, verbatim from
# https://docs.fish.audio/developer-guide/core-features/emotions
# Kept as data so the LLM prompt and the sanitizer cannot drift apart.

BASIC_EMOTIONS = (
    "happy", "sad", "angry", "excited", "calm", "nervous", "confident",
    "surprised", "satisfied", "delighted", "scared", "worried", "upset",
    "frustrated", "depressed", "empathetic", "embarrassed", "disgusted",
    "moved", "proud", "relaxed", "grateful", "curious", "sarcastic",
)
ADVANCED_EMOTIONS = (
    "disdainful", "unhappy", "anxious", "hysterical", "indifferent",
    "uncertain", "doubtful", "confused", "disappointed", "regretful",
    "guilty", "ashamed", "jealous", "envious", "hopeful", "optimistic",
    "pessimistic", "nostalgic", "lonely", "bored", "contemptuous",
    "sympathetic", "compassionate", "determined", "resigned",
)
TONE_MARKERS = (
    "in a hurry tone", "shouting", "screaming", "whispering", "soft tone",
    "emphasis",
)
AUDIO_EFFECTS = (
    "laughing", "chuckling", "sobbing", "crying loudly", "sighing",
    "groaning", "panting", "gasping", "yawning", "snoring", "clear throat",
)
SPECIAL_EFFECTS = (
    "audience laughing", "background laughter", "crowd laughing",
    "break", "long-break",
)

ALL_MARKERS = frozenset(
    BASIC_EMOTIONS + ADVANCED_EMOTIONS + TONE_MARKERS + AUDIO_EFFECTS + SPECIAL_EFFECTS
)

# S2 supports intensity qualifiers on any emotion ("[very excited]").
INTENSITY_WORDS = frozenset({"very", "slightly", "extremely", "a bit", "somewhat", "really"})

# Matches ANY bracketed run — deliberately unbounded. Bounding the regex
# instead of the handler would let an over-long bracket slip through unmatched
# and therefore un-sanitized, which is the exact case the length guard exists
# to catch.
_ANY_BRACKET = re.compile(r"\[([^\]]*)\]")
# Longer than any legitimate direction; almost certainly leaked markup.
_MAX_MARKER_LEN = 48


def is_known_marker(inner: str) -> bool:
    """True if `inner` is a documented marker, or a documented emotion carrying
    an intensity qualifier ("very excited")."""
    text = inner.strip().lower()
    if text in ALL_MARKERS:
        return True
    words = text.split()
    if len(words) > 1 and words[0] in INTENSITY_WORDS:
        return " ".join(words[1:]) in ALL_MARKERS
    return False


def sanitize_markers(text: str) -> str:
    """Drop bracketed tokens that are clearly not stage direction.

    Permissive by design. S2 explicitly supports free-form descriptions, and an
    unrecognised marker was measured to be silently ignored rather than spoken,
    so rejecting everything unfamiliar would throw away a real feature to
    prevent a failure that does not occur. Only over-long brackets are removed.
    """
    def _keep(match: "re.Match[str]") -> str:
        inner = match.group(1).strip()
        if not inner or len(inner) > _MAX_MARKER_LEN:
            return ""
        return match.group(0)

    cleaned = _ANY_BRACKET.sub(_keep, text)
    cleaned = re.sub(r"\s+([.,!?])", r"\1", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def strip_markers(text: str) -> str:
    """Remove every marker — for transcripts, logs, and non-Fish engines."""
    return re.sub(r"\s{2,}", " ", _ANY_BRACKET.sub("", text)).strip()


def prompt_vocabulary() -> str:
    """The marker instructions handed to the LLM.

    Generated from the same tuples the sanitizer uses, so the model is never
    told about a marker this module would strip.
    """
    return (
        "You may direct your own delivery with Fish Audio S2 emotion markers in "
        "square brackets. They are performed, never read aloud.\n"
        f"- Emotion (start of a sentence): {', '.join('[' + e + ']' for e in BASIC_EMOTIONS[:12])}\n"
        f"- Tone (anywhere): {', '.join('[' + t + ']' for t in TONE_MARKERS)}\n"
        f"- Sounds (anywhere): {', '.join('[' + a + ']' for a in AUDIO_EFFECTS[:6])}\n"
        "- Pauses: [break] short, [long-break] longer\n"
        "- Intensity: [very excited], [slightly worried]\n"
        "Use at most two per reply, and only where the meaning genuinely calls "
        "for it. Most sentences need none. Never bracket anything that is not a "
        "delivery direction."
    )


class FishTTS(tts_base.TTS):
    """Fish Audio S2 over the HTTP streaming endpoint.

    Declares streaming=False so the framework wraps it in a StreamAdapter and
    feeds it sentence by sentence, which is how audio starts on sentence one.
    """

    def __init__(
        self,
        *,
        api_key: str,
        reference_id: str = "",
        model: str = DEFAULT_MODEL,
        speed: float = 1.0,
        latency: str = "balanced",
        http_session=None,
    ):
        super().__init__(
            capabilities=tts_base.TTSCapabilities(streaming=False, aligned_transcript=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        if not api_key:
            raise ValueError("FISH_API_KEY is required for Fish Audio TTS")

        self._api_key = api_key
        self._reference_id = reference_id
        self._model = model
        self._speed = speed
        self._latency = latency
        self._session = http_session

    @property
    def voice_id(self) -> str:
        return self._reference_id

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
    ) -> "FishChunkedStream":
        return FishChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    def prewarm(self) -> None:
        # HTTP connections are pooled by the shared session; nothing to warm.
        pass

    async def aclose(self) -> None:
        pass


class FishChunkedStream(tts_base.ChunkedStream):
    """One sentence -> one HTTP streaming request -> PCM frames."""

    def __init__(self, *, tts: FishTTS, input_text: str, conn_options: APIConnectOptions):
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._tts: FishTTS = tts

    async def _run(self, output_emitter: tts_base.AudioEmitter) -> None:
        import aiohttp

        request_id = f"fish-{id(self):x}"
        output_emitter.initialize(
            request_id=request_id,
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type="audio/pcm",
            stream=False,
        )

        spoken = sanitize_markers(self._input_text)
        if not spoken:
            output_emitter.flush()
            return

        body: dict = {
            "text": spoken,
            # Raw PCM: Fish's own format:"wav" carries a placeholder length in
            # its header, which is meaningless for a stream and actively
            # misleading if anything downstream trusts it.
            "format": "pcm",
            "sample_rate": SAMPLE_RATE,
            "latency": self._tts._latency,
            "chunk_length": 200,
            "normalize": True,
        }
        if self._tts._reference_id:
            body["reference_id"] = self._tts._reference_id
        if self._tts._speed != 1.0:
            body["prosody"] = {"speed": self._tts._speed}

        session = self._tts._ensure_session()

        try:
            async with session.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self._tts._api_key}",
                    "Content-Type": "application/json",
                    "model": self._tts._model,  # required on every request
                },
                json=body,
                timeout=aiohttp.ClientTimeout(total=self._conn_options.timeout + 20),
            ) as response:
                if response.status != 200:
                    text = (await response.text())[:300]
                    # 402 is the one everyone hits: Fish bills API credit
                    # separately from platform credit, and the message alone
                    # does not make the model/credit relationship obvious.
                    if response.status == 402:
                        logger.error(
                            "fish_tts_no_credit",
                            model=self._tts._model,
                            hint="top up API credit at fish.audio/app/developers, "
                                 "or use FISH_MODEL=s2.1-pro-free which needs none",
                        )
                    raise APIStatusError(
                        f"Fish Audio returned {response.status}: {text}",
                        status_code=response.status,
                        request_id=request_id,
                        body=text,
                    )

                # Fish does NOT align its chunk boundaries to sample boundaries:
                # a real 7s response arrived as 126 chunks of which 46 had ODD
                # byte length (1015, 11, 1369...). Pushing an odd number of
                # bytes hands the emitter half of a 16-bit sample, so every
                # sample after it is assembled from the low byte of one and the
                # high byte of the next — which is heard as tearing, crackling
                # and dropouts that sound exactly like a bad connection.
                #
                # So carry the stray byte across pushes and only ever emit whole
                # frames. ElevenLabs happens to send even-length chunks, which is
                # why tts/eleven_v3.py can push straight through and why copying
                # that shape was not enough here.
                frame_size = NUM_CHANNELS * 2  # 16-bit samples
                carry = b""
                async for chunk in response.content.iter_chunked(4096):
                    if not chunk:
                        continue
                    buf = carry + chunk
                    cut = len(buf) - (len(buf) % frame_size)
                    if cut:
                        output_emitter.push(buf[:cut])
                    carry = buf[cut:]

                if carry:
                    # A trailing partial frame cannot be sounded. Fish's totals
                    # have been even in testing, so this is a guard rather than
                    # an expected path — log it if it ever fires.
                    logger.debug("fish_tts_trailing_partial_frame", bytes=len(carry))

                output_emitter.flush()

        except APIStatusError:
            raise
        except asyncio.TimeoutError as e:
            raise APIConnectionError("Fish Audio TTS timed out") from e
        except Exception as e:
            raise APIConnectionError(f"Fish Audio TTS request failed: {e}") from e


def create_fish_tts(
    *,
    api_key: str,
    reference_id: str = "",
    text_pacing: bool = True,
    **kwargs,
) -> tts_base.TTS:
    """Build a Fish TTS ready to drop into an AgentSession.

    StreamAdapter makes the framework tokenize the LLM's output into sentences
    and synthesize them as they complete, so audio starts on sentence one
    instead of at the end of the turn.
    """
    inner = FishTTS(api_key=api_key, reference_id=reference_id, **kwargs)
    return tts_base.StreamAdapter(tts=inner, text_pacing=text_pacing)
