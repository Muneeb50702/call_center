"""
Nexus — Public demo router

Backs the client-facing pitch page at /demo. One endpoint: mint a LiveKit token
and dispatch a sales agent into a fresh room.

This is the only unauthenticated, agent-spawning endpoint in the system, which
makes it the only one that costs real money when abused — every session starts a
worker and burns STT/LLM/TTS credits for its lifetime. So it is rate limited per
IP, capped globally, and the room carries a hard duration cap.

The voice catalog is deliberately NOT served here. The agent publishes its own
catalog over the room data channel on connect, so there is exactly one source of
truth (nexus_agent/tts/registry.py) rather than a copy in the backend that drifts
the first time someone adds a voice.
"""

import asyncio
import os
import time
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger()

router = APIRouter(prefix="/demo", tags=["demo"])

# ── Abuse limits ──
# Generous enough that a client clicking around never notices, tight enough that
# a scripted loop cannot run up a bill.
MAX_SESSIONS_PER_IP_PER_HOUR = 12
MAX_CONCURRENT_DEMO_SESSIONS = 8
# LiveKit closes the room this long after it empties, which also bounds a session
# left open in a forgotten tab.
ROOM_EMPTY_TIMEOUT_SECONDS = 30
ROOM_MAX_DURATION_SECONDS = 15 * 60

DEMO_TENANT_ID = os.getenv("DEMO_TENANT_ID", "lumenia")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")

_RATE_KEY = "nexus:demo:rate:{ip}"
_ACTIVE_KEY = "nexus:demo:active"

# Strong references to in-flight agent dispatches. asyncio only holds weak
# references to tasks, so without this a dispatch can be garbage collected
# mid-flight and the agent silently never joins.
_pending_dispatches: set = set()


class DemoSessionRequest(BaseModel):
    voice_id: str = Field(default="", description="Voice to open with; agent default if empty")
    prospect_name: str = Field(default="", max_length=80, description="Name the agent greets")
    tenant_id: str = Field(default="", max_length=64, description="Knowledge base to load")


class DemoSessionResponse(BaseModel):
    url: str
    token: str
    room: str
    identity: str
    tenant_id: str
    expires_in: int


def _client_ip(request: Request) -> str:
    # Behind nginx, so trust the first hop of X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _redis():
    import redis.asyncio as aioredis
    return aioredis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
    )


async def _enforce_limits(ip: str) -> None:
    """Rate limit per IP and cap total concurrent demos.

    Fails open: if Redis is down the demo still works. An unmetered demo is a
    smaller problem than a demo that will not start in front of a client.
    """
    try:
        redis = await _redis()
    except Exception as e:
        logger.warning("demo_rate_limit_unavailable", error=str(e))
        return

    try:
        key = _RATE_KEY.format(ip=ip)
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 3600)
        if count > MAX_SESSIONS_PER_IP_PER_HOUR:
            logger.warning("demo_rate_limited", ip=ip, count=count)
            raise HTTPException(
                status_code=429,
                detail="Too many demo sessions from this address. Try again in an hour.",
            )

        active = await redis.scard(_ACTIVE_KEY)
        if active >= MAX_CONCURRENT_DEMO_SESSIONS:
            raise HTTPException(
                status_code=503,
                detail="All demo lines are busy right now. Please try again in a minute.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("demo_rate_limit_check_failed", error=str(e))
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass


@router.post("/session", response_model=DemoSessionResponse)
async def create_demo_session(payload: DemoSessionRequest, request: Request):
    """Create a browser voice session against the sales agent.

    Mints a room-scoped publish token and dispatches an agent into that room with
    the persona, tenant knowledge base, and opening voice in its job metadata.
    """
    if not LIVEKIT_URL:
        raise HTTPException(status_code=503, detail="LiveKit is not configured on this server.")

    ip = _client_ip(request)
    await _enforce_limits(ip)

    room_name = f"demo-{uuid.uuid4().hex[:12]}"
    identity = f"visitor-{uuid.uuid4().hex[:8]}"
    tenant_id = payload.tenant_id or DEMO_TENANT_ID

    try:
        from livekit import api

        from services.livekit_control import (
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET,
            dispatch_agent,
        )

        # Dispatch the agent WITHOUT blocking the token response.
        #
        # Awaiting it here cost ~2-3s (a LiveKit API round trip) before the
        # browser was even handed a token, so agent-startup and browser-connect
        # ran strictly one after the other. Firing it as a task lets them overlap:
        # the browser starts joining the room while the worker is still being
        # assigned, which is roughly a 2s saving on every session.
        #
        # Safe because the room is created by whoever arrives first — the agent
        # joining an empty room and the visitor joining an agentless room are both
        # normal transient states that resolve when the other side lands.
        dispatch_task = asyncio.create_task(
            dispatch_agent(
                room_name=room_name,
                metadata={
                    "tenant_id": tenant_id,
                    "agent_profile": "sales",
                    "direction": "web_demo",
                    "voice_id": payload.voice_id,
                    "prospect_name": payload.prospect_name,
                },
            )
        )
        _pending_dispatches.add(dispatch_task)
        dispatch_task.add_done_callback(_pending_dispatches.discard)

        def _log_dispatch(task):
            if not task.cancelled() and task.exception():
                # The visitor will sit in a silent room; surface it loudly here
                # since there is no longer an exception path to the HTTP response.
                logger.error(
                    "demo_agent_dispatch_failed",
                    room=room_name,
                    error=str(task.exception())[:200],
                )

        dispatch_task.add_done_callback(_log_dispatch)

        token = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(identity)
            .with_name(payload.prospect_name or "Guest")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,       # the visitor's microphone
                    can_subscribe=True,     # the agent's voice
                    can_publish_data=True,  # the voice-switch control channel
                )
            )
            .with_ttl(__import__("datetime").timedelta(seconds=ROOM_MAX_DURATION_SECONDS))
            .to_jwt()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("demo_session_failed", error=str(e), room=room_name)
        raise HTTPException(status_code=502, detail=f"Could not start a demo session: {e}")

    try:
        redis = await _redis()
        await redis.sadd(_ACTIVE_KEY, room_name)
        # Self-expiring: a crashed agent cannot permanently consume a slot.
        await redis.expire(_ACTIVE_KEY, ROOM_MAX_DURATION_SECONDS)
        await redis.aclose()
    except Exception:
        pass

    logger.info("demo_session_created", room=room_name, tenant_id=tenant_id, ip=ip,
                voice=payload.voice_id or "default")

    return DemoSessionResponse(
        url=LIVEKIT_URL,
        token=token,
        room=room_name,
        identity=identity,
        tenant_id=tenant_id,
        expires_in=ROOM_MAX_DURATION_SECONDS,
    )


@router.get("/health")
async def demo_health():
    """Whether the demo can actually start a session — checked by the page before
    it offers a microphone button, so a misconfigured server surfaces as a clear
    message rather than a hang."""
    return {
        "ready": bool(LIVEKIT_URL and os.getenv("LIVEKIT_API_KEY")),
        "livekit_configured": bool(LIVEKIT_URL),
        "tenant_id": DEMO_TENANT_ID,
        "timestamp": time.time(),
    }
