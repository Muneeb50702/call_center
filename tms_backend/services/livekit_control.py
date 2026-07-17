"""
Nexus Dispatch — LiveKit server-side control helper (backend)

Thin wrapper around the LiveKit server API for backend-initiated actions:
- mint room access tokens (supervisor listen / takeover — Phase 1 console),
- place outbound calls + dispatch the agent (Phase 1 dialer),
- start/stop egress recording.

Lazy imports so the backend still boots if ``livekit-api`` isn't installed in a
given environment; callers only hit an ImportError when they actually use it.
"""

import json
import os

import structlog

logger = structlog.get_logger()

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")


def _client():
    from livekit import api  # lazy
    return api.LiveKitAPI(
        url=LIVEKIT_URL or None,
        api_key=LIVEKIT_API_KEY or None,
        api_secret=LIVEKIT_API_SECRET or None,
    )


def mint_room_token(
    room_name: str,
    identity: str,
    *,
    can_publish: bool = False,
    can_subscribe: bool = True,
    name: str = "",
) -> str:
    """Mint a LiveKit access token for a supervisor to listen (subscribe-only) or
    take over (can_publish=True) a live call room."""
    from livekit import api

    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=can_publish,
        can_subscribe=can_subscribe,
        can_publish_data=True,
    )
    return (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(name or identity)
        .with_grants(grants)
        .to_jwt()
    )


async def dispatch_agent(
    *,
    room_name: str,
    metadata: dict,
    agent_name: str = "nexus-agent",
) -> dict:
    """Dispatch an agent worker into a room without dialing anyone.

    This is the web path: the browser joins the room itself, so there is no SIP
    participant to create. `metadata` reaches the worker as `ctx.job.metadata` and
    is how the caller selects persona, tenant knowledge base, and opening voice.
    """
    from livekit import api

    lkapi = _client()
    try:
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata=json.dumps(metadata),
            )
        )
        logger.info("Agent dispatched", room=room_name, agent=agent_name,
                    profile=metadata.get("agent_profile"))
        return {"room": room_name, "agent": agent_name}
    finally:
        await lkapi.aclose()


async def place_outbound_call(
    *,
    sip_trunk_id: str,
    to_number: str,
    room_name: str,
    agent_name: str = "nexus-agent",
    tenant_id: str = "",
    campaign_id: str = "",
    participant_identity: str = "phone_user",
    wait_until_answered: bool = True,
) -> dict:
    """Dispatch the agent into a room and dial the callee into it."""
    from livekit import api

    lkapi = _client()
    try:
        metadata = json.dumps({
            "direction": "outbound",
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
        })
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(agent_name=agent_name, room=room_name, metadata=metadata)
        )
        await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=sip_trunk_id,
                sip_call_to=to_number,
                room_name=room_name,
                participant_identity=participant_identity,
                wait_until_answered=wait_until_answered,
                krisp_enabled=True,
            )
        )
        logger.info("Outbound call placed", to=to_number, room=room_name)
        return {"room": room_name, "to": to_number}
    finally:
        await lkapi.aclose()
