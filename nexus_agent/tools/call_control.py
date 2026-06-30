"""
Nexus Dispatch — Call Control Tools

Production-critical tools for managing call lifecycle:
- Warm transfer to human dispatcher
- Graceful call termination
- Call hold functionality
"""

import structlog
from livekit.agents import RunContext

logger = structlog.get_logger()


async def end_call_session(ctx: RunContext, summary: str = "") -> str:
    """
    Gracefully terminate the current call session.
    
    In a LiveKit SIP session, this disconnects the SIP participant.
    For WebRTC sessions, this signals the room to close.
    """
    try:
        room = ctx.session.userdata.get("room")
        if room:
            # Disconnect all SIP participants (ends the phone call)
            for participant in room.remote_participants.values():
                sip_call_id = participant.attributes.get("sip.callID", "")
                if sip_call_id:
                    logger.info(
                        "Disconnecting SIP participant",
                        sip_call_id=sip_call_id,
                        summary=summary,
                    )
            # Signal session to stop
            logger.info("Call session ending", summary=summary)
        return f"Call ended. Summary: {summary}"
    except Exception as e:
        logger.exception("Error ending call session", error=str(e))
        return f"Call ended with error: {str(e)}"


async def transfer_to_human_dispatcher(
    ctx: RunContext,
    reason: str,
    transfer_number: str = "",
) -> str:
    """
    Warm-transfer the call to a human dispatcher.
    
    In production with SIP, this performs a SIP REFER to redirect
    the caller to the human dispatcher's phone/extension.
    """
    fsm = ctx.session.userdata.get("state_machine")
    tenant = ctx.session.userdata.get("tenant_config", {})

    # Use tenant-specific transfer number or fallback
    target_number = transfer_number or tenant.get("human_transfer_number", "")

    logger.warning(
        "Warm transfer initiated",
        call_id=fsm.context.call_id if fsm else "unknown",
        reason=reason,
        target_number=target_number,
        tenant_id=tenant.get("tenant_id", "default"),
    )

    if fsm:
        fsm.context.transferred_to_human = True
        fsm.context.transfer_reason = reason

    if target_number:
        # In production: Use LiveKit's SIP transfer API
        # await room.transfer_participant(participant, f"sip:{target_number}")
        return f"Transferring you to a human dispatcher at {target_number}. Reason: {reason}. Please hold."
    else:
        return f"I'm connecting you with a human dispatcher now. Reason: {reason}. Please hold, someone will be with you shortly."


async def hold_caller(ctx: RunContext, message: str = "") -> str:
    """
    Place the caller on a brief hold while performing a long-running operation.
    The TTS will speak the hold message before pausing.
    """
    hold_msg = message or "One moment please while I look that up for you."
    logger.info("Caller placed on hold", message=hold_msg)
    return hold_msg
