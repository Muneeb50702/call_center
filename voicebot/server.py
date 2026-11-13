#!/usr/bin/env python3
"""
Web UI for the Fish Audio voice bot.

    .venv-dev/bin/python voicebot/server.py
    # then open http://127.0.0.1:8080

Pipeline per turn:
    browser mic (webm/opus) -> Deepgram STT -> gpt-4o-mini -> Fish TTS -> <audio>

The UI asks in two steps -- POST /api/ask returns the text immediately, then
POST /api/speak fetches the audio -- so the reply appears on screen while the
voice is still being synthesized.
"""

from __future__ import annotations

import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn  # noqa: E402
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import core  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
SAMPLES = os.path.join(HERE, "samples")

MAX_TURNS = 24  # trailing messages kept per session (12 exchanges)

app = FastAPI(title="Fish Audio voice bot")
app.mount("/samples", StaticFiles(directory=SAMPLES), name="samples")

# Demo-scale session store: process memory, dropped on restart.
SESSIONS: dict[str, list[dict]] = {}


def history_for(sid: str) -> list[dict]:
    return SESSIONS.setdefault(sid, [])


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/config")
def config() -> JSONResponse:
    samples = []
    manifest = os.path.join(SAMPLES, "manifest.json")
    if os.path.exists(manifest):
        import json
        try:
            with open(manifest) as f:
                samples = json.load(f).get("samples", [])
        except (OSError, ValueError):
            samples = []
    return JSONResponse({
        "tts_model": core.FISH_MODEL,
        "llm_model": core.OPENAI_MODEL,
        "stt_model": "deepgram nova-3",
        "missing_keys": core.missing_keys(),
        "samples": samples,
        "session": uuid.uuid4().hex,
    })


@app.get("/api/voices")
def voices(q: str = "", limit: int = 20) -> JSONResponse:
    try:
        return JSONResponse({"voices": core.list_voices(q or None, limit)})
    except Exception as e:
        raise HTTPException(502, f"voice search failed: {e}")


@app.post("/api/ask")
async def ask(
    session: str = Form(...),
    text: str = Form(""),
    audio: UploadFile | None = File(None),
) -> JSONResponse:
    """Audio or typed text in, reply text out. No synthesis here -- that's /speak."""
    timings: dict[str, float] = {}
    said = text.strip()

    if audio is not None:
        raw = await audio.read()
        if not raw:
            raise HTTPException(400, "empty recording")
        t0 = time.monotonic()
        try:
            said, _ = core.stt(raw, audio.content_type or "audio/webm")
        except core.ConfigError as e:
            raise HTTPException(502, str(e))
        timings["stt"] = round(time.monotonic() - t0, 2)

    if not said:
        return JSONResponse({"transcript": "", "reply": "", "timings": timings,
                             "note": "nothing heard - try again, a bit louder"})

    hist = history_for(session)
    hist.append({"role": "user", "content": said})
    t1 = time.monotonic()
    try:
        reply = core.llm(hist[-MAX_TURNS:])
    except core.ConfigError as e:
        hist.pop()
        raise HTTPException(502, str(e))
    timings["llm"] = round(time.monotonic() - t1, 2)
    hist.append({"role": "assistant", "content": reply})
    del hist[:-MAX_TURNS]

    return JSONResponse({"transcript": said, "reply": reply, "timings": timings})


@app.post("/api/speak")
def speak(payload: dict = Body(...)) -> Response:
    """Text -> WAV.

    Buffers the full clip and writes a correct WAV header rather than relaying
    Fish's chunked output: Fish's own format:"wav" declares a placeholder length
    (a 1.9s clip decodes as ~48,695s) which browsers mis-handle.
    """
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "no text")
    voice = payload.get("voice_id") or None
    try:
        speed = float(payload.get("speed") or 1.0)
    except (TypeError, ValueError):
        speed = 1.0

    t0 = time.monotonic()
    try:
        pcm = core.tts_pcm(text, voice, speed)
    except core.ConfigError as e:
        raise HTTPException(502, str(e))
    return Response(
        content=core.wrap_wav(pcm),
        media_type="audio/wav",
        headers={
            "X-TTS-Seconds": f"{core.pcm_seconds(pcm):.2f}",
            "X-TTS-Elapsed": f"{time.monotonic() - t0:.2f}",
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/reset")
def reset(payload: dict = Body(...)) -> JSONResponse:
    SESSIONS.pop(payload.get("session", ""), None)
    return JSONResponse({"ok": True})


def main() -> None:
    missing = core.missing_keys()
    if missing:
        print(f"warning: missing {', '.join(missing)} - "
              f"those hops will error until set in .env")
    # Deliberately not PORT: the repo .env sets PORT=8000 for the TMS backend,
    # and core.load_dotenv pulls it into this process too.
    port = int(os.getenv("VOICEBOT_PORT", "8080"))
    print(f"tts={core.FISH_MODEL}  llm={core.OPENAI_MODEL}  stt=deepgram nova-3")
    print(f"open http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
