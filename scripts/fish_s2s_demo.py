#!/usr/bin/env python3
"""
Fish Audio speech-to-speech demo / accent playground.

Fish Audio has no single speech-to-speech model yet (they've said one is in
development), so this wires up the three pieces they *do* ship:

    mic -> ASR (/v1/asr) -> LLM -> Fish TTS (/v1/tts, s2.1-pro) -> speaker

s2.1-pro is their current best model and where the accent/prosody quality is.
TTS streams as raw PCM into the player, so audio starts before the whole clip
is generated (~0.6s to first word in testing).

Audio I/O goes through ALSA (`arecord` / `aplay`) instead of sounddevice,
because PortAudio isn't installed on this box and subprocess piping needs no
extra deps.

Setup
-----
Keys are read from the repo's .env (gitignored), or the environment:

    FISH_API_KEY       required
    FISH_MODEL         default s2.1-pro-free (see the credit note below)
    GROQ_API_KEY       LLM brain; optional, --echo skips the LLM entirely
    DEEPGRAM_API_KEY   STT fallback; see the credit note below

Credit note: Fish's API credit is billed separately from platform credit. With
an un-topped-up key, only `s2.1-pro-free` TTS works -- `s2.1-pro`, `s2-pro`,
`s1`, and *all* of `/v1/asr` return 402. s2.1-pro-free is the same generation as
s2.1-pro (no TTFA/DPA guarantee), so voice quality is representative. Because
Fish ASR is credit-gated, --stt auto falls back to Deepgram for the listening
half; add API credit and use --stt fish for an all-Fish pipeline.

Usage
-----
    # 1. Pure TTS test - fastest way to judge accent quality
    python scripts/fish_s2s_demo.py say "Hey there, thanks for calling Nexus Dispatch."

    # 2. Find a voice with the accent you want, then reuse its id
    python scripts/fish_s2s_demo.py voices british
    export FISH_VOICE_ID=<reference_id from above>

    # 3. Full speech-to-speech chat loop (push-to-talk: Enter to start/stop)
    python scripts/fish_s2s_demo.py chat

    # 4. One turn from an existing audio file (no mic needed)
    python scripts/fish_s2s_demo.py once /path/to/question.wav

    # Talk to yourself, no LLM in the middle - isolates voice quality
    python scripts/fish_s2s_demo.py chat --echo
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave

import requests
from dotenv import load_dotenv

# Repo .env carries FISH_API_KEY / GROQ_API_KEY / DEEPGRAM_API_KEY.
# Real env vars win, so you can still override per-invocation.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

FISH_BASE = "https://api.fish.audio"
# s2.1-pro-free is the free tier and is the same generation as s2.1-pro.
# The paid models (s2.1-pro, s2-pro, s1) need API credit topped up separately
# from platform credit, otherwise every request 402s.
FISH_MODEL = os.getenv("FISH_MODEL", "s2.1-pro-free")
FISH_VOICE_ID = os.getenv("FISH_VOICE_ID") or None

# Raw PCM out of TTS so we can pipe straight into aplay and start hearing
# audio before the whole clip has been generated.
PCM_RATE = 44100
PCM_CHANNELS = 1

SYSTEM_PROMPT = (
    "You are a friendly voice assistant on a phone call. "
    "Reply in one or two short spoken sentences. No markdown, no lists, "
    "no emoji - everything you say gets read aloud by a TTS engine."
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def die(msg: str) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def fish_key() -> str:
    key = os.getenv("FISH_API_KEY") or os.getenv("FISH_AUDIO_API_KEY")
    if not key:
        die("set FISH_API_KEY (get one at https://fish.audio/go/api-keys)")
    return key


def which_or_die(*names: str) -> str:
    for n in names:
        if shutil.which(n):
            return n
    die(f"need one of {', '.join(names)} on PATH")


# --------------------------------------------------------------------------- #
# Fish Audio API
# --------------------------------------------------------------------------- #
def fish_voices(query: str | None, page_size: int = 20) -> list[dict]:
    """Search the public voice library. GET /model"""
    params: dict[str, object] = {"page_size": page_size}
    if query:
        params["title"] = query
    r = requests.get(
        f"{FISH_BASE}/model",
        params=params,
        headers={"Authorization": f"Bearer {fish_key()}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("items", [])


def fish_asr(audio: bytes, language: str | None = "en") -> str:
    """Speech -> text. POST /v1/asr (multipart). Needs paid API credit."""
    files = {"audio": ("input.wav", audio, "audio/wav")}
    data = {"ignore_timestamps": "true"}
    if language:
        data["language"] = language
    r = requests.post(
        f"{FISH_BASE}/v1/asr",
        headers={"Authorization": f"Bearer {fish_key()}"},
        files=files,
        data=data,
        timeout=120,
    )
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


def deepgram_asr(audio: bytes) -> str:
    """Fallback speech -> text, so the loop still runs without Fish credit."""
    key = os.getenv("DEEPGRAM_API_KEY")
    if not key:
        die("no DEEPGRAM_API_KEY for the STT fallback; add Fish API credit "
            "or run with --echo")
    r = requests.post(
        "https://api.deepgram.com/v1/listen",
        params={"model": "nova-2", "smart_format": "true", "language": "en"},
        headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
        data=audio,
        timeout=120,
    )
    r.raise_for_status()
    alts = r.json()["results"]["channels"][0]["alternatives"]
    return (alts[0]["transcript"] if alts else "").strip()


def transcribe(audio: bytes, engine: str = "auto") -> tuple[str, str]:
    """Returns (text, engine_actually_used).

    Fish ASR is gated behind paid API credit (402 on the free tier), so 'auto'
    tries Fish and quietly falls back to Deepgram rather than dead-ending.
    """
    if engine == "deepgram":
        return deepgram_asr(audio), "deepgram"
    try:
        return fish_asr(audio), "fish"
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        if engine == "fish" or status not in (401, 402, 403):
            raise
        print(f"  (fish asr unavailable: {status} - falling back to deepgram)")
        return deepgram_asr(audio), "deepgram"


def _tts_body(text: str, voice_id: str | None, fmt: str, speed: float) -> dict:
    body: dict[str, object] = {
        "text": text,
        "format": fmt,
        "latency": "balanced",  # noticeably snappier than "normal"
        "chunk_length": 200,
        "normalize": True,
    }
    if fmt == "pcm":
        body["sample_rate"] = PCM_RATE
    if voice_id:
        body["reference_id"] = voice_id
    if speed != 1.0:
        body["prosody"] = {"speed": speed}
    return body


def fish_tts_stream(text: str, voice_id: str | None, speed: float = 1.0):
    """Speech synthesis, yielding raw PCM chunks as they arrive."""
    r = requests.post(
        f"{FISH_BASE}/v1/tts",
        headers={
            "Authorization": f"Bearer {fish_key()}",
            "Content-Type": "application/json",
            "model": FISH_MODEL,  # required on every request
        },
        json=_tts_body(text, voice_id, "pcm", speed),
        stream=True,
        timeout=180,
    )
    if r.status_code >= 400:
        die(f"tts {r.status_code}: {r.text[:400]}")
    for chunk in r.iter_content(chunk_size=4096):
        if chunk:
            yield chunk


def fish_tts_bytes(text: str, voice_id: str | None, fmt: str = "pcm",
                   speed: float = 1.0) -> bytes:
    r = requests.post(
        f"{FISH_BASE}/v1/tts",
        headers={
            "Authorization": f"Bearer {fish_key()}",
            "Content-Type": "application/json",
            "model": FISH_MODEL,
        },
        json=_tts_body(text, voice_id, fmt, speed),
        timeout=180,
    )
    if r.status_code >= 400:
        die(f"tts {r.status_code}: {r.text[:400]}")
    return r.content


def write_wav(path: str, pcm: bytes) -> float:
    """Wrap raw PCM in a correct WAV header; returns duration in seconds.

    Fish's own `format: "wav"` output is a streaming WAV whose header declares a
    placeholder data length (it decoded as ~48000 seconds for a 2-second clip),
    which confuses anything that trusts the header. Requesting PCM and writing
    the header locally avoids that entirely.
    """
    with wave.open(path, "wb") as w:
        w.setnchannels(PCM_CHANNELS)
        w.setsampwidth(2)  # S16_LE
        w.setframerate(PCM_RATE)
        w.writeframes(pcm)
    return len(pcm) / (2 * PCM_CHANNELS * PCM_RATE)


# --------------------------------------------------------------------------- #
# LLM brain (OpenAI-compatible; Groq by default, matching this repo)
# --------------------------------------------------------------------------- #
def llm_reply(history: list[dict]) -> str:
    base = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    if not key:
        die("no GROQ_API_KEY / OPENAI_API_KEY set - run with --echo to skip the LLM")

    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history,
            "max_tokens": 150,
            "temperature": 0.7,
        },
        timeout=60,
    )
    if r.status_code >= 400:
        die(f"llm {r.status_code}: {r.text[:400]}")
    return r.json()["choices"][0]["message"]["content"].strip()


# --------------------------------------------------------------------------- #
# audio in / out
# --------------------------------------------------------------------------- #
def play_pcm_stream(chunks) -> tuple[float, float]:
    """Pipe PCM into aplay as it arrives.

    Returns (seconds_to_first_audio, seconds_of_audio_spoken). The first is the
    latency that actually matters for a voice bot; the wall-clock total is
    dominated by however long the reply takes to speak, which is not latency.
    """
    player = which_or_die("aplay")
    proc = subprocess.Popen(
        [player, "-q", "-t", "raw", "-f", "S16_LE",
         "-r", str(PCM_RATE), "-c", str(PCM_CHANNELS), "-"],
        stdin=subprocess.PIPE,
    )
    t0 = time.monotonic()
    ttfb, nbytes = None, 0
    try:
        for chunk in chunks:
            if ttfb is None:
                ttfb = time.monotonic() - t0
            nbytes += len(chunk)
            proc.stdin.write(chunk)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    proc.wait()
    return ttfb or 0.0, nbytes / (2 * PCM_CHANNELS * PCM_RATE)


def play_wav_file(path: str) -> None:
    subprocess.run([which_or_die("aplay"), "-q", path], check=False)


def record_push_to_talk() -> bytes | None:
    """Enter starts recording, Enter again stops. Returns WAV bytes."""
    rec = which_or_die("arecord")
    try:
        line = input("\n[Enter] to talk, or 'q' to quit > ").strip().lower()
    except EOFError:
        return None
    if line in {"q", "quit", "exit"}:
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    proc = subprocess.Popen(
        [rec, "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "wav", tmp.name],
        stderr=subprocess.DEVNULL,
    )
    print("  recording... [Enter] to stop")
    try:
        input()
    except EOFError:
        pass
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=5)

    with open(tmp.name, "rb") as f:
        data = f.read()
    os.unlink(tmp.name)

    try:
        with wave.open(io.BytesIO(data)) as w:
            secs = w.getnframes() / float(w.getframerate())
        if secs < 0.3:
            print("  (too short, nothing captured)")
            return None
    except wave.Error:
        pass  # not a parseable wav; let the ASR endpoint be the judge
    return data


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_voices(args) -> None:
    items = fish_voices(args.query, args.limit)
    if not items:
        print("no voices matched")
        return
    print(f"{'reference_id':<34}  {'lang':<6}  title")
    print("-" * 78)
    for v in items:
        vid = v.get("_id") or v.get("id") or ""
        langs = ",".join(v.get("languages") or []) or "-"
        print(f"{vid:<34}  {langs:<6}  {v.get('title', '')}")
    print("\nexport FISH_VOICE_ID=<reference_id> to use one of these.")


def cmd_say(args) -> None:
    text = " ".join(args.text)
    voice = args.voice or FISH_VOICE_ID
    print(f"model={FISH_MODEL} voice={voice or 'default'}")
    t0 = time.monotonic()
    if args.out:
        pcm = fish_tts_bytes(text, voice, fmt="pcm", speed=args.speed)
        secs = write_wav(args.out, pcm)
        print(f"wrote {args.out} ({len(pcm) / 1024:.0f} KB, {secs:.1f}s audio) "
              f"in {time.monotonic() - t0:.2f}s")
        play_wav_file(args.out)
    else:
        ttfb, spoken = play_pcm_stream(fish_tts_stream(text, voice, args.speed))
        print(f"first audio in {ttfb:.2f}s, spoke {spoken:.1f}s")


def _turn(audio: bytes, history: list[dict], echo: bool,
          voice: str | None, speed: float, stt: str = "auto") -> None:
    t0 = time.monotonic()
    said, engine = transcribe(audio, stt)
    t_asr = time.monotonic() - t0
    if not said:
        print("  (heard nothing)")
        return
    print(f"  you [{engine} {t_asr:.2f}s]: {said}")

    if echo:
        reply, t_llm = said, 0.0
    else:
        history.append({"role": "user", "content": said})
        t1 = time.monotonic()
        reply = llm_reply(history)
        t_llm = time.monotonic() - t1
        history.append({"role": "assistant", "content": reply})
    print(f"  bot [{t_llm:.2f}s]: {reply}")

    t2 = time.monotonic()
    ttfb, spoken = play_pcm_stream(fish_tts_stream(reply, voice, speed))
    # Latency = mic-stop to first audible word. Playback time is excluded on
    # purpose: it scales with reply length, not with pipeline speed.
    print(f"  tts ttfa {ttfb:.2f}s | spoke {spoken:.1f}s of audio "
          f"| latency to first word {(t2 - t0) + ttfb:.2f}s")


def cmd_chat(args) -> None:
    voice = args.voice or FISH_VOICE_ID
    print(f"Fish Audio S2S demo - model={FISH_MODEL} voice={voice or 'default'}"
          f"{' [echo mode, no LLM]' if args.echo else ''}")
    history: list[dict] = []
    while True:
        audio = record_push_to_talk()
        if audio is None:
            print("bye")
            return
        try:
            _turn(audio, history, args.echo, voice, args.speed, args.stt)
        except requests.HTTPError as e:
            print(f"  http error: {e}")


def cmd_once(args) -> None:
    with open(args.file, "rb") as f:
        audio = f.read()
    _turn(audio, [], args.echo, args.voice or FISH_VOICE_ID, args.speed, args.stt)


def main() -> None:
    # Shared flags, attached to each subcommand so they can go after it:
    #   ... say "hi" --voice X   (rather than only  ... --voice X say "hi")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--voice", help="reference_id of a Fish voice model")
    common.add_argument("--speed", type=float, default=1.0, help="prosody speed 0.5-2.0")
    common.add_argument("--echo", action="store_true",
                        help="skip the LLM, speak back the transcript")
    common.add_argument("--stt", choices=("auto", "fish", "deepgram"), default="auto",
                        help="speech-to-text engine; auto tries Fish, falls back "
                             "to Deepgram when Fish ASR has no credit")

    p = argparse.ArgumentParser(description="Fish Audio speech-to-speech demo")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("voices", parents=[common], help="search the voice library")
    v.add_argument("query", nargs="?", help="e.g. british, indian, narrator")
    v.add_argument("--limit", type=int, default=20)
    v.set_defaults(func=cmd_voices)

    s = sub.add_parser("say", parents=[common], help="one-shot TTS")
    s.add_argument("text", nargs="+")
    s.add_argument("--out", help="also save a wav here")
    s.set_defaults(func=cmd_say)

    c = sub.add_parser("chat", parents=[common],
                       help="push-to-talk speech-to-speech loop")
    c.set_defaults(func=cmd_chat)

    o = sub.add_parser("once", parents=[common], help="one turn from an audio file")
    o.add_argument("file")
    o.set_defaults(func=cmd_once)

    args = p.parse_args()
    fish_key()  # fail fast on a missing key rather than mid-turn
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")


if __name__ == "__main__":
    main()
