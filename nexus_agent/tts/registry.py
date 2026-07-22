"""
Nexus — Multi-provider voice registry

One catalog of speakable voices across providers, addressed by a namespaced id
(`deepgram:aura-2-thalia-en`, `cartesia:<uuid>`), plus a TTS wrapper that lets a
live call change voice between utterances without dropping the session.

Why a wrapper rather than the framework:
`Agent.tts` and `AgentSession.tts` are read-only properties in livekit-agents
1.6, and `AgentSession.update_options()` does not accept a TTS. The only
supported way to change voice is to rebuild the agent, which costs a handoff. So
`SwitchableTTS` implements the TTS interface and delegates to a swappable inner
instance. `stream()` captures the current inner at call time, so a swap mid-
utterance lets the in-flight sentence finish in the old voice and the next one
start in the new — which is exactly the desired behaviour.

Both Deepgram and Cartesia default to 24kHz PCM, so a swap never changes the
sample rate underneath the audio path. `_assert_compatible` enforces that, since
a silent rate mismatch would surface as chipmunk audio rather than an exception.

Provider availability is keyed off env vars: a provider with no API key is simply
absent from the catalog. Deepgram alone is a complete, working configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import structlog
from livekit.agents import tts as tts_base

logger = structlog.get_logger()

# Every provider is pinned here. Deepgram and Cartesia both default to 24kHz;
# stating it explicitly makes the invariant enforceable rather than incidental.
SAMPLE_RATE = 24000

# Sales default: Asteria — FEMININE, American, "clear, confident, knowledgeable,
# energetic". Chosen for consistency over theatrics.
#
# NOTE: this voice is feminine, so `agent_name` in config/tenants.json must be a
# name that matches it. A voice that opens with "I'm William" in a woman's voice
# is the first thing a prospect notices and it destroys the illusion instantly.
# Keep the two in sync whenever either changes.
#
# Deepgram cannot perform ElevenLabs' inline emotion tags, so delivery here comes
# from the writing rather than [sighs]/[laughs]; state/agents.py strips those tags
# before synthesis so a non-v3 voice can never read them aloud. To get emotional
# tags back, pick an "ElevenLabs ... (v3)" voice in the demo's picker — switching
# is live and takes effect on the next sentence.
DEFAULT_VOICE_ID = "deepgram:aura-2-asteria-en"
# Fallback when the configured default is unavailable.
DEEPGRAM_DEFAULT_VOICE_ID = "deepgram:aura-2-asteria-en"
# The dispatch product shipped on Apollo; keep that the dispatch default so this
# refactor does not silently change how existing tenants sound.
DISPATCH_DEFAULT_VOICE_ID = "deepgram:aura-2-apollo-en"


@dataclass(frozen=True)
class VoiceProfile:
    """A selectable voice. `voice_id` is the stable public handle — it is what the
    demo page sends and what tenant config stores."""

    voice_id: str
    provider: str
    model: str
    voice: str
    label: str
    gender: str
    accent: str
    traits: tuple[str, ...]
    blurb: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    # Provider-specific tuning (currently ElevenLabs stability/style/speed).
    # Kept opaque so adding a provider knob does not change this dataclass.
    settings: tuple[tuple[str, float | bool], ...] = field(default_factory=tuple)

    def settings_dict(self) -> dict:
        return dict(self.settings)

    def to_dict(self) -> dict:
        return {
            "voice_id": self.voice_id,
            "provider": self.provider,
            "label": self.label,
            "gender": self.gender,
            "accent": self.accent,
            "traits": list(self.traits),
            "blurb": self.blurb,
            "tags": list(self.tags),
        }


def _dg(name: str, label: str, gender: str, traits: tuple[str, ...], blurb: str,
        accent: str = "American", tags: tuple[str, ...] = ()) -> VoiceProfile:
    model = f"aura-2-{name}-en"
    return VoiceProfile(
        voice_id=f"deepgram:{model}",
        provider="deepgram",
        model=model,
        voice=model,
        label=label,
        gender=gender,
        accent=accent,
        traits=traits,
        blurb=blurb,
        tags=tags,
    )


# ── Catalog ───────────────────────────────────────────────────────────────────
# A curated slice of Aura-2's ~40 English voices rather than all of them. A demo
# voice picker with 40 entries is a worse product than one with 12 chosen for the
# job: every voice here is plausible on an outbound sales call, and the set spans
# warm/authoritative, feminine/masculine, and American/British/Southern so a
# client can actually hear the range. All IDs verified against Deepgram's docs.

_DEEPGRAM_VOICES: tuple[VoiceProfile, ...] = (
    _dg("thalia", "Thalia", "feminine", ("clear", "confident", "energetic"),
        "Bright and quick. The safest strong default for outbound sales.",
        tags=("recommended", "sales")),
    _dg("asteria", "Asteria", "feminine", ("clear", "knowledgeable", "energetic"),
        "Sounds like she knows the product cold. Good for technical buyers.",
        tags=("sales",)),
    _dg("luna", "Luna", "feminine", ("friendly", "natural", "engaging"),
        "Warm and unhurried. Lowers the guard of a cold prospect.",
        tags=("warm",)),
    _dg("cordelia", "Cordelia", "feminine", ("approachable", "warm", "polite"),
        "Polite and easy. Hard to be annoyed at.",
        tags=("warm",)),
    _dg("helena", "Helena", "feminine", ("caring", "natural", "raspy"),
        "Distinctive raspy texture — reads as a real person, not a voice actor.",
        tags=("creative",)),
    _dg("janus", "Janus", "feminine", ("southern", "smooth", "trustworthy"),
        "Southern US lilt. Memorable and disarming on a cold call.",
        accent="American (Southern)", tags=("creative",)),
    _dg("apollo", "Apollo", "masculine", ("confident", "comfortable", "casual"),
        "Relaxed authority. The current dispatch agent's voice.",
        tags=("dispatch",)),
    _dg("orpheus", "Orpheus", "masculine", ("professional", "clear", "trustworthy"),
        "Straight-down-the-middle professional. Very safe.",
        tags=("recommended", "sales")),
    _dg("zeus", "Zeus", "masculine", ("deep", "trustworthy", "smooth"),
        "Deep and authoritative. Carries weight on price conversations.",
        tags=("authoritative",)),
    _dg("atlas", "Atlas", "masculine", ("enthusiastic", "confident", "friendly"),
        "High energy. Good for a short, punchy opener.",
        tags=("sales",)),
    _dg("draco", "Draco", "masculine", ("warm", "approachable", "baritone"),
        "British baritone. Reads as premium and consultative.",
        accent="British", tags=("creative",)),
    _dg("pandora", "Pandora", "feminine", ("smooth", "calm", "melodic"),
        "British, calm and measured. Never sounds like it is selling.",
        accent="British", tags=("creative",)),
)

# Cartesia Sonic. Only the plugin's documented default voice is hardcoded — the
# rest are discovered from Cartesia's API at startup, because voice UUIDs are
# account-scoped and a hardcoded list would rot. See `discover_cartesia_voices`.
_CARTESIA_SEED: tuple[VoiceProfile, ...] = (
    VoiceProfile(
        voice_id="cartesia:f786b574-daa5-4673-aa0c-cbe3e8534c02",
        provider="cartesia",
        model="sonic-3",
        voice="f786b574-daa5-4673-aa0c-cbe3e8534c02",
        label="Sonic Default",
        gender="unknown",
        accent="American",
        traits=("fast", "natural", "expressive"),
        blurb="Cartesia Sonic-3 — the lowest-latency voice in the stack.",
        tags=("fastest",),
    ),
)

# ── ElevenLabs ────────────────────────────────────────────────────────────────
#
# Model choice is forced, not preferred. `eleven_v3` is the model with the
# emotional Audio Tags ([sighs], [laughs], [whispers], [breathes]) and it CANNOT
# be used here: ElevenLabs does not expose WebSockets for v3, their docs
# explicitly steer realtime/conversational use to Flash v2.5, and livekit-agents
# has no v3 streaming support (livekit/agents#4901). The plugin's TTSModels type
# lists "eleven_v3", which is a type, not a working streaming path — selecting it
# would stall or fail a live call. v3 is built for pre-rendered audio (audiobooks,
# dubbing) where the whole script is known up front. A cold call has no script.
#
# So expressiveness here comes from voice SETTINGS rather than inline tags:
#
#   stability        LOWER is more emotional and variable. ~0.30-0.40 gives a
#                    real cold-call lift; below ~0.25 it starts to wander.
#   style            HIGHER exaggerates the voice's own character. Above ~0.6 it
#                    both destabilises and measurably raises latency.
#   speed            A touch above 1.0 reads as energy rather than rushing.
#   use_speaker_boost  Improves presence, small latency cost.
ELEVEN_MODEL_REALTIME = "eleven_flash_v2_5"   # ~75ms, the realtime recommendation
ELEVEN_MODEL_QUALITY = "eleven_turbo_v2_5"    # a little richer, still streams
# v3 — the ONLY model that speaks inline emotional Audio Tags ([sighs], [laughs],
# [warmly]) in a live call. It has no WebSocket (the official plugin gets a hard
# 403), so it is driven over HTTP streaming by our own TTS in tts/eleven_v3.py.
# Measured on the SAME transport, v3 costs ~125ms more than Flash — the "v3 can't
# do realtime" received wisdom is really "v3 has no WebSocket".
ELEVEN_MODEL_EXPRESSIVE = "eleven_v3"

# Tuned for an energetic outbound opener.
_ENERGETIC = (
    ("stability", 0.35),
    ("similarity_boost", 0.75),
    ("style", 0.45),
    ("speed", 1.05),
    ("use_speaker_boost", True),
)
# For the rest of the call: steadier, so long answers do not wobble.
_WARM = (
    ("stability", 0.5),
    ("similarity_boost", 0.75),
    ("style", 0.3),
    ("speed", 1.0),
    ("use_speaker_boost", True),
)
# For v3. Closer to neutral ON PURPOSE: the emotion comes from the inline tags,
# and stacking a low stability on top of them makes delivery wander mid-sentence.
# Let the tags act; let the settings stay out of the way.
_EXPRESSIVE = (
    ("stability", 0.4),
    ("similarity_boost", 0.75),
    ("style", 0.35),
    ("speed", 1.0),
    ("use_speaker_boost", True),
)

# Only the plugin's own default voice is seeded. Real voices are discovered from
# the account at startup (`discover_elevenlabs_voices`) because voice ids are
# account-scoped — a hardcoded list rots the moment the library changes.
_ELEVENLABS_SEED: tuple[VoiceProfile, ...] = (
    VoiceProfile(
        voice_id=f"elevenlabs:{'hpp4J3VqNfWAUOO0d1Us'}",
        provider="elevenlabs",
        # v3 by default: it is the only model that performs inline [sighs] and
        # [laughs] during a live call, which is the whole point of the demo.
        model=ELEVEN_MODEL_EXPRESSIVE,
        voice="hpp4J3VqNfWAUOO0d1Us",
        label="ElevenLabs v3 (emotional)",
        gender="unknown",
        accent="American",
        traits=("emotional", "natural", "expressive"),
        blurb="ElevenLabs v3 — breathes, sighs and laughs mid-sentence.",
        tags=("recommended", "emotional"),
        settings=_EXPRESSIVE,
    ),
)


def _provider_available(provider: str) -> bool:
    return bool(os.getenv({
        "deepgram": "DEEPGRAM_API_KEY",
        "cartesia": "CARTESIA_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
    }.get(provider, ""), ""))


_catalog: dict[str, VoiceProfile] = {
    v.voice_id: v for v in _ELEVENLABS_SEED + _DEEPGRAM_VOICES + _CARTESIA_SEED
}


def register_voice(profile: VoiceProfile) -> None:
    _catalog[profile.voice_id] = profile


def list_voices(*, available_only: bool = True) -> list[VoiceProfile]:
    """The voice catalog, by default filtered to providers that have a key.

    Ordering is deliberate: recommended voices first, then by provider, so the
    demo picker's first option is always a good one.
    """
    voices = list(_catalog.values())
    if available_only:
        voices = [v for v in voices if _provider_available(v.provider)]
    return sorted(
        voices,
        key=lambda v: (0 if "recommended" in v.tags else 1, v.provider, v.label),
    )


def get_voice(voice_id: str) -> VoiceProfile | None:
    return _catalog.get(voice_id)


def resolve_voice(voice_id: str = "", *, fallback: str = DEFAULT_VOICE_ID) -> VoiceProfile:
    """Resolve a voice id to a usable profile, degrading rather than raising.

    Voice ids arrive from tenant config and from the browser, so this must never
    take a call down. An unknown or unavailable voice logs and falls back. Legacy
    bare Deepgram model names (`aura-2-hera-en`, as still stored in tenants.json)
    are accepted and normalised.
    """
    if voice_id and ":" not in voice_id:
        voice_id = f"deepgram:{voice_id}"

    profile = _catalog.get(voice_id) if voice_id else None

    if profile is None and voice_id:
        # An unknown Deepgram model is probably a real Aura voice we just did not
        # curate — pass it through rather than silently substituting a default.
        if voice_id.startswith("deepgram:aura"):
            model = voice_id.split(":", 1)[1]
            logger.info("voice_uncurated_passthrough", voice_id=voice_id)
            return VoiceProfile(
                voice_id=voice_id, provider="deepgram", model=model, voice=model,
                label=model, gender="unknown", accent="unknown",
                traits=(), blurb="", tags=("uncurated",),
            )
        logger.warning("voice_unknown", voice_id=voice_id, fallback=fallback)

    if profile is not None and not _provider_available(profile.provider):
        logger.warning(
            "voice_provider_unavailable",
            voice_id=voice_id,
            provider=profile.provider,
            hint=f"set {profile.provider.upper()}_API_KEY to enable this voice",
            fallback=fallback,
        )
        profile = None

    if profile is not None:
        return profile

    fallback_profile = _catalog.get(fallback)
    if fallback_profile is not None and _provider_available(fallback_profile.provider):
        return fallback_profile

    # The requested fallback is itself unavailable — most often DEFAULT_VOICE_ID
    # pointing at ElevenLabs on a deployment with no ELEVENLABS_API_KEY. Step to
    # the Deepgram default explicitly rather than taking whatever sorts first, so
    # a missing key produces a chosen voice and not an arbitrary one.
    deepgram_default = _catalog.get(DEEPGRAM_DEFAULT_VOICE_ID)
    if deepgram_default is not None and _provider_available(deepgram_default.provider):
        logger.info(
            "voice_fell_back_to_deepgram",
            requested=voice_id or fallback,
            using=DEEPGRAM_DEFAULT_VOICE_ID,
            hint="set ELEVENLABS_API_KEY for the more expressive default",
        )
        return deepgram_default

    # Last resort: anything at all that we can actually speak with.
    usable = list_voices(available_only=True)
    if not usable:
        raise RuntimeError(
            "no TTS provider is configured — set DEEPGRAM_API_KEY "
            "(or ELEVENLABS_API_KEY / CARTESIA_API_KEY)"
        )
    return usable[0]


def build_tts(voice_id: str = "", *, fallback: str = DEFAULT_VOICE_ID) -> tts_base.TTS:
    """Construct a concrete TTS for a voice id."""
    profile = resolve_voice(voice_id, fallback=fallback)

    if profile.provider == "deepgram":
        from livekit.plugins import deepgram
        return deepgram.TTS(model=profile.model, sample_rate=SAMPLE_RATE)

    if profile.provider == "cartesia":
        from livekit.plugins import cartesia
        return cartesia.TTS(
            model=profile.model,
            voice=profile.voice,
            sample_rate=SAMPLE_RATE,
            # Sonic streams sentence-by-sentence; the pacer holds back text so the
            # model gets enough context to prosody-plan without stalling TTFB.
            text_pacing=True,
        )

    if profile.provider == "elevenlabs":
        tuning = profile.settings_dict() or dict(_ENERGETIC)

        if profile.model == ELEVEN_MODEL_EXPRESSIVE:
            # v3 cannot use the official plugin (no WebSocket → 403), so it goes
            # through our HTTP-streaming implementation. This is the path that
            # gives inline [sighs]/[laughs] emotion during a live conversation.
            from tts.eleven_v3 import create_v3_tts

            return create_v3_tts(
                api_key=os.getenv("ELEVENLABS_API_KEY", ""),
                voice_id=profile.voice,
                stability=tuning.get("stability", 0.4),
                similarity_boost=tuning.get("similarity_boost", 0.75),
                style=tuning.get("style", 0.35),
                speed=tuning.get("speed", 1.0),
                use_speaker_boost=tuning.get("use_speaker_boost", True),
            )

        from livekit.plugins import elevenlabs
        return elevenlabs.TTS(
            model=profile.model,
            voice_id=profile.voice,
            # Passed explicitly. The plugin reads ELEVEN_API_KEY from the
            # environment, but this project standardises on ELEVENLABS_API_KEY
            # (matching the vendor's own naming and the rest of our config), so
            # relying on the plugin's lookup raises "API key is required" even
            # with a perfectly good key present.
            api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            voice_settings=elevenlabs.VoiceSettings(
                stability=tuning.get("stability", 0.35),
                similarity_boost=tuning.get("similarity_boost", 0.75),
                style=tuning.get("style", 0.45),
                speed=tuning.get("speed", 1.05),
                use_speaker_boost=tuning.get("use_speaker_boost", True),
            ),
            language="en",
            # Streams as soon as a chunk is ready instead of waiting on
            # punctuation, which is the single biggest ElevenLabs TTFB win.
            auto_mode=True,
            # ElevenLabs emits 24kHz PCM, matching SAMPLE_RATE so the switchable
            # wrapper can swap to/from it without resampling.
            encoding="pcm_24000",
        )

    raise ValueError(f"unknown TTS provider: {profile.provider!r}")


class SwitchableTTS(tts_base.TTS):
    """A TTS that delegates to an inner instance which can be swapped live.

    Instances are cached per voice id, so switching back to a previously used
    voice reuses its warmed connection pool instead of paying a cold TLS
    handshake on the first utterance.
    """

    def __init__(self, voice_id: str = "", *, fallback: str = DEFAULT_VOICE_ID):
        self._fallback = fallback
        profile = resolve_voice(voice_id, fallback=fallback)
        inner = build_tts(profile.voice_id, fallback=fallback)

        super().__init__(
            # Conservative capabilities: reported once at construction but must
            # hold for every voice we might swap to. Both providers stream;
            # aligned_transcript is not universal, so we do not claim it.
            capabilities=tts_base.TTSCapabilities(streaming=True, aligned_transcript=False),
            sample_rate=SAMPLE_RATE,
            num_channels=1,
        )

        self._profile = profile
        self._inner = inner
        self._cache: dict[str, tts_base.TTS] = {profile.voice_id: inner}
        self._on_switch = None

    # ── Introspection ──

    @property
    def profile(self) -> VoiceProfile:
        return self._profile

    @property
    def voice_id(self) -> str:
        return self._profile.voice_id

    def on_switch(self, callback) -> None:
        """Register `callback(VoiceProfile)`, fired after a successful switch.
        The demo HUD uses this to reflect the live voice."""
        self._on_switch = callback

    # ── Switching ──

    def _assert_compatible(self, candidate: tts_base.TTS, voice_id: str) -> None:
        if candidate.sample_rate != self.sample_rate:
            raise ValueError(
                f"voice {voice_id!r} synthesizes at {candidate.sample_rate}Hz but this "
                f"session is pinned to {self.sample_rate}Hz; swapping would corrupt playback"
            )
        if not candidate.capabilities.streaming:
            raise ValueError(f"voice {voice_id!r} does not support streaming synthesis")

    def switch(self, voice_id: str) -> VoiceProfile:
        """Change voice, taking effect on the next utterance.

        Returns the profile actually in use — which may differ from the request
        if it resolved to a fallback. Callers should surface the returned id
        rather than assume the requested one took.
        """
        profile = resolve_voice(voice_id, fallback=self._fallback)
        if profile.voice_id == self._profile.voice_id:
            return profile

        inner = self._cache.get(profile.voice_id)
        if inner is None:
            inner = build_tts(profile.voice_id, fallback=self._fallback)
            self._assert_compatible(inner, profile.voice_id)
            inner.prewarm()
            self._cache[profile.voice_id] = inner

        previous = self._profile
        self._inner = inner
        self._profile = profile
        logger.info(
            "voice_switched",
            from_voice=previous.voice_id,
            to_voice=profile.voice_id,
            provider=profile.provider,
        )
        if self._on_switch is not None:
            try:
                self._on_switch(profile)
            except Exception as e:
                logger.debug("voice switch callback failed", error=str(e))
        return profile

    # ── TTS interface — delegate to whichever inner is current ──

    def synthesize(self, text: str, *, conn_options=tts_base.APIConnectOptions()
                   if hasattr(tts_base, "APIConnectOptions") else None, **kwargs):
        return self._inner.synthesize(text, conn_options=conn_options, **kwargs)

    def stream(self, **kwargs):
        # Reads _inner once, so an in-flight utterance always finishes in the
        # voice it started in even if a switch lands mid-stream.
        return self._inner.stream(**kwargs)

    def prewarm(self) -> None:
        self._inner.prewarm()

    async def aclose(self) -> None:
        for inner in self._cache.values():
            try:
                await inner.aclose()
            except Exception as e:
                logger.debug("tts close failed", error=str(e))
        self._cache.clear()


async def discover_elevenlabs_voices(*, limit: int = 12) -> int:
    """Pull the account's ElevenLabs voices into the catalog.

    Voice ids are account-scoped, so hardcoding a list would rot as soon as the
    client's library changes. Every discovered voice is registered twice: once on
    Flash v2.5 (fastest, the realtime recommendation) and once on Turbo v2.5
    (slightly richer), so the demo's picker can A/B latency against quality on
    the same voice.

    Best-effort — any failure leaves the seeded default and the rest of the
    catalog untouched.
    """
    if not _provider_available("elevenlabs"):
        return 0

    import httpx

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY", "")},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as e:
        logger.warning("elevenlabs_voice_discovery_failed", error=str(e))
        return 0

    added = 0
    for voice in payload.get("voices", [])[:limit]:
        vid, name = voice.get("voice_id"), voice.get("name")
        if not vid or not name:
            continue
        labels = voice.get("labels") or {}
        gender = labels.get("gender", "unknown")
        accent = labels.get("accent", "American")
        description = (voice.get("description") or labels.get("description") or "").strip()

        for model, suffix, tuning, tags in (
            # v3 first: it is the only one that speaks [sighs]/[laughs] inline, and
            # it is the demo default. ~125ms slower than Flash on the same
            # transport — worth it for a call that has to feel human.
            (ELEVEN_MODEL_EXPRESSIVE, ":v3", _EXPRESSIVE, ("recommended", "emotional")),
            (ELEVEN_MODEL_REALTIME, "", _ENERGETIC, ("fastest", "expressive")),
            (ELEVEN_MODEL_QUALITY, ":turbo", _WARM, ("expressive",)),
        ):
            register_voice(VoiceProfile(
                voice_id=f"elevenlabs:{vid}{suffix}",
                provider="elevenlabs",
                model=model,
                voice=vid,
                label=f"{name}{' (turbo)' if suffix else ''}",
                gender=gender,
                accent=accent,
                traits=("expressive", "natural"),
                blurb=description[:160] or f"ElevenLabs {name} on {model}.",
                tags=tags,
                settings=tuning,
            ))
            added += 1

    logger.info("elevenlabs_voices_discovered", count=added)
    return added


async def discover_cartesia_voices(*, limit: int = 12) -> int:
    """Pull the account's Cartesia voices into the catalog.

    Cartesia voice ids are account-scoped UUIDs, so hardcoding a list would rot
    the moment the client's library changes. Best-effort: any failure leaves the
    seeded default in place and the rest of the catalog untouched.
    """
    if not _provider_available("cartesia"):
        return 0

    import httpx

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                "https://api.cartesia.ai/voices",
                headers={
                    "X-API-Key": os.getenv("CARTESIA_API_KEY", ""),
                    "Cartesia-Version": "2025-04-16",
                },
                params={"limit": limit},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as e:
        logger.warning("cartesia_voice_discovery_failed", error=str(e))
        return 0

    voices = payload.get("data", payload if isinstance(payload, list) else [])
    added = 0
    for voice in voices:
        vid, name = voice.get("id"), voice.get("name")
        if not vid or not name:
            continue
        register_voice(VoiceProfile(
            voice_id=f"cartesia:{vid}",
            provider="cartesia",
            model="sonic-3",
            voice=vid,
            label=name,
            gender=voice.get("gender", "unknown"),
            accent=voice.get("language", "en"),
            traits=("fast", "expressive"),
            blurb=(voice.get("description") or "Cartesia Sonic-3 voice.")[:160],
            tags=("fastest",),
        ))
        added += 1

    logger.info("cartesia_voices_discovered", count=added)
    return added
