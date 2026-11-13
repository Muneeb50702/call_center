"""
Shared plumbing for the Fish Audio voice bot: TTS, STT, LLM, voice catalog.

Deliberately provider-explicit so each hop can be swapped or debugged alone:

    STT   Deepgram nova-3   (Fish /v1/asr is behind paid API credit -> 402)
    LLM   gpt-4o-mini       (general purpose, not domain specific)
    TTS   Fish s2.1-pro-free

Fish's API credit is billed separately from platform credit. On a key with no
API credit, only `s2.1-pro-free` works; `s2.1-pro` / `s2-pro` / `s1` and every
`/v1/asr` call return 402. s2.1-pro-free is the same generation as s2.1-pro, so
voice quality is representative -- it just carries no latency/DPA guarantee.
"""

from __future__ import annotations

import io
import os
import wave

import requests
from dotenv import load_dotenv

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO_ROOT, ".env"))

FISH_BASE = "https://api.fish.audio"
FISH_MODEL = os.getenv("FISH_MODEL", "s2.1-pro-free")
FISH_KEY = os.getenv("FISH_API_KEY") or os.getenv("FISH_AUDIO_API_KEY") or ""

DEEPGRAM_KEY = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Fish PCM output, confirmed by inspecting a decoded clip.
PCM_RATE = 44100
PCM_CHANNELS = 1
PCM_WIDTH = 2  # S16_LE

# General-purpose assistant. Intentionally domain-free: no dispatch, freight,
# logistics or company framing -- this is a plain gpt-4o-mini-style helper that
# happens to speak. The only constraints are voice-shaped ones.
SYSTEM_PROMPT = (
    "You are a helpful, knowledgeable voice assistant. Help with anything the "
    "user asks: general questions, explanations, brainstorming, writing, math, "
    "code, advice, trivia, language practice, planning.\n\n"
    "Your replies are spoken aloud by a text-to-speech engine, so:\n"
    "- Keep answers to 1-3 short sentences unless asked for more detail.\n"
    "- Write plain prose. No markdown, no bullet points, no headings, no emoji, "
    "no code blocks. If you must give steps, say them as a sentence.\n"
    "- Expand symbols into words a listener can follow (say 'twenty percent' "
    "rather than '20%').\n"
    "- If a question is ambiguous, ask one short clarifying question.\n"
    "- If you don't know something, say so plainly instead of guessing."
)


# Fish S2 emotion markers. S2 takes [square brackets] and, unlike S1's fixed
# (parenthesis) vocabulary, accepts free-form descriptions like [warm and
# amused] or intensity modifiers like [very excited]. Verified working on
# s2.1-pro-free: markers are consumed as direction, never spoken.
EXPRESSION_RULES = """
You may add Fish Audio S2 emotion markers in square brackets to direct how your
reply is performed. They are stage directions -- they are never read aloud.

Useful markers:
- Feeling (put at the start of a sentence): [happy] [excited] [calm] [curious]
  [empathetic] [confident] [surprised] [grateful] [sad] [worried] [sarcastic]
- Intensity: [slightly sad] [very excited] -- or free-form like [warm and amused]
- Delivery (anywhere): [whispering] [soft tone] [emphasis] [shouting]
- Sounds (anywhere): [laughing] [chuckling] [sighing] [gasping] [clear throat]
- Pauses (anywhere): [break] short, [long-break] longer

Rules:
- Use at most two markers per reply. Most sentences need none.
- Only add one where it genuinely fits the meaning; a tag on every sentence
  sounds unhinged, not expressive.
- Markers are the ONLY square brackets allowed. Never bracket anything else.
- Everything outside the brackets stays plain spoken prose.
""".strip()

SYSTEM_PROMPT_EXPRESSIVE = SYSTEM_PROMPT + "\n\n" + EXPRESSION_RULES


class ConfigError(RuntimeError):
    pass


def missing_keys() -> list[str]:
    out = []
    if not FISH_KEY:
        out.append("FISH_API_KEY")
    if not OPENAI_KEY:
        out.append("OPENAI_API_KEY")
    if not DEEPGRAM_KEY:
        out.append("DEEPGRAM_API_KEY")
    return out


# --------------------------------------------------------------------------- #
# Fish Audio TTS
# --------------------------------------------------------------------------- #
def _tts_body(text: str, voice_id: str | None, speed: float,
              fmt: str = "pcm", mp3_bitrate: int = 192) -> dict:
    body: dict[str, object] = {
        "text": text,
        # pcm is header-less and we frame it ourselves (see wrap_wav); mp3 is
        # self-describing, so it needs no fixing up.
        "format": fmt,
        "latency": "balanced",
        "chunk_length": 200,
        "normalize": True,
    }
    if fmt == "pcm":
        body["sample_rate"] = PCM_RATE
    elif fmt == "mp3":
        body["mp3_bitrate"] = mp3_bitrate  # 64 | 128 | 192
    if voice_id:
        body["reference_id"] = voice_id
    if speed and speed != 1.0:
        body["prosody"] = {"speed": speed}
    return body


def _tts_headers() -> dict:
    if not FISH_KEY:
        raise ConfigError("FISH_API_KEY is not set")
    return {
        "Authorization": f"Bearer {FISH_KEY}",
        "Content-Type": "application/json",
        "model": FISH_MODEL,  # required on every request
    }


def tts_pcm(text: str, voice_id: str | None = None, speed: float = 1.0) -> bytes:
    return tts_bytes(text, voice_id, speed, fmt="pcm")


def tts_bytes(text: str, voice_id: str | None = None, speed: float = 1.0,
              fmt: str = "pcm", mp3_bitrate: int = 192) -> bytes:
    """Synthesize in whichever container Fish supports: pcm | mp3 | wav | opus.

    Prefer mp3 for anything you need to *share* -- WhatsApp, Slack, iMessage and
    most players reject or mishandle WAV. Prefer pcm for local playback and for
    files you post-process, since it sidesteps Fish's broken streaming WAV header.
    """
    r = requests.post(
        f"{FISH_BASE}/v1/tts",
        headers=_tts_headers(),
        json=_tts_body(text, voice_id, speed, fmt, mp3_bitrate),
        timeout=180,
    )
    if r.status_code >= 400:
        raise ConfigError(f"fish tts {r.status_code}: {r.text[:300]}")
    return r.content


def tts_stream(text: str, voice_id: str | None = None, speed: float = 1.0):
    """Yield PCM chunks as they arrive, for progressive playback."""
    r = requests.post(
        f"{FISH_BASE}/v1/tts",
        headers=_tts_headers(),
        json=_tts_body(text, voice_id, speed),
        stream=True,
        timeout=180,
    )
    if r.status_code >= 400:
        raise ConfigError(f"fish tts {r.status_code}: {r.text[:300]}")
    for chunk in r.iter_content(chunk_size=4096):
        if chunk:
            yield chunk


def wrap_wav(pcm: bytes) -> bytes:
    """Frame raw PCM as a valid WAV.

    Fish's own format:"wav" is a streaming WAV with a placeholder length in the
    header -- a 1.9s clip decodes as ~48,695s, which breaks anything that trusts
    the header (browsers included). Requesting PCM and writing the header here
    sidesteps that.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(PCM_CHANNELS)
        w.setsampwidth(PCM_WIDTH)
        w.setframerate(PCM_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def wav_header(data_bytes: int = 0xFFFFFFF0) -> bytes:
    """A WAV header with an open-ended length, for streaming to a browser.

    Browsers need a header before they will decode anything, but with chunked
    transfer we don't know the length up front -- so declare a huge one and let
    the connection end define the real length. (This is what Fish does; it's
    fine for playback, which is why the /speak endpoint streams. It is *not*
    fine for files on disk, which is what wrap_wav is for.)
    """
    return (
        b"RIFF" + (data_bytes + 36).to_bytes(4, "little") + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")                      # PCM
        + PCM_CHANNELS.to_bytes(2, "little")
        + PCM_RATE.to_bytes(4, "little")
        + (PCM_RATE * PCM_CHANNELS * PCM_WIDTH).to_bytes(4, "little")
        + (PCM_CHANNELS * PCM_WIDTH).to_bytes(2, "little")
        + (PCM_WIDTH * 8).to_bytes(2, "little")
        + b"data" + data_bytes.to_bytes(4, "little")
    )


def pcm_seconds(pcm: bytes) -> float:
    return len(pcm) / (PCM_RATE * PCM_CHANNELS * PCM_WIDTH)


# --------------------------------------------------------------------------- #
# Voice catalog
# --------------------------------------------------------------------------- #
def list_voices(query: str | None = None, limit: int = 20) -> list[dict]:
    params: dict[str, object] = {"page_size": limit}
    if query:
        params["title"] = query
    r = requests.get(
        f"{FISH_BASE}/model",
        params=params,
        headers={"Authorization": f"Bearer {FISH_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    return [
        {
            "id": v.get("_id") or v.get("id"),
            "title": v.get("title") or "(untitled)",
            "languages": v.get("languages") or [],
        }
        for v in r.json().get("items", [])
        if (v.get("_id") or v.get("id"))
    ]


# --------------------------------------------------------------------------- #
# Speech to text
# --------------------------------------------------------------------------- #
STT_MODEL = os.getenv("STT_MODEL", "nova-2")


def stt(audio: bytes, content_type: str = "audio/webm",
        model: str | None = None, smart_format: bool = True) -> tuple[str, str]:
    """Transcribe. Returns (text, engine). Deepgram handles webm/opus natively,
    so browser MediaRecorder output needs no transcoding (there's no ffmpeg here).

    Defaults to nova-2, not nova-3: nova-3 returned an empty transcript for some
    perfectly clean Fish clips (verified healthy audio -- rms 0.28, 4% silence,
    normal speech spectrum -- that nova-2, base and enhanced all transcribed
    correctly). nova-3 is fine most of the time but not reliable enough to
    measure against.

    smart_format=False matters when comparing against known text: with it on,
    Deepgram rewrites spoken numbers into digits ("seventeen percent" -> "17%",
    "eighteen eleven" -> "1811"), which looks like a transcription error when it
    is only a formatting difference.
    """
    if not DEEPGRAM_KEY:
        raise ConfigError("DEEPGRAM_API_KEY is not set")
    r = requests.post(
        "https://api.deepgram.com/v1/listen",
        params={"model": model or STT_MODEL,
                "smart_format": "true" if smart_format else "false",
                "language": "en"},
        headers={"Authorization": f"Token {DEEPGRAM_KEY}",
                 "Content-Type": content_type},
        data=audio,
        timeout=120,
    )
    if r.status_code >= 400:
        raise ConfigError(f"deepgram {r.status_code}: {r.text[:300]}")
    alts = r.json()["results"]["channels"][0]["alternatives"]
    return ((alts[0]["transcript"] if alts else "").strip(), "deepgram")


# --------------------------------------------------------------------------- #
# LLM
# --------------------------------------------------------------------------- #
def llm(history: list[dict], expressive: bool = False) -> str:
    """expressive=True asks the model to embed Fish S2 emotion markers."""
    if not OPENAI_KEY:
        raise ConfigError("OPENAI_API_KEY is not set")
    prompt = SYSTEM_PROMPT_EXPRESSIVE if expressive else SYSTEM_PROMPT
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_KEY}",
                 "Content-Type": "application/json"},
        json={
            "model": OPENAI_MODEL,
            "messages": [{"role": "system", "content": prompt}] + history,
            "max_tokens": 300,
            "temperature": 0.7,
        },
        timeout=90,
    )
    if r.status_code >= 400:
        raise ConfigError(f"openai {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"].strip()
