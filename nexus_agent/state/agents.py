"""
Nexus Dispatch — Specialized Agent Classes

Each conversation phase has its own Agent subclass with:
- Phase-specific system instructions
- Phase-specific tools (state-gated)
- Transition tools to move to the next phase via session.update_agent()

The agents share call context through session.userdata["state_machine"].
"""

import structlog
from livekit.agents import Agent, function_tool, RunContext

from llm.prompts import (
    get_greeting_prompt,
    get_qualification_prompt,
    get_negotiation_prompt,
    get_booking_prompt,
    get_wrap_up_prompt,
)
from state.machine import CallState, CallStateMachine
from tools.tms_tools import TMSTools
from tools.call_control import end_call_session
from tools.booking_tools import BookingTools

logger = structlog.get_logger()


def _get_fsm(ctx: RunContext) -> CallStateMachine:
    """Helper to retrieve the CallStateMachine from session userdata."""
    return ctx.session.userdata["state_machine"]


def _get_tms(ctx: RunContext) -> TMSTools:
    """Helper to retrieve the TMSTools client from session userdata."""
    return ctx.session.userdata["tms_tools"]


def _get_booking_tools(ctx: RunContext) -> BookingTools:
    """Helper to retrieve the BookingTools client from session userdata."""
    return ctx.session.userdata["booking_tools"]


# =============================================================================
# GREETING AGENT
# =============================================================================

class GreetingAgent(Agent):
    """
    Phase 1: Greet the caller, collect MC number or driver ID.
    Once qualified, transitions to QualificationAgent.
    """

    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(
            instructions=get_greeting_prompt(company_name=tenant_company),
        )

    @function_tool()
    async def transition_to_qualification(
        self,
        ctx: RunContext,
        mc_number: str = "",
        driver_name: str = "",
        equipment_type: str = "",
    ) -> str:
        """
        Call this tool once you have collected the caller's MC number or driver name
        and know what they are looking for. This moves the conversation to the
        qualification phase where you can search for loads.
        """
        fsm = _get_fsm(ctx)
        fsm.context.driver_mc_number = mc_number
        fsm.context.driver_name = driver_name
        fsm.context.driver_equipment = equipment_type

        if fsm.transition(CallState.QUALIFICATION):
            logger.info(
                "Transitioning to QUALIFICATION",
                call_id=fsm.context.call_id,
                mc_number=mc_number,
                driver_name=driver_name,
            )
            tenant = ctx.session.userdata.get("tenant_config", {})
            company = tenant.get("company_name", "Nexus Dispatch")
            await ctx.session.update_agent(QualificationAgent(tenant_company=company))
            return f"Successfully moved to qualification phase. Driver: {driver_name}, MC: {mc_number}, Equipment: {equipment_type}. Now search for matching loads."
        return "Cannot transition to qualification phase right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """
        Transfer the call to a human dispatcher if the caller is confused,
        frustrated, or explicitly requests a human. Provide a reason.
        """
        fsm = _get_fsm(ctx)
        fsm.context.transferred_to_human = True
        fsm.context.transfer_reason = reason
        logger.warning(
            "Call transferred to human",
            call_id=fsm.context.call_id,
            reason=reason,
            state=fsm.current_state.value,
        )
        return f"Call is being transferred to a human dispatcher. Reason: {reason}. Please hold while we connect you."


# =============================================================================
# QUALIFICATION AGENT
# =============================================================================

class QualificationAgent(Agent):
    """
    Phase 2: Search for loads matching the driver's equipment and route preference.
    Uses TMS tools to find available loads and check driver availability.
    """

    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(
            instructions=get_qualification_prompt(company_name=tenant_company),
        )

    @function_tool()
    async def search_loads(
        self,
        ctx: RunContext,
        origin: str = "",
        destination: str = "",
        equipment: str = "",
    ) -> str:
        """Search for available freight loads by origin, destination, or equipment type (e.g. 'Dry Van', 'Reefer', 'Flatbed')."""
        fsm = _get_fsm(ctx)
        tms = _get_tms(ctx)
        fsm.record_tool_invocation("search_loads")
        return await tms.search_loads(origin=origin, destination=destination, equipment=equipment)

    @function_tool()
    async def check_driver_availability(self, ctx: RunContext, equipment: str = "") -> str:
        """Check available drivers, optionally filtered by equipment type."""
        fsm = _get_fsm(ctx)
        tms = _get_tms(ctx)
        fsm.record_tool_invocation("check_driver_availability")
        return await tms.check_driver_availability(equipment=equipment)

    @function_tool()
    async def lookup_driver_by_mc(self, ctx: RunContext, mc_number: str) -> str:
        """Look up a driver's details using their MC number."""
        fsm = _get_fsm(ctx)
        tms = _get_tms(ctx)
        fsm.record_tool_invocation("lookup_driver_by_mc")
        return await tms.lookup_driver_by_mc(mc_number=mc_number)

    @function_tool()
    async def transition_to_negotiation(
        self,
        ctx: RunContext,
        load_id: str,
        origin: str,
        destination: str,
        lane_id: str,
    ) -> str:
        """
        Call this once the driver has selected a load and wants to discuss the rate.
        Provide the load_id, origin, destination, and lane_id (e.g. 'IL-TX').
        """
        fsm = _get_fsm(ctx)
        fsm.context.selected_load_id = load_id
        fsm.context.selected_origin = origin
        fsm.context.selected_destination = destination
        fsm.context.selected_lane_id = lane_id

        if fsm.transition(CallState.NEGOTIATION):
            logger.info(
                "Transitioning to NEGOTIATION",
                call_id=fsm.context.call_id,
                load_id=load_id,
                lane_id=lane_id,
            )
            tenant = ctx.session.userdata.get("tenant_config", {})
            company = tenant.get("company_name", "Nexus Dispatch")
            await ctx.session.update_agent(NegotiationAgent(tenant_company=company))
            return f"Moved to negotiation phase for load {load_id} on lane {lane_id} ({origin} → {destination}). Now present the rate."
        return "Cannot transition to negotiation right now."

    @function_tool()
    async def wrap_up_no_match(self, ctx: RunContext, reason: str) -> str:
        """
        If no loads match the driver's needs, gracefully end the call.
        Provide the reason (e.g. 'no loads available for reefer to TX').
        """
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            tenant = ctx.session.userdata.get("tenant_config", {})
            company = tenant.get("company_name", "Nexus Dispatch")
            await ctx.session.update_agent(WrapUpAgent(tenant_company=company))
            return f"Moving to wrap-up. Reason: {reason}"
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer the call to a human dispatcher. Provide a reason."""
        fsm = _get_fsm(ctx)
        fsm.context.transferred_to_human = True
        fsm.context.transfer_reason = reason
        logger.warning("Call transferred to human", call_id=fsm.context.call_id, reason=reason)
        return f"Transferring to human dispatcher. Reason: {reason}. Please hold."


# =============================================================================
# NEGOTIATION AGENT
# =============================================================================

class NegotiationAgent(Agent):
    """
    Phase 3: Present rates and handle counter-offers.
    Firm but professional — only accepts offers the TMS system allows.
    """

    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(
            instructions=get_negotiation_prompt(company_name=tenant_company),
        )

    @function_tool()
    async def get_rate(self, ctx: RunContext, lane_id: str) -> str:
        """Get the current base rate for a specific lane (e.g., 'IL-TX')."""
        fsm = _get_fsm(ctx)
        tms = _get_tms(ctx)
        fsm.record_tool_invocation("get_rate")
        result = await tms.get_rate(lane_id=lane_id)
        # Try to parse and store the base rate
        try:
            import json
            rate_data = json.loads(result.replace("'", '"'))
            fsm.context.base_rate = rate_data.get("per_mile", 0.0)
        except Exception:
            pass
        return result

    @function_tool()
    async def negotiate_rate(self, ctx: RunContext, lane_id: str, counter_offer: float) -> str:
        """
        Submit a driver's counter-offer for a lane rate (USD per mile).
        The system will accept or reject based on business rules.
        """
        fsm = _get_fsm(ctx)
        tms = _get_tms(ctx)
        fsm.record_tool_invocation("negotiate_rate")
        fsm.context.negotiation_rounds += 1
        result = await tms.negotiate_rate(lane_id=lane_id, counter_offer=counter_offer)
        # Check if accepted and store the agreed rate
        try:
            import json
            neg_data = json.loads(result.replace("'", '"'))
            if neg_data.get("accepted", False):
                fsm.context.agreed_rate = counter_offer
        except Exception:
            pass
        return result

    @function_tool()
    async def transition_to_booking(self, ctx: RunContext, agreed_rate: float) -> str:
        """
        Call this once a rate has been agreed upon (either the base rate or a
        negotiated counter-offer). Provide the final agreed rate per mile.
        """
        fsm = _get_fsm(ctx)
        fsm.context.agreed_rate = agreed_rate

        if fsm.transition(CallState.BOOKING):
            logger.info(
                "Transitioning to BOOKING",
                call_id=fsm.context.call_id,
                agreed_rate=agreed_rate,
            )
            tenant = ctx.session.userdata.get("tenant_config", {})
            company = tenant.get("company_name", "Nexus Dispatch")
            await ctx.session.update_agent(BookingAgent(tenant_company=company))
            return f"Moved to booking phase. Agreed rate: ${agreed_rate}/mile. Now confirm the booking details with the driver."
        return "Cannot transition to booking right now."

    @function_tool()
    async def go_back_to_qualification(self, ctx: RunContext, reason: str) -> str:
        """
        If the driver wants to look at different loads instead of continuing
        negotiation, go back to the qualification phase.
        """
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.QUALIFICATION):
            tenant = ctx.session.userdata.get("tenant_config", {})
            company = tenant.get("company_name", "Nexus Dispatch")
            await ctx.session.update_agent(QualificationAgent(tenant_company=company))
            return f"Going back to load search. Reason: {reason}"
        return "Cannot go back to qualification right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer the call to a human dispatcher. Provide a reason."""
        fsm = _get_fsm(ctx)
        fsm.context.transferred_to_human = True
        fsm.context.transfer_reason = reason
        logger.warning("Call transferred to human", call_id=fsm.context.call_id, reason=reason)
        return f"Transferring to human dispatcher. Reason: {reason}. Please hold."


# =============================================================================
# BOOKING AGENT
# =============================================================================

class BookingAgent(Agent):
    """
    Phase 4: Confirm load details, agreed rate, and dispatch the booking.
    """

    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(
            instructions=get_booking_prompt(company_name=tenant_company),
        )

    @function_tool()
    async def lookup_load(self, ctx: RunContext, load_id: str) -> str:
        """Look up the full details of a specific load by its ID."""
        fsm = _get_fsm(ctx)
        tms = _get_tms(ctx)
        fsm.record_tool_invocation("lookup_load")
        return await tms.lookup_load(load_id=load_id)

    @function_tool()
    async def confirm_booking(
        self,
        ctx: RunContext,
        load_id: str,
        driver_id: str,
        agreed_rate: float,
    ) -> str:
        """
        Confirm and create the booking. This dispatches the rate confirmation.
        Provide the load_id, driver_id (or MC number), and the agreed rate per mile.
        """
        fsm = _get_fsm(ctx)
        booking_tools = _get_booking_tools(ctx)
        fsm.record_tool_invocation("confirm_booking")

        result = await booking_tools.confirm_booking(
            load_id=load_id,
            driver_id=driver_id,
            agreed_rate=agreed_rate,
        )

        # Update context
        fsm.context.booking_confirmed = True
        fsm.context.booking_id = f"BK-{fsm.context.call_id[:8]}"
        fsm.context.agreed_rate = agreed_rate

        return result

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """Call this after the booking is confirmed to end the call professionally."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            logger.info(
                "Transitioning to WRAP_UP",
                call_id=fsm.context.call_id,
                booking_confirmed=fsm.context.booking_confirmed,
            )
            tenant = ctx.session.userdata.get("tenant_config", {})
            company = tenant.get("company_name", "Nexus Dispatch")
            await ctx.session.update_agent(WrapUpAgent(tenant_company=company))
            return "Moved to wrap-up. Thank the driver and end the call."
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer the call to a human dispatcher. Provide a reason."""
        fsm = _get_fsm(ctx)
        fsm.context.transferred_to_human = True
        fsm.context.transfer_reason = reason
        logger.warning("Call transferred to human", call_id=fsm.context.call_id, reason=reason)
        return f"Transferring to human dispatcher. Reason: {reason}. Please hold."


# =============================================================================
# WRAP-UP AGENT
# =============================================================================

class WrapUpAgent(Agent):
    """
    Phase 5: Thank the driver and end the call cleanly.
    """

    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(
            instructions=get_wrap_up_prompt(company_name=tenant_company),
        )

    @function_tool()
    async def end_call(self, ctx: RunContext, summary: str = "") -> str:
        """
        End the call. Provide a brief summary of what was accomplished.
        This will disconnect the caller gracefully.
        """
        fsm = _get_fsm(ctx)
        fsm.record_tool_invocation("end_call")
        call_summary = fsm.get_call_summary()
        logger.info(
            "Call ending",
            call_id=fsm.context.call_id,
            summary=summary,
            call_analytics=call_summary,
        )
        # Store analytics for later retrieval
        ctx.session.userdata["call_summary"] = call_summary
        return await end_call_session(ctx, summary)
