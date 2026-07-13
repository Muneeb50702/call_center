"""
Nexus Dispatch — Call Control Tools (LiveKit Agents 1.x)

Production call-lifecycle actions:
- Warm transfer to a senior dispatcher (real SIP REFER via the LiveKit server API)
- Graceful call termination (real room teardown)
- Brief hold

Transfer flow: the mode prompts instruct the agent to speak the hand-off line
("Let me connect you with one of our senior dispatchers…") and THEN call the
transfer tool. This function waits briefly for that line to finish, performs a
real SIP REFER to the tenant's human_transfer_number, and tells the model to stay
silent (the caller has left the room).
"""

import asyncio
import structlog

from livekit import api
from livekit.agents import RunContext, get_job_context

logger = structlog.get_logger()

# Seconds to let the agent's spoken hand-off / wrap-up line play before we act.
_ANNOUNCE_GRACE_S = 1.5


def _find_sip_participant(room):
    """Return the identity of the SIP (phone) participant, or None for WebRTC."""
    try:
        for p in room.remote_participants.values():
            if p.attributes.get("sip.callID"):
                return p.identity
    except Exception:
        pass
    return None


async def end_call_session(ctx: RunContext, summary: str = "") -> str:
    """Gracefully end the call by tearing down the LiveKit room (disconnects the
    SIP leg). Falls back to closing the session if room deletion is unavailable."""
    logger.info("Call session ending", summary=summary)
    try:
        job = get_job_context()
        await asyncio.sleep(1.0)  # let the wrap-up line finish
        try:
            res = job.delete_room()
            if res is not None and hasattr(res, "__await__"):
                await res
        except Exception as e:
            logger.warning("delete_room failed, closing session", error=str(e))
            try:
                await ctx.session.aclose()
            except Exception:
                pass
    except Exception as e:
        logger.exception("Error ending call session", error=str(e))
    return f"Call ended. {summary}".strip()


async def transfer_to_human_dispatcher(
    ctx: RunContext,
    reason: str,
    transfer_number: str = "",
) -> str:
    """Warm-transfer the caller to a senior dispatcher via a real SIP REFER."""
    fsm = ctx.session.userdata.get("state_machine")
    tenant = ctx.session.userdata.get("tenant_config", {}) or {}
    target = transfer_number or tenant.get("human_transfer_number", "")

    if fsm is not None:
        fsm.context.transferred_to_human = True
        fsm.context.transfer_reason = reason
        fsm.context.exception_score = max(fsm.context.exception_score, 0.8)

    logger.warning(
        "Warm transfer initiated",
        call_id=(fsm.context.call_id if fsm else "unknown"),
        reason=reason,
        target=target,
    )

    if not target:
        return (
            "SYSTEM: No transfer number is configured. Tell the caller: "
            "'Let me get one of our senior team members for you.' and keep them on the line."
        )

    try:
        job = get_job_context()
        room = job.room
        sip_identity = _find_sip_participant(room)

        if sip_identity is None:
            # Not a phone call (e.g. local WebRTC test) — nothing to REFER.
            return (
                "SYSTEM: Tell the caller a senior dispatcher will be right with them, "
                "then wait. (No SIP leg to transfer in this session.)"
            )

        # Let the agent's spoken hand-off line play before we REFER the leg away.
        await asyncio.sleep(_ANNOUNCE_GRACE_S)

        transfer_to = target if target.startswith(("tel:", "sip:")) else f"tel:{target}"
        await job.api.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                room_name=room.name,
                participant_identity=sip_identity,
                transfer_to=transfer_to,
                play_dialtone=False,
            )
        )
        logger.info("SIP transfer executed", target=transfer_to, identity=sip_identity)
        return (
            "SYSTEM: The caller has been connected to a senior dispatcher. "
            "The transfer is complete — do not say anything else."
        )
    except Exception as e:
        logger.error("SIP transfer failed", error=str(e), target=target)
        return (
            "SYSTEM: The transfer didn't go through. Tell the caller: "
            "'Let me get one of our senior team members for you.' and stay on the line."
        )


async def hold_caller(ctx: RunContext, message: str = "") -> str:
    """Place the caller on a brief hold while performing a long operation."""
    hold_msg = message or "One moment please while I look that up for you."
    logger.info("Caller placed on hold", message=hold_msg)
    return hold_msg
