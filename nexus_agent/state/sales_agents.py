"""
Nexus — Outbound SDR agents

The sales persona: five Agent subclasses over the SALES_OPENING → DISCOVERY →
PITCH → OBJECTION → CLOSING → WRAP_UP graph, sharing the dispatch persona's
NexusAgent base so they inherit the pre-TTS grounding verifier, the STT
low-confidence signal, and the per-turn fact reset for free.

Every agent here carries `search_knowledge_base`, not just the pitch agent. A
prospect asks "wait, what do you actually do?" during the close, not on cue
during the pitch — an agent that can only retrieve in one state has to either
refuse or invent, and it will invent.

Lead capture is incremental rather than a form at the end. Cold calls end
abruptly; a lead recorded only at WRAP_UP is a lead lost every time someone hangs
up mid-sentence.
"""

from __future__ import annotations

import re

import structlog
from livekit.agents import RunContext, function_tool

from llm.sales_prompts import (
    get_closing_prompt,
    get_discovery_prompt,
    get_objection_prompt,
    get_pitch_prompt,
    get_sales_opening_prompt,
    get_sales_wrap_up_prompt,
)
from state.agents import NexusAgent
from state.machine import CallState, CallStateMachine
from tools.call_control import end_call_session

logger = structlog.get_logger()

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def _fsm(ctx: RunContext) -> CallStateMachine:
    return ctx.session.userdata["state_machine"]


def _kb(ctx: RunContext):
    return ctx.session.userdata.get("kb_tools")


def _persona(ctx: RunContext) -> dict:
    """The persona kwargs every sales agent is constructed with.

    Passed on every state handoff, so the campaign (who we're calling and why)
    survives the whole call instead of being re-improvised per state.
    """
    cfg = ctx.session.userdata.get("tenant_config", {})
    return {
        "company_name": cfg.get("company_name", "our company"),
        "agent_name": cfg.get("agent_name", "William"),
        "disclosure_mode": cfg.get("disclosure_mode", "if_asked"),
        "campaign_id": cfg.get("campaign_id", ""),
    }


class SalesAgent(NexusAgent):
    """Base for every sales state. Carries retrieval and lead capture, which every
    state needs, and leaves state movement to the subclasses."""

    # Sales is the persona where an invented CLIENT NAME is fatal: saying "we did
    # this for Maersk" to the founder of the company you are representing is
    # instantly recognisable as false to the one person who knows the real client
    # list. Numbers alone are not enough of a guard here — a fabricated logo is
    # worse than a fabricated figure. A false positive only costs a hedge.
    verify_entities: bool = True

    @function_tool()
    async def search_knowledge_base(self, ctx: RunContext, query: str) -> str:
        """Look up verified facts about the company — services, past projects, clients,
        process, pricing, location, track record. You MUST call this before stating ANY
        fact about the company. Search for what the caller actually asked about, phrased
        as a natural question. Returns NO_RESULTS if the company has not published it, in
        which case say you don't have it rather than guessing."""
        fsm = _fsm(ctx)
        kb = _kb(ctx)
        if kb is None:
            return (
                "NO_RESULTS: knowledge base unavailable. Tell the caller you don't have "
                "that to hand and offer to have someone follow up."
            )

        fsm.record_tool_invocation("search_knowledge_base")
        result = kb.search(query)

        # Mirror retrieval telemetry onto the call context so the demo HUD and the
        # final call record can show what the knowledge base actually did.
        fsm.context.kb_queries = kb.stats["queries"]
        fsm.context.kb_misses = kb.stats["misses"]
        fsm.context.kb_last_latency_ms = round(kb.last_latency_ms, 2)
        fsm.context.kb_last_sources = [h.to_dict() for h in kb.last_hits]

        # A miss is a quality signal worth a supervisor's attention: it means a
        # prospect asked something the company's own material does not answer.
        if not kb.last_hits:
            fsm.context.exception_score = max(fsm.context.exception_score, 0.3)
        return result

    @function_tool()
    async def capture_lead(
        self,
        ctx: RunContext,
        name: str = "",
        company: str = "",
        role: str = "",
        email: str = "",
        problem: str = "",
        timeline: str = "",
        budget: str = "",
    ) -> str:
        """Record what you've learned about the prospect. Call this as soon as you learn
        anything — do not wait until the end of the call. Pass only the fields you
        actually learned; omit the rest. Safe to call repeatedly as you learn more."""
        fsm = _fsm(ctx)
        fsm.record_tool_invocation("capture_lead")
        c = fsm.context

        # Only overwrite with non-empty values: a later call that omits a field
        # must not wipe what an earlier one captured.
        for field_name, value in (
            ("lead_name", name), ("lead_company", company), ("lead_role", role),
            ("lead_problem", problem), ("lead_timeline", timeline), ("lead_budget", budget),
        ):
            if value.strip():
                setattr(c, field_name, value.strip())

        warning = ""
        if email.strip():
            candidate = email.strip().replace(" ", "")
            if _EMAIL.match(candidate):
                c.lead_email = candidate
            else:
                # Emails arrive via speech-to-text and are mangled constantly.
                # Storing a malformed one silently means the follow-up never
                # lands, so make the agent read it back instead.
                warning = (
                    f" WARNING: '{email}' is not a valid email address — you likely "
                    "misheard it. Ask them to spell it out, then call this tool again."
                )
                logger.info("lead_email_rejected", call_id=c.call_id, raw=email[:60])

        c.lead_qualified = bool(c.lead_problem and (c.lead_company or c.lead_name))

        logger.info(
            "lead_captured",
            call_id=c.call_id,
            name=c.lead_name,
            company=c.lead_company,
            has_email=bool(c.lead_email),
            qualified=c.lead_qualified,
        )
        return f"Lead updated. Qualified: {c.lead_qualified}.{warning}"

    @function_tool()
    async def confirm_ai_disclosure(self, ctx: RunContext) -> str:
        """Call this immediately after you tell the caller you are an AI, whenever they
        ask whether you're a bot, an AI, a recording, or a real person."""
        fsm = _fsm(ctx)
        fsm.context.ai_disclosed = True
        fsm.record_tool_invocation("confirm_ai_disclosure")
        logger.info("ai_disclosed", call_id=fsm.context.call_id)
        return "Disclosure recorded. Continue naturally — do not dwell on it."

    @function_tool()
    async def end_conversation(self, ctx: RunContext, reason: str = "") -> str:
        """End the call. Use when the prospect isn't interested, asks to be removed, a
        next step is agreed, or the conversation has naturally finished."""
        fsm = _fsm(ctx)
        fsm.record_tool_invocation("end_conversation")
        if fsm.current_state != CallState.WRAP_UP:
            fsm.transition(CallState.WRAP_UP)
        logger.info("sales_call_ending", call_id=fsm.context.call_id, reason=reason,
                    qualified=fsm.context.lead_qualified, booked=fsm.context.meeting_booked)
        return await end_call_session(ctx, reason)

    # ── Shared state movement ──

    def _move(self, ctx: RunContext, target: CallState, agent_cls, note: str) -> str:
        fsm = _fsm(ctx)
        if not fsm.transition(target):
            # Not an error worth surfacing to the caller — the agent should just
            # keep talking from where it is.
            return f"Already in the right place. Continue the conversation."
        ctx.session.update_agent(agent_cls(**_persona(ctx)))
        return note


class SalesOpeningAgent(SalesAgent):
    """Earns the next thirty seconds, or gets off the call gracefully."""

    def __init__(self, company_name: str = "Lumenia", agent_name: str = "William",
                 disclosure_mode: str = "if_asked", campaign_id: str = ""):
        super().__init__(instructions=get_sales_opening_prompt(company_name, agent_name, disclosure_mode, campaign_id))

    @function_tool()
    async def advance_to_discovery(self, ctx: RunContext) -> str:
        """Call when the prospect gives you permission to continue or asks a question."""
        return self._move(ctx, CallState.DISCOVERY, DiscoveryAgent,
                          "In discovery. Ask about their business — one question, then listen.")

    @function_tool()
    async def advance_to_pitch(self, ctx: RunContext) -> str:
        """Call when the prospect immediately asks what the company does or can build."""
        return self._move(ctx, CallState.PITCH, PitchAgent,
                          "In pitch. Search the knowledge base before you claim anything.")


class DiscoveryAgent(SalesAgent):
    """Qualifies: is there a real problem worth solving here?"""

    def __init__(self, company_name: str = "Lumenia", agent_name: str = "William",
                 disclosure_mode: str = "if_asked", campaign_id: str = ""):
        super().__init__(instructions=get_discovery_prompt(company_name, agent_name, disclosure_mode, campaign_id))

    @function_tool()
    async def advance_to_pitch(self, ctx: RunContext) -> str:
        """Call once you understand a specific problem the company could solve."""
        return self._move(ctx, CallState.PITCH, PitchAgent,
                          "In pitch. Search for a real project matching their problem, then connect it.")

    @function_tool()
    async def advance_to_objection(self, ctx: RunContext, objection: str = "") -> str:
        """Call when the prospect pushes back, hesitates, or raises a concern."""
        if objection:
            _fsm(ctx).context.objections_raised.append(objection)
        return self._move(ctx, CallState.OBJECTION, ObjectionAgent,
                          "Handling the objection. Acknowledge it first — do not argue.")

    @function_tool()
    async def advance_to_closing(self, ctx: RunContext) -> str:
        """Call when the prospect wants to book time or speak to someone."""
        return self._move(ctx, CallState.CLOSING, ClosingAgent,
                          "Closing. Get a specific day and a confirmed email address.")


class PitchAgent(SalesAgent):
    """Connects their problem to something the company has verifiably built."""

    def __init__(self, company_name: str = "Lumenia", agent_name: str = "William",
                 disclosure_mode: str = "if_asked", campaign_id: str = ""):
        super().__init__(instructions=get_pitch_prompt(company_name, agent_name, disclosure_mode, campaign_id))

    @function_tool()
    async def advance_to_discovery(self, ctx: RunContext) -> str:
        """Call when the prospect raises a new problem worth understanding."""
        return self._move(ctx, CallState.DISCOVERY, DiscoveryAgent,
                          "Back in discovery. Understand the new problem before pitching again.")

    @function_tool()
    async def advance_to_objection(self, ctx: RunContext, objection: str = "") -> str:
        """Call when the prospect objects or hesitates."""
        if objection:
            _fsm(ctx).context.objections_raised.append(objection)
        return self._move(ctx, CallState.OBJECTION, ObjectionAgent,
                          "Handling the objection. Acknowledge it first.")

    @function_tool()
    async def advance_to_closing(self, ctx: RunContext) -> str:
        """Call when the prospect shows real interest in a next step."""
        return self._move(ctx, CallState.CLOSING, ClosingAgent,
                          "Closing. Get a specific day and a confirmed email address.")


class ObjectionAgent(SalesAgent):
    """Understands the objection rather than beating it."""

    def __init__(self, company_name: str = "Lumenia", agent_name: str = "William",
                 disclosure_mode: str = "if_asked", campaign_id: str = ""):
        super().__init__(instructions=get_objection_prompt(company_name, agent_name, disclosure_mode, campaign_id))

    @function_tool()
    async def advance_to_pitch(self, ctx: RunContext) -> str:
        """Call when the objection needs more context about what the company has built."""
        return self._move(ctx, CallState.PITCH, PitchAgent,
                          "Back in pitch. Search for evidence that speaks to their concern.")

    @function_tool()
    async def advance_to_discovery(self, ctx: RunContext) -> str:
        """Call when the objection reveals a different underlying problem."""
        return self._move(ctx, CallState.DISCOVERY, DiscoveryAgent,
                          "Back in discovery. Understand what's really underneath this.")

    @function_tool()
    async def advance_to_closing(self, ctx: RunContext) -> str:
        """Call once the objection is resolved and the prospect is still interested."""
        return self._move(ctx, CallState.CLOSING, ClosingAgent,
                          "Closing. Get a specific day and a confirmed email address.")


class ClosingAgent(SalesAgent):
    """Books a conversation with a human. Not a deal — a conversation."""

    def __init__(self, company_name: str = "Lumenia", agent_name: str = "William",
                 disclosure_mode: str = "if_asked", campaign_id: str = ""):
        super().__init__(instructions=get_closing_prompt(company_name, agent_name, disclosure_mode, campaign_id))

    @function_tool()
    async def book_meeting(self, ctx: RunContext, preferred_time: str, email: str = "") -> str:
        """Book the follow-up. Provide the day/time the prospect agreed to in their own
        words (e.g. 'Tuesday afternoon'). Only call once you have confirmed their email
        by reading it back to them."""
        fsm = _fsm(ctx)
        fsm.record_tool_invocation("book_meeting")
        c = fsm.context

        if email.strip():
            candidate = email.strip().replace(" ", "")
            if _EMAIL.match(candidate):
                c.lead_email = candidate

        if not c.lead_email:
            # Refuse rather than book a meeting that can never be delivered.
            return (
                "CANNOT BOOK: no valid email on file. Ask them to spell out their email "
                "address, call capture_lead with it, then try booking again."
            )

        c.meeting_booked = True
        c.meeting_slot = preferred_time.strip()
        c.lead_qualified = True
        logger.info("meeting_booked", call_id=c.call_id, slot=c.meeting_slot,
                    company=c.lead_company, email=c.lead_email)
        return (
            f"Meeting request recorded for {c.meeting_slot}, confirmation to {c.lead_email}. "
            "Confirm the day and the email back to them once, briefly, then end the call. "
            "Do not keep selling."
        )

    @function_tool()
    async def advance_to_objection(self, ctx: RunContext, objection: str = "") -> str:
        """Call if a final concern surfaces before they commit."""
        if objection:
            _fsm(ctx).context.objections_raised.append(objection)
        return self._move(ctx, CallState.OBJECTION, ObjectionAgent,
                          "Handling the final objection. Acknowledge it, answer once, ask again.")


class SalesWrapUpAgent(SalesAgent):
    """Terminal. Says goodbye and stops."""

    def __init__(self, company_name: str = "Lumenia", agent_name: str = "William",
                 disclosure_mode: str = "if_asked", campaign_id: str = ""):
        super().__init__(instructions=get_sales_wrap_up_prompt(company_name, agent_name, disclosure_mode, campaign_id))
