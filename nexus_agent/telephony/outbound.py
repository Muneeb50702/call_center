"""
Nexus Dispatch — Outbound SIP Dialing (LiveKit Agents 1.x)

Phase 0 primitive: dispatch the nexus-agent into a room and dial a callee into it
over a LiveKit SIP outbound trunk (US DID → STIR/SHAKEN A-attestation). Proves the
outbound path end-to-end before Phase 1 adds campaigns + compliance.

⚠️ Compliance: cold AI-voice calls to non-consented US cell phones are restricted
under the FCC's Feb-2024 TCPA ruling. Use this ONLY for consented contacts (your
own drivers/carriers) or test numbers. Phase 1 puts the consent ledger + DNC +
8am–9pm calling-window checks in front of every dial (services/compliance.py).
"""

import json
import structlog

logger = structlog.get_logger()


async def place_outbound_call(
    lkapi,
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
    """Dispatch the agent into ``room_name`` and dial ``to_number`` into it.

    Args:
        lkapi: an initialized ``livekit.api.LiveKitAPI`` client.
    """
    from livekit import api

    metadata = json.dumps({
        "direction": "outbound",
        "tenant_id": tenant_id,
        "campaign_id": campaign_id,
    })

    # 1) Ensure the agent is dispatched into the room.
    await lkapi.agent_dispatch.create_dispatch(
        api.CreateAgentDispatchRequest(agent_name=agent_name, room=room_name, metadata=metadata)
    )

    # 2) Dial the callee into the same room.
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
    logger.info("Outbound call placed", to=to_number, room=room_name, trunk=sip_trunk_id)
    return {"room": room_name, "to": to_number, "participant_identity": participant_identity}
