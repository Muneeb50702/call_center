"""
Nexus Dispatch — Specialized Agent Classes (All 10 Modes)

Each conversation mode has its own Agent subclass with:
- Mode-specific system instructions
- Mode-specific tools (state-gated)
- Transition tools to move between modes via session.update_agent()

The GreetingAgent acts as an Intent Router — detecting what the caller
needs and routing to the appropriate specialized agent.

Agents:
1. GreetingAgent (Intent Router)
2. QualificationAgent (Load Search)
3. NegotiationAgent (Rate Discussion)
4. BookingAgent (Booking Confirmation)
5. CheckCallAgent (Where is my truck?)
6. ETAUpdateAgent (ETA Communication)
7. LoadStatusAgent (Load Status Inquiry)
8. DetentionAgent (Detention Claims)
9. BreakdownAgent (Breakdown/Emergency)
10. DocumentAgent (Rate Con/POD/BOL)
11. OnboardingAgent (Driver Registration)
12. WrapUpAgent (Call Termination)
"""

import structlog
from livekit.agents import Agent, function_tool, RunContext

from llm.prompts import (
    get_greeting_prompt,
    get_qualification_prompt,
    get_negotiation_prompt,
    get_booking_prompt,
    get_check_call_prompt,
    get_eta_update_prompt,
    get_load_status_prompt,
    get_detention_prompt,
    get_breakdown_prompt,
    get_document_prompt,
    get_onboarding_prompt,
    get_wrap_up_prompt,
)
from state.machine import CallState, CallStateMachine
from tools.tms_tools import TMSTools
from tools.call_control import end_call_session
from tools.booking_tools import BookingTools
from tools.check_call_tools import CheckCallTools
from tools.detention_tools import DetentionTools
from tools.document_tools import DocumentTools
from tools.onboarding_tools import OnboardingTools

logger = structlog.get_logger()


# ── Helpers ──

def _get_fsm(ctx: RunContext) -> CallStateMachine:
    return ctx.session.userdata["state_machine"]

def _get_tms(ctx: RunContext) -> TMSTools:
    return ctx.session.userdata["tms_tools"]

def _get_booking_tools(ctx: RunContext) -> BookingTools:
    return ctx.session.userdata["booking_tools"]

def _get_check_call_tools(ctx: RunContext) -> CheckCallTools:
    return ctx.session.userdata["check_call_tools"]

def _get_detention_tools(ctx: RunContext) -> DetentionTools:
    return ctx.session.userdata["detention_tools"]

def _get_document_tools(ctx: RunContext) -> DocumentTools:
    return ctx.session.userdata["document_tools"]

def _get_onboarding_tools(ctx: RunContext) -> OnboardingTools:
    return ctx.session.userdata["onboarding_tools"]

def _get_company(ctx: RunContext) -> str:
    return ctx.session.userdata.get("tenant_config", {}).get("company_name", "Nexus Dispatch")


# =============================================================================
# 1. GREETING AGENT (Intent Router)
# =============================================================================

class GreetingAgent(Agent):
    """
    Phase 1: Greet the caller, collect their identity, and detect intent.
    Routes to the appropriate specialized agent based on what the caller needs.
    """

    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(
            instructions=get_greeting_prompt(company_name=tenant_company),
        )

    # ── Intent Routing Tools ──

    @function_tool()
    async def route_to_load_booking(
        self, ctx: RunContext,
        mc_number: str = "", driver_name: str = "", equipment_type: str = "",
    ) -> str:
        """Route caller to load booking flow. Call when they want to find/book a load."""
        fsm = _get_fsm(ctx)
        fsm.context.driver_mc_number = mc_number
        fsm.context.driver_name = driver_name
        fsm.context.driver_equipment = equipment_type
        if fsm.transition(CallState.QUALIFICATION):
            logger.info("Routing to LOAD BOOKING", call_id=fsm.context.call_id)
            await ctx.session.update_agent(QualificationAgent(tenant_company=_get_company(ctx)))
            return f"Moved to load search. Driver: {driver_name}, MC: {mc_number}."
        return "Cannot route to load booking right now."

    @function_tool()
    async def route_to_check_call(
        self, ctx: RunContext,
        load_id: str = "", caller_name: str = "",
    ) -> str:
        """Route caller to check call flow. Call when they ask 'where is my truck/load?'"""
        fsm = _get_fsm(ctx)
        fsm.context.driver_name = caller_name
        fsm.context.check_call_load_id = load_id
        
        location_data = ""
        if load_id:
            tools = _get_check_call_tools(ctx)
            location_data = await tools.get_load_location(load_id=load_id)

        if fsm.transition(CallState.CHECK_CALL):
            logger.info("Routing to CHECK CALL", call_id=fsm.context.call_id)
            await ctx.session.update_agent(CheckCallAgent(tenant_company=_get_company(ctx)))
            return f"SYSTEM: Moved to check call mode. PRE-FETCHED LOCATION: {location_data}. Tell the user this location immediately."
        return "Cannot route to check call right now."

    @function_tool()
    async def route_to_load_status(
        self, ctx: RunContext,
        load_id: str = "", caller_name: str = "",
    ) -> str:
        """Route caller to load status inquiry. Call when they ask about a load's status."""
        fsm = _get_fsm(ctx)
        fsm.context.driver_name = caller_name
        fsm.context.check_call_load_id = load_id
        
        status_data = ""
        if load_id:
            tms = _get_tms(ctx)
            status_data = await tms.lookup_load(load_id=load_id)

        if fsm.transition(CallState.LOAD_STATUS):
            logger.info("Routing to LOAD STATUS", call_id=fsm.context.call_id)
            await ctx.session.update_agent(LoadStatusAgent(tenant_company=_get_company(ctx)))
            return f"SYSTEM: Moved to load status mode. PRE-FETCHED STATUS: {status_data}. Tell the user this status immediately."
        return "Cannot route to load status right now."

    @function_tool()
    async def route_to_eta_update(
        self, ctx: RunContext,
        load_id: str = "", caller_name: str = "",
    ) -> str:
        """Route caller to ETA update flow. Call when they ask about delivery timing."""
        fsm = _get_fsm(ctx)
        fsm.context.driver_name = caller_name
        fsm.context.check_call_load_id = load_id
        
        eta_data = ""
        if load_id:
            tools = _get_check_call_tools(ctx)
            eta_data = await tools.get_load_eta(load_id=load_id)

        if fsm.transition(CallState.ETA_UPDATE):
            logger.info("Routing to ETA UPDATE", call_id=fsm.context.call_id)
            await ctx.session.update_agent(ETAUpdateAgent(tenant_company=_get_company(ctx)))
            return f"SYSTEM: Moved to ETA update mode. PRE-FETCHED ETA: {eta_data}. Tell the user this ETA immediately."
        return "Cannot route to ETA update right now."

    @function_tool()
    async def route_to_detention(
        self, ctx: RunContext,
        driver_name: str = "", load_id: str = "",
    ) -> str:
        """Route caller to detention claim flow. Call when a driver is stuck at a facility."""
        fsm = _get_fsm(ctx)
        fsm.context.driver_name = driver_name
        fsm.context.check_call_load_id = load_id
        if fsm.transition(CallState.DETENTION):
            logger.info("Routing to DETENTION", call_id=fsm.context.call_id)
            await ctx.session.update_agent(DetentionAgent(tenant_company=_get_company(ctx)))
            return f"Moved to detention claim mode."
        return "Cannot route to detention right now."

    @function_tool()
    async def route_to_breakdown(
        self, ctx: RunContext,
        driver_name: str = "", location: str = "",
    ) -> str:
        """Route caller to breakdown/emergency flow. Call when there's a breakdown or emergency."""
        fsm = _get_fsm(ctx)
        fsm.context.driver_name = driver_name
        fsm.context.breakdown_location = location
        if fsm.transition(CallState.BREAKDOWN):
            logger.info("Routing to BREAKDOWN", call_id=fsm.context.call_id)
            await ctx.session.update_agent(BreakdownAgent(tenant_company=_get_company(ctx)))
            return f"Moved to breakdown mode. Location: {location}."
        return "Cannot route to breakdown right now."

    @function_tool()
    async def route_to_document_request(
        self, ctx: RunContext,
        doc_type: str = "", reference_id: str = "",
    ) -> str:
        """Route caller to document request flow. Call when they need a rate con, POD, or BOL."""
        fsm = _get_fsm(ctx)
        fsm.context.document_type = doc_type
        if fsm.transition(CallState.DOCUMENT_REQUEST):
            logger.info("Routing to DOCUMENT REQUEST", call_id=fsm.context.call_id)
            await ctx.session.update_agent(DocumentAgent(tenant_company=_get_company(ctx)))
            return f"Moved to document request mode. Type: {doc_type}."
        return "Cannot route to document request right now."

    @function_tool()
    async def route_to_onboarding(
        self, ctx: RunContext,
        driver_name: str = "", mc_number: str = "",
    ) -> str:
        """Route caller to driver onboarding. Call when a new driver wants to register."""
        fsm = _get_fsm(ctx)
        fsm.context.driver_name = driver_name
        fsm.context.onboarding_mc_number = mc_number
        if fsm.transition(CallState.ONBOARDING):
            logger.info("Routing to ONBOARDING", call_id=fsm.context.call_id)
            await ctx.session.update_agent(OnboardingAgent(tenant_company=_get_company(ctx)))
            return f"Moved to onboarding mode."
        return "Cannot route to onboarding right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer the call to a senior dispatcher. LAST RESORT ONLY — use after 2-3 recovery attempts have failed, or for genuine emergencies."""
        fsm = _get_fsm(ctx)
        fsm.context.transferred_to_human = True
        fsm.context.transfer_reason = reason
        logger.warning("Call transferred to senior", call_id=fsm.context.call_id, reason=reason)
        return f"SYSTEM: Call is being transferred to a senior dispatcher. Reason: {reason}. Tell the caller: 'Let me connect you with one of our senior dispatchers.' Do NOT say 'human'."


# =============================================================================
# 2. QUALIFICATION AGENT (Load Search)
# =============================================================================

class QualificationAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_qualification_prompt(company_name=tenant_company))

    @function_tool()
    async def search_loads(self, ctx: RunContext, origin: str = "", destination: str = "", equipment: str = "") -> str:
        """Search for available freight loads by origin, destination, or equipment type (e.g. 'Dry Van', 'Reefer', 'Flatbed')."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("search_loads")
        return await tms.search_loads(origin=origin, destination=destination, equipment=equipment)

    @function_tool()
    async def check_driver_availability(self, ctx: RunContext, equipment: str = "") -> str:
        """Check available drivers, optionally filtered by equipment type."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("check_driver_availability")
        return await tms.check_driver_availability(equipment=equipment)

    @function_tool()
    async def lookup_driver_by_mc(self, ctx: RunContext, mc_number: str) -> str:
        """Look up a driver's details using their MC number."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("lookup_driver_by_mc")
        return await tms.lookup_driver_by_mc(mc_number=mc_number)

    @function_tool()
    async def transition_to_negotiation(self, ctx: RunContext, load_id: str, origin: str, destination: str, lane_id: str) -> str:
        """Call this once the driver has selected a load and wants to discuss the rate."""
        fsm = _get_fsm(ctx)
        fsm.context.selected_load_id = load_id
        fsm.context.selected_origin = origin
        fsm.context.selected_destination = destination
        fsm.context.selected_lane_id = lane_id
        if fsm.transition(CallState.NEGOTIATION):
            logger.info("Transitioning to NEGOTIATION", call_id=fsm.context.call_id, load_id=load_id)
            await ctx.session.update_agent(NegotiationAgent(tenant_company=_get_company(ctx)))
            return f"Moved to negotiation for load {load_id} on lane {lane_id}."
        return "Cannot transition to negotiation right now."

    @function_tool()
    async def wrap_up_no_match(self, ctx: RunContext, reason: str) -> str:
        """If no loads match the driver's needs, gracefully end the call."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return f"Moving to wrap-up. Reason: {reason}"
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a senior dispatcher. LAST RESORT — try recovery first."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        logger.warning("Call transferred to senior", call_id=fsm.context.call_id, reason=reason)
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me get one of our senior team members for you.'"


# =============================================================================
# 3. NEGOTIATION AGENT
# =============================================================================

class NegotiationAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_negotiation_prompt(company_name=tenant_company))

    @function_tool()
    async def get_rate(self, ctx: RunContext, lane_id: str) -> str:
        """Get the current base rate for a specific lane (e.g., 'IL-TX')."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("get_rate")
        result = await tms.get_rate(lane_id=lane_id)
        try:
            import json
            rate_data = json.loads(result.replace("'", '"'))
            fsm.context.base_rate = rate_data.get("per_mile", 0.0)
        except Exception:
            pass
        return result

    @function_tool()
    async def negotiate_rate(self, ctx: RunContext, lane_id: str, counter_offer: float) -> str:
        """Submit a driver's counter-offer for a lane rate (USD per mile)."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("negotiate_rate")
        fsm.context.negotiation_rounds += 1
        result = await tms.negotiate_rate(lane_id=lane_id, counter_offer=counter_offer)
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
        """Call once a rate is agreed upon. Provide the final agreed rate per mile."""
        fsm = _get_fsm(ctx); fsm.context.agreed_rate = agreed_rate
        if fsm.transition(CallState.BOOKING):
            logger.info("Transitioning to BOOKING", call_id=fsm.context.call_id, agreed_rate=agreed_rate)
            await ctx.session.update_agent(BookingAgent(tenant_company=_get_company(ctx)))
            return f"Moved to booking. Agreed rate: ${agreed_rate}/mile."
        return "Cannot transition to booking right now."

    @function_tool()
    async def go_back_to_qualification(self, ctx: RunContext, reason: str) -> str:
        """Go back to load search if the driver wants different loads."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.QUALIFICATION):
            await ctx.session.update_agent(QualificationAgent(tenant_company=_get_company(ctx)))
            return f"Going back to load search. Reason: {reason}"
        return "Cannot go back right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a senior dispatcher. LAST RESORT."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me get my manager to take a look at this for you.'"


# =============================================================================
# 4. BOOKING AGENT
# =============================================================================

class BookingAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_booking_prompt(company_name=tenant_company))

    @function_tool()
    async def lookup_load(self, ctx: RunContext, load_id: str) -> str:
        """Look up the full details of a specific load by its ID."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("lookup_load")
        return await tms.lookup_load(load_id=load_id)

    @function_tool()
    async def confirm_booking(self, ctx: RunContext, load_id: str, driver_id: str, agreed_rate: float) -> str:
        """Confirm and create the booking. Provide load_id, driver_id, and agreed rate."""
        fsm = _get_fsm(ctx); booking_tools = _get_booking_tools(ctx)
        fsm.record_tool_invocation("confirm_booking")
        result = await booking_tools.confirm_booking(load_id=load_id, driver_id=driver_id, agreed_rate=agreed_rate)
        fsm.context.booking_confirmed = True
        fsm.context.booking_id = f"BK-{fsm.context.call_id[:8]}"
        fsm.context.agreed_rate = agreed_rate
        return result

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """Call after the booking is confirmed to end the call."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return "Moved to wrap-up. Thank the driver and end the call."
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a senior dispatcher. LAST RESORT."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me have one of our senior dispatchers finalize this for you.'"


# =============================================================================
# 5. CHECK CALL AGENT
# =============================================================================

class CheckCallAgent(Agent):
    """Handles 'where is my truck?' calls."""

    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_check_call_prompt(company_name=tenant_company))

    @function_tool()
    async def get_load_location(self, ctx: RunContext, load_id: str) -> str:
        """Get the current GPS location and status of a load."""
        fsm = _get_fsm(ctx); tools = _get_check_call_tools(ctx)
        fsm.record_tool_invocation("get_load_location")
        fsm.context.check_call_load_id = load_id
        return await tools.get_load_location(load_id=load_id)

    @function_tool()
    async def get_load_eta(self, ctx: RunContext, load_id: str) -> str:
        """Calculate the estimated time of arrival for a load."""
        fsm = _get_fsm(ctx); tools = _get_check_call_tools(ctx)
        fsm.record_tool_invocation("get_load_eta")
        return await tools.get_load_eta(load_id=load_id)

    @function_tool()
    async def lookup_load(self, ctx: RunContext, load_id: str) -> str:
        """Look up full load details by ID."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("lookup_load")
        return await tms.lookup_load(load_id=load_id)

    @function_tool()
    async def transition_to_eta_update(self, ctx: RunContext) -> str:
        """Move to ETA update mode if the caller needs an ETA sent to someone."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.ETA_UPDATE):
            await ctx.session.update_agent(ETAUpdateAgent(tenant_company=_get_company(ctx)))
            return "Moved to ETA update mode."
        return "Cannot transition right now."

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """End the call after providing the location."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return "Moving to wrap-up."
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a senior dispatcher. LAST RESORT."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me connect you with one of our senior team members.'"


# =============================================================================
# 6. ETA UPDATE AGENT
# =============================================================================

class ETAUpdateAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_eta_update_prompt(company_name=tenant_company))

    @function_tool()
    async def get_load_eta(self, ctx: RunContext, load_id: str) -> str:
        """Calculate ETA for a load."""
        fsm = _get_fsm(ctx); tools = _get_check_call_tools(ctx); fsm.record_tool_invocation("get_load_eta")
        return await tools.get_load_eta(load_id=load_id)

    @function_tool()
    async def send_eta_notification(self, ctx: RunContext, load_id: str, message: str, email: str = "") -> str:
        """Send an ETA update notification to the broker/shipper."""
        fsm = _get_fsm(ctx); tools = _get_check_call_tools(ctx); fsm.record_tool_invocation("send_eta_notification")
        return await tools.send_eta_notification(load_id=load_id, message=message, email=email)

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """End the call."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return "Moving to wrap-up."
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a human."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me get one of our senior dispatchers on the line for you.'"


# =============================================================================
# 7. LOAD STATUS AGENT
# =============================================================================

class LoadStatusAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_load_status_prompt(company_name=tenant_company))

    @function_tool()
    async def lookup_load(self, ctx: RunContext, load_id: str) -> str:
        """Look up load details and current status."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("lookup_load")
        return await tms.lookup_load(load_id=load_id)

    @function_tool()
    async def get_load_location(self, ctx: RunContext, load_id: str) -> str:
        """Get GPS location for in-transit loads."""
        fsm = _get_fsm(ctx); tools = _get_check_call_tools(ctx); fsm.record_tool_invocation("get_load_location")
        return await tools.get_load_location(load_id=load_id)

    @function_tool()
    async def transition_to_check_call(self, ctx: RunContext) -> str:
        """Move to check call mode if they need detailed location."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.CHECK_CALL):
            await ctx.session.update_agent(CheckCallAgent(tenant_company=_get_company(ctx)))
            return "Moved to check call mode."
        return "Cannot transition right now."

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """End the call."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return "Moving to wrap-up."
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a human."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me connect you with one of our senior team members.'"


# =============================================================================
# 8. DETENTION AGENT
# =============================================================================

class DetentionAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_detention_prompt(company_name=tenant_company))

    @function_tool()
    async def create_detention_claim(
        self, ctx: RunContext,
        load_id: str, facility_name: str = "", facility_type: str = "shipper",
        arrival_time: str = "", departure_time: str = "", notes: str = "",
    ) -> str:
        """Create a detention claim for a driver stuck at a facility."""
        fsm = _get_fsm(ctx); tools = _get_detention_tools(ctx)
        fsm.record_tool_invocation("create_detention_claim")
        result = await tools.create_detention_claim(
            load_id=load_id, facility_name=facility_name, facility_type=facility_type,
            arrival_time=arrival_time, departure_time=departure_time,
            driver_id=fsm.context.driver_id, notes=notes,
        )
        return result

    @function_tool()
    async def lookup_load(self, ctx: RunContext, load_id: str) -> str:
        """Look up load details."""
        fsm = _get_fsm(ctx); tms = _get_tms(ctx); fsm.record_tool_invocation("lookup_load")
        return await tms.lookup_load(load_id=load_id)

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """End the call after filing the claim."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return "Moving to wrap-up."
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a human."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me get one of our senior dispatchers to help with this.'"


# =============================================================================
# 9. BREAKDOWN AGENT
# =============================================================================

class BreakdownAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_breakdown_prompt(company_name=tenant_company))

    @function_tool()
    async def log_breakdown(
        self, ctx: RunContext,
        location: str, description: str, load_id: str = "", is_safe: bool = True,
    ) -> str:
        """Log a breakdown event. Always escalate to human after logging."""
        fsm = _get_fsm(ctx)
        fsm.record_tool_invocation("log_breakdown")
        fsm.context.breakdown_location = location
        fsm.context.breakdown_description = description
        logger.warning(
            "BREAKDOWN REPORTED",
            call_id=fsm.context.call_id,
            location=location,
            description=description,
            load_id=load_id,
            is_safe=is_safe,
        )
        return (
            f"Breakdown logged. Location: {location}. Issue: {description}. "
            f"Driver safe: {'Yes' if is_safe else 'NO — URGENT'}. "
            f"A senior dispatcher will coordinate roadside assistance. Tell the caller you're connecting them with your senior team."
        )

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """ALWAYS transfer to human after a breakdown report."""
        fsm = _get_fsm(ctx)
        fsm.context.transferred_to_human = True
        fsm.context.transfer_reason = reason
        logger.warning("Breakdown escalated to senior", call_id=fsm.context.call_id, reason=reason)
        return f"SYSTEM: Connecting to senior dispatcher for roadside assistance. Reason: {reason}. Tell the caller: 'I'm connecting you with one of our senior dispatchers right now. They'll get you taken care of.'"

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """End the call (only after human transfer is arranged)."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return "Moving to wrap-up."
        return "Cannot wrap up right now."


# =============================================================================
# 10. DOCUMENT AGENT
# =============================================================================

class DocumentAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_document_prompt(company_name=tenant_company))

    @function_tool()
    async def send_rate_confirmation(self, ctx: RunContext, booking_id: str, email: str) -> str:
        """Send a rate confirmation document to the specified email."""
        fsm = _get_fsm(ctx); tools = _get_document_tools(ctx)
        fsm.record_tool_invocation("send_rate_confirmation")
        fsm.context.document_type = "rate_confirmation"
        fsm.context.document_sent_to = email
        return await tools.send_rate_confirmation(booking_id=booking_id, email=email)

    @function_tool()
    async def send_pod(self, ctx: RunContext, load_id: str, email: str) -> str:
        """Send a Proof of Delivery document."""
        fsm = _get_fsm(ctx); tools = _get_document_tools(ctx)
        fsm.record_tool_invocation("send_pod")
        fsm.context.document_type = "pod"
        fsm.context.document_sent_to = email
        return await tools.send_pod(load_id=load_id, email=email)

    @function_tool()
    async def send_bol(self, ctx: RunContext, load_id: str, email: str) -> str:
        """Send a Bill of Lading document."""
        fsm = _get_fsm(ctx); tools = _get_document_tools(ctx)
        fsm.record_tool_invocation("send_bol")
        fsm.context.document_type = "bol"
        fsm.context.document_sent_to = email
        return await tools.send_bol(load_id=load_id, email=email)

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """End the call after sending the document."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return "Moving to wrap-up."
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a human."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me connect you with one of our senior team members.'"


# =============================================================================
# 11. ONBOARDING AGENT
# =============================================================================

class OnboardingAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_onboarding_prompt(company_name=tenant_company))

    @function_tool()
    async def validate_mc_number(self, ctx: RunContext, mc_number: str) -> str:
        """Validate MC number format."""
        fsm = _get_fsm(ctx); tools = _get_onboarding_tools(ctx)
        fsm.record_tool_invocation("validate_mc_number")
        return await tools.validate_mc_number(mc_number=mc_number)

    @function_tool()
    async def check_duplicate_driver(self, ctx: RunContext, mc_number: str) -> str:
        """Check if a driver with this MC number is already registered."""
        fsm = _get_fsm(ctx); tools = _get_onboarding_tools(ctx)
        fsm.record_tool_invocation("check_duplicate_driver")
        return await tools.check_duplicate_driver(mc_number=mc_number)

    @function_tool()
    async def register_driver(
        self, ctx: RunContext,
        mc_number: str, name: str, equipment: str,
        phone: str = "", email: str = "", dot_number: str = "",
    ) -> str:
        """Register a new driver in the system."""
        fsm = _get_fsm(ctx); tools = _get_onboarding_tools(ctx)
        fsm.record_tool_invocation("register_driver")
        result = await tools.register_driver(
            mc_number=mc_number, name=name, equipment=equipment,
            phone=phone, email=email, dot_number=dot_number,
        )
        fsm.context.onboarding_completed = True
        fsm.context.driver_name = name
        fsm.context.driver_mc_number = mc_number
        return result

    @function_tool()
    async def transition_to_qualification(self, ctx: RunContext) -> str:
        """Move to load search after onboarding (if they want to find a load)."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.QUALIFICATION):
            await ctx.session.update_agent(QualificationAgent(tenant_company=_get_company(ctx)))
            return "Moved to load search. Let's find you a load!"
        return "Cannot transition right now."

    @function_tool()
    async def transition_to_wrap_up(self, ctx: RunContext) -> str:
        """End the call after registration."""
        fsm = _get_fsm(ctx)
        if fsm.transition(CallState.WRAP_UP):
            await ctx.session.update_agent(WrapUpAgent(tenant_company=_get_company(ctx)))
            return "Moving to wrap-up."
        return "Cannot wrap up right now."

    @function_tool()
    async def transfer_to_human(self, ctx: RunContext, reason: str) -> str:
        """Transfer to a human."""
        fsm = _get_fsm(ctx); fsm.context.transferred_to_human = True; fsm.context.transfer_reason = reason
        return f"SYSTEM: Transferring to senior dispatcher. Reason: {reason}. Tell the caller: 'Let me get one of our senior dispatchers for you.'"


# =============================================================================
# 12. WRAP-UP AGENT
# =============================================================================

class WrapUpAgent(Agent):
    def __init__(self, tenant_company: str = "Nexus Dispatch"):
        super().__init__(instructions=get_wrap_up_prompt(company_name=tenant_company))

    @function_tool()
    async def end_call(self, ctx: RunContext, summary: str = "") -> str:
        """End the call. Provide a brief summary of what was accomplished."""
        fsm = _get_fsm(ctx)
        fsm.record_tool_invocation("end_call")
        call_summary = fsm.get_call_summary()
        logger.info("Call ending", call_id=fsm.context.call_id, summary=summary, call_analytics=call_summary)
        ctx.session.userdata["call_summary"] = call_summary
        return await end_call_session(ctx, summary)
