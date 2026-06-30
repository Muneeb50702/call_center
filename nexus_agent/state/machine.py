"""
Nexus Dispatch — Call State Machine

Manages the conversational flow through 5 distinct phases.
Each call gets its own CallStateMachine instance stored in session.userdata.
State transitions are validated to prevent illegal jumps.
"""

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional
import structlog

logger = structlog.get_logger()


class CallState(str, enum.Enum):
    """The 5 phases of a freight dispatch call."""
    GREETING = "GREETING"
    QUALIFICATION = "QUALIFICATION"
    NEGOTIATION = "NEGOTIATION"
    BOOKING = "BOOKING"
    WRAP_UP = "WRAP_UP"


# Valid state transitions — guards against illegal jumps
TRANSITION_MAP: dict[CallState, list[CallState]] = {
    CallState.GREETING: [CallState.QUALIFICATION, CallState.WRAP_UP],
    CallState.QUALIFICATION: [CallState.NEGOTIATION, CallState.WRAP_UP],
    CallState.NEGOTIATION: [CallState.BOOKING, CallState.QUALIFICATION, CallState.WRAP_UP],
    CallState.BOOKING: [CallState.WRAP_UP],
    CallState.WRAP_UP: [],  # Terminal state
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

    # Tenant info (injected at session start)
    tenant_id: str = ""
    company_name: str = ""

    # Driver info (populated during GREETING)
    driver_mc_number: str = ""
    driver_id: str = ""
    driver_name: str = ""
    driver_equipment: str = ""

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
                allowed=TRANSITION_MAP.get(self._current_state, []),
            )
            return False

        previous = self._current_state
        self._current_state = target
        self.context.states_visited.append(target.value)

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
            "states_visited": self.context.states_visited,
            "tools_invoked": self.context.tools_invoked,
            "transferred_to_human": self.context.transferred_to_human,
            "transfer_reason": self.context.transfer_reason,
            "final_state": self._current_state.value,
        }
