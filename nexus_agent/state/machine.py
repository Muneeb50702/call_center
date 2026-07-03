"""
Nexus Dispatch — Call State Machine (10-Mode Architecture)

Manages conversational flow across all 10 dispatcher modes.
Each call gets its own CallStateMachine instance stored in session.userdata.
The GreetingAgent acts as an Intent Router, detecting what the caller needs
and routing to the appropriate specialized agent.

Modes:
1. GREETING → Intent detection
2. QUALIFICATION → Load search (existing)
3. NEGOTIATION → Rate negotiation (existing)
4. BOOKING → Booking confirmation (existing)
5. CHECK_CALL → "Where is my truck?"
6. ETA_UPDATE → ETA communication
7. LOAD_STATUS → Load status inquiry
8. DETENTION → Detention claim reporting
9. BREAKDOWN → Breakdown/emergency handling
10. DOCUMENT_REQUEST → Rate con/POD/BOL requests
11. ONBOARDING → New driver registration
12. WRAP_UP → Call termination (terminal)
"""

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional
import structlog

logger = structlog.get_logger()


class CallState(str, enum.Enum):
    """All phases of a freight dispatch call."""
    # Entry point
    GREETING = "GREETING"

    # Load booking flow (original 5-phase)
    QUALIFICATION = "QUALIFICATION"
    NEGOTIATION = "NEGOTIATION"
    BOOKING = "BOOKING"

    # New dispatcher modes
    CHECK_CALL = "CHECK_CALL"
    ETA_UPDATE = "ETA_UPDATE"
    LOAD_STATUS = "LOAD_STATUS"
    DETENTION = "DETENTION"
    BREAKDOWN = "BREAKDOWN"
    DOCUMENT_REQUEST = "DOCUMENT_REQUEST"
    ONBOARDING = "ONBOARDING"

    # Terminal
    WRAP_UP = "WRAP_UP"


# Valid state transitions — GREETING can route to any mode
TRANSITION_MAP: dict[CallState, list[CallState]] = {
    # Intent Router can go to any mode
    CallState.GREETING: [
        CallState.QUALIFICATION,
        CallState.CHECK_CALL,
        CallState.ETA_UPDATE,
        CallState.LOAD_STATUS,
        CallState.DETENTION,
        CallState.BREAKDOWN,
        CallState.DOCUMENT_REQUEST,
        CallState.ONBOARDING,
        CallState.WRAP_UP,
    ],
    # Load booking flow
    CallState.QUALIFICATION: [CallState.NEGOTIATION, CallState.WRAP_UP],
    CallState.NEGOTIATION: [CallState.BOOKING, CallState.QUALIFICATION, CallState.WRAP_UP],
    CallState.BOOKING: [CallState.WRAP_UP],

    # New modes — each can wrap up or escalate
    CallState.CHECK_CALL: [CallState.ETA_UPDATE, CallState.WRAP_UP],
    CallState.ETA_UPDATE: [CallState.WRAP_UP],
    CallState.LOAD_STATUS: [CallState.CHECK_CALL, CallState.WRAP_UP],
    CallState.DETENTION: [CallState.WRAP_UP],
    CallState.BREAKDOWN: [CallState.WRAP_UP],
    CallState.DOCUMENT_REQUEST: [CallState.WRAP_UP],
    CallState.ONBOARDING: [CallState.QUALIFICATION, CallState.WRAP_UP],  # After onboarding, can search loads

    # Terminal state
    CallState.WRAP_UP: [],
}


@dataclass
class CallContext:
    """
    Accumulated context for a single call.
    Populated progressively as the conversation moves through states.
    Shared across all Agent subclasses via session.userdata.
    """
    # Call metadata
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    call_start_time: float = field(default_factory=time.time)
    call_mode: str = ""  # Primary mode detected by intent router

    # Tenant info (injected at session start)
    tenant_id: str = ""
    company_name: str = ""

    # Driver info (populated during GREETING)
    driver_mc_number: str = ""
    driver_id: str = ""
    driver_name: str = ""
    driver_equipment: str = ""
    driver_phone: str = ""
    driver_email: str = ""

    # Load info (populated during QUALIFICATION)
    selected_load_id: str = ""
    selected_origin: str = ""
    selected_destination: str = ""
    selected_lane_id: str = ""

    # Rate info (populated during NEGOTIATION)
    base_rate: float = 0.0
    agreed_rate: float = 0.0
    negotiation_rounds: int = 0

    # Booking info (populated during BOOKING)
    booking_id: str = ""
    booking_confirmed: bool = False

    # Check call / ETA info
    check_call_load_id: str = ""
    check_call_location: str = ""
    check_call_eta: str = ""

    # Detention info
    detention_claim_id: str = ""
    detention_facility: str = ""
    detention_hours: float = 0.0

    # Breakdown info
    breakdown_location: str = ""
    breakdown_description: str = ""

    # Document info
    document_type: str = ""  # rate_confirmation, pod, bol
    document_sent_to: str = ""

    # Onboarding info
    onboarding_mc_number: str = ""
    onboarding_completed: bool = False

    # Analytics
    states_visited: list[str] = field(default_factory=list)
    tools_invoked: list[str] = field(default_factory=list)
    transferred_to_human: bool = False
    transfer_reason: str = ""


class CallStateMachine:
    """
    Finite-state machine for managing dispatch call flow.

    One instance per call, stored in session.userdata["state_machine"].
    Validates transitions and emits structured logs for analytics.
    """

    def __init__(self, tenant_id: str = "", company_name: str = ""):
        self._current_state = CallState.GREETING
        self.context = CallContext(
            tenant_id=tenant_id,
            company_name=company_name,
        )
        self.context.states_visited.append(CallState.GREETING.value)
        logger.info(
            "Call state machine initialized",
            call_id=self.context.call_id,
            tenant_id=tenant_id,
            initial_state=self._current_state.value,
        )

    @property
    def current_state(self) -> CallState:
        return self._current_state

    def can_transition(self, target: CallState) -> bool:
        """Check if a transition from the current state to target is valid."""
        return target in TRANSITION_MAP.get(self._current_state, [])

    def transition(self, target: CallState) -> bool:
        """
        Attempt to transition to a new state.
        Returns True if successful, False if the transition is invalid.
        """
        if not self.can_transition(target):
            logger.warning(
                "Invalid state transition attempted",
                call_id=self.context.call_id,
                from_state=self._current_state.value,
                to_state=target.value,
                allowed=[s.value for s in TRANSITION_MAP.get(self._current_state, [])],
            )
            return False

        previous = self._current_state
        self._current_state = target
        self.context.states_visited.append(target.value)

        # Track the primary call mode on first transition from GREETING
        if previous == CallState.GREETING and target != CallState.WRAP_UP:
            mode_map = {
                CallState.QUALIFICATION: "load_booking",
                CallState.CHECK_CALL: "check_call",
                CallState.ETA_UPDATE: "eta_update",
                CallState.LOAD_STATUS: "load_status",
                CallState.DETENTION: "detention",
                CallState.BREAKDOWN: "breakdown",
                CallState.DOCUMENT_REQUEST: "document_request",
                CallState.ONBOARDING: "onboarding",
            }
            self.context.call_mode = mode_map.get(target, "unknown")

        logger.info(
            "State transition successful",
            call_id=self.context.call_id,
            from_state=previous.value,
            to_state=target.value,
            elapsed_seconds=round(time.time() - self.context.call_start_time, 2),
        )
        return True

    def record_tool_invocation(self, tool_name: str):
        """Track which tools were used during this call."""
        self.context.tools_invoked.append(tool_name)

    def get_call_duration(self) -> float:
        """Get the current call duration in seconds."""
        return round(time.time() - self.context.call_start_time, 2)

    def get_call_summary(self) -> dict:
        """
        Generate a structured summary of the call for analytics.
        Called at WRAP_UP or when the call ends.
        """
        return {
            "call_id": self.context.call_id,
            "tenant_id": self.context.tenant_id,
            "company_name": self.context.company_name,
            "call_mode": self.context.call_mode,
            "duration_seconds": self.get_call_duration(),
            "driver_mc": self.context.driver_mc_number,
            "driver_name": self.context.driver_name,
            "load_id": self.context.selected_load_id,
            "lane": self.context.selected_lane_id,
            "base_rate": self.context.base_rate,
            "agreed_rate": self.context.agreed_rate,
            "negotiation_rounds": self.context.negotiation_rounds,
            "booking_confirmed": self.context.booking_confirmed,
            "booking_id": self.context.booking_id,
            "check_call_load_id": self.context.check_call_load_id,
            "detention_claim_id": self.context.detention_claim_id,
            "onboarding_completed": self.context.onboarding_completed,
            "states_visited": self.context.states_visited,
            "tools_invoked": self.context.tools_invoked,
            "transferred_to_human": self.context.transferred_to_human,
            "transfer_reason": self.context.transfer_reason,
            "final_state": self._current_state.value,
        }
