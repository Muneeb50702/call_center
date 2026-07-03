"""
Unit tests for the Call State Machine (12 Modes).
Tests state transitions, context accumulation, and edge cases.
"""

import pytest
from state.machine import CallState, CallStateMachine, TRANSITION_MAP


class TestCallStateMachine:
    """Tests for the core FSM logic."""

    def test_initial_state_is_greeting(self):
        fsm = CallStateMachine()
        assert fsm.current_state == CallState.GREETING

    def test_greeting_states_visited_on_init(self):
        fsm = CallStateMachine()
        assert "GREETING" in fsm.context.states_visited

    # ── Original 5-Phase Tests ──
    def test_valid_transition_greeting_to_qualification(self):
        fsm = CallStateMachine()
        result = fsm.transition(CallState.QUALIFICATION)
        assert result is True
        assert fsm.current_state == CallState.QUALIFICATION

    def test_valid_transition_qualification_to_negotiation(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        result = fsm.transition(CallState.NEGOTIATION)
        assert result is True
        assert fsm.current_state == CallState.NEGOTIATION

    def test_valid_transition_negotiation_to_booking(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        fsm.transition(CallState.NEGOTIATION)
        result = fsm.transition(CallState.BOOKING)
        assert result is True
        assert fsm.current_state == CallState.BOOKING

    def test_valid_transition_booking_to_wrap_up(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        fsm.transition(CallState.NEGOTIATION)
        fsm.transition(CallState.BOOKING)
        result = fsm.transition(CallState.WRAP_UP)
        assert result is True
        assert fsm.current_state == CallState.WRAP_UP

    # ── New 10-Mode Routing Tests ──
    def test_intent_router_transitions(self):
        """Test that GREETING can transition to any specific mode."""
        valid_targets = [
            CallState.QUALIFICATION,
            CallState.CHECK_CALL,
            CallState.ETA_UPDATE,
            CallState.LOAD_STATUS,
            CallState.DETENTION,
            CallState.BREAKDOWN,
            CallState.DOCUMENT_REQUEST,
            CallState.ONBOARDING,
            CallState.WRAP_UP,
        ]
        for target in valid_targets:
            fsm = CallStateMachine()
            assert fsm.transition(target) is True
            assert fsm.current_state == target

    def test_check_call_transitions(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.CHECK_CALL)
        assert fsm.can_transition(CallState.ETA_UPDATE) is True
        assert fsm.can_transition(CallState.WRAP_UP) is True
        assert fsm.can_transition(CallState.QUALIFICATION) is False

    def test_load_status_transitions(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.LOAD_STATUS)
        assert fsm.can_transition(CallState.CHECK_CALL) is True
        assert fsm.can_transition(CallState.WRAP_UP) is True

    def test_onboarding_transitions(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.ONBOARDING)
        assert fsm.can_transition(CallState.QUALIFICATION) is True
        assert fsm.can_transition(CallState.WRAP_UP) is True

    # ── Invalid Transitions ──
    def test_invalid_transition_greeting_to_negotiation(self):
        fsm = CallStateMachine()
        result = fsm.transition(CallState.NEGOTIATION)
        assert result is False
        assert fsm.current_state == CallState.GREETING  # State unchanged

    def test_invalid_transition_wrap_up_to_anything(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.WRAP_UP)
        # WRAP_UP is terminal
        assert fsm.transition(CallState.GREETING) is False
        assert fsm.transition(CallState.QUALIFICATION) is False
        assert fsm.transition(CallState.BREAKDOWN) is False

    # ── Call Mode Tracking ──
    def test_call_mode_tracking(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.DETENTION)
        assert fsm.context.call_mode == "detention"

        fsm2 = CallStateMachine()
        fsm2.transition(CallState.ONBOARDING)
        assert fsm2.context.call_mode == "onboarding"


class TestCallContext:
    """Tests for context accumulation during a call."""

    def test_context_stores_tenant_info(self):
        fsm = CallStateMachine(tenant_id="abc", company_name="ABC Logistics")
        assert fsm.context.tenant_id == "abc"
        assert fsm.context.company_name == "ABC Logistics"

    def test_new_context_fields(self):
        fsm = CallStateMachine()
        fsm.context.check_call_load_id = "L100"
        fsm.context.detention_facility = "Walmart DC"
        fsm.context.breakdown_location = "I-90 MM 42"
        fsm.context.document_type = "pod"
        
        assert fsm.context.check_call_load_id == "L100"
        assert fsm.context.detention_facility == "Walmart DC"
        assert fsm.context.breakdown_location == "I-90 MM 42"
        assert fsm.context.document_type == "pod"

    def test_tool_invocation_recording(self):
        fsm = CallStateMachine()
        fsm.record_tool_invocation("create_detention_claim")
        fsm.record_tool_invocation("transfer_to_human")
        assert fsm.context.tools_invoked == ["create_detention_claim", "transfer_to_human"]

    def test_call_summary(self):
        fsm = CallStateMachine(tenant_id="abc", company_name="ABC")
        fsm.context.driver_mc_number = "MC123"
        fsm.transition(CallState.DETENTION)
        
        summary = fsm.get_call_summary()
        assert summary["tenant_id"] == "abc"
        assert summary["driver_mc"] == "MC123"
        assert summary["call_mode"] == "detention"
        assert summary["final_state"] == "DETENTION"
        assert "call_id" in summary
        assert "duration_seconds" in summary


class TestTransitionMap:
    """Tests for the transition map configuration."""

    def test_all_states_have_entries(self):
        for state in CallState:
            assert state in TRANSITION_MAP

    def test_wrap_up_is_terminal(self):
        assert TRANSITION_MAP[CallState.WRAP_UP] == []
