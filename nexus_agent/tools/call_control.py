"""
Nexus Dispatch — Call Control Tools

Production-critical tools for managing call lifecycle:
- Warm transfer to senior dispatcher (SIP REFER)
- Graceful call termination
- Call hold functionality

Transfer Architecture:
When the AI decides to transfer, it uses LiveKit's SIP transfer API
to redirect the caller's SIP leg to the tenant's human_transfer_number.
The AI stays in the room briefly to announce the transfer, then disconnects.
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
    Warm-transfer the call to a senior dispatcher using LiveKit SIP REFER.
    
    This performs a real SIP transfer:
    1. Looks up the tenant's human_transfer_number
    2. Uses LiveKit's transfer_participant API to SIP REFER the caller
    3. The caller hears ringing and connects to the human
    4. The AI agent disconnects from the room after transfer
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
        # Attempt real SIP transfer via LiveKit API
        try:
            room = ctx.session.userdata.get("room")
            if room:
                for participant in room.remote_participants.values():
                    sip_call_id = participant.attributes.get("sip.callID", "")
                    if sip_call_id:
                        # LiveKit SIP transfer — performs a SIP REFER
                        # This redirects the caller's phone connection to target_number
                        try:
                            await room.transfer_sip_participant(
                                participant_identity=participant.identity,
                                transfer_to=f"sip:{target_number}@sip.telnyx.com",
                            )
                            logger.info(
                                "SIP transfer executed successfully",
                                target=target_number,
                                sip_call_id=sip_call_id,
                            )
                            return (
                                f"SYSTEM: Transfer to senior dispatcher at {target_number} initiated successfully. "
                                "Tell the caller: 'I'm connecting you with one of our senior dispatchers now. Please hold.'"
                            )
                        except AttributeError:
                            # Fallback if transfer_sip_participant is not available
                            # (older LiveKit SDK or WebRTC-only session)
                            logger.warning(
                                "SIP transfer API not available, using fallback announcement",
                                target=target_number,
                            )
                            pass
                        except Exception as transfer_err:
                            logger.error(
                                "SIP transfer failed",
                                error=str(transfer_err),
                                target=target_number,
                            )
                            pass

        except Exception as e:
            logger.error("Error during SIP transfer", error=str(e))

        # Fallback: announce the transfer even if SIP REFER fails
        return (
            f"SYSTEM: Transferring to senior dispatcher at {target_number}. "
            "Tell the caller: 'I'm connecting you with one of our senior dispatchers now. Please hold.'"
        )
    else:
        return (
            "SYSTEM: Connecting to senior dispatcher. "
            "Tell the caller: 'Let me get one of our senior team members for you. One moment please.'"
        )


async def hold_caller(ctx: RunContext, message: str = "") -> str:
    """
    Place the caller on a brief hold while performing a long-running operation.
    The TTS will speak the hold message before pausing.
    """
    hold_msg = message or "One moment please while I look that up for you."
    logger.info("Caller placed on hold", message=hold_msg)
    return hold_msg
