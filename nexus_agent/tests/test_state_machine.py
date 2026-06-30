"""
Unit tests for the Call State Machine.
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

    def test_invalid_transition_greeting_to_negotiation(self):
        fsm = CallStateMachine()
        result = fsm.transition(CallState.NEGOTIATION)
        assert result is False
        assert fsm.current_state == CallState.GREETING  # State unchanged

    def test_invalid_transition_greeting_to_booking(self):
        fsm = CallStateMachine()
        result = fsm.transition(CallState.BOOKING)
        assert result is False
        assert fsm.current_state == CallState.GREETING

    def test_invalid_transition_wrap_up_to_anything(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        fsm.transition(CallState.WRAP_UP)
        # WRAP_UP is terminal — no valid transitions
        assert fsm.transition(CallState.GREETING) is False
        assert fsm.transition(CallState.QUALIFICATION) is False
        assert fsm.transition(CallState.NEGOTIATION) is False

    def test_negotiation_can_go_back_to_qualification(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        fsm.transition(CallState.NEGOTIATION)
        result = fsm.transition(CallState.QUALIFICATION)
        assert result is True
        assert fsm.current_state == CallState.QUALIFICATION

    def test_early_wrap_up_from_greeting(self):
        fsm = CallStateMachine()
        result = fsm.transition(CallState.WRAP_UP)
        assert result is True
        assert fsm.current_state == CallState.WRAP_UP

    def test_early_wrap_up_from_qualification(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        result = fsm.transition(CallState.WRAP_UP)
        assert result is True

    def test_early_wrap_up_from_negotiation(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        fsm.transition(CallState.NEGOTIATION)
        result = fsm.transition(CallState.WRAP_UP)
        assert result is True

    def test_can_transition_check(self):
        fsm = CallStateMachine()
        assert fsm.can_transition(CallState.QUALIFICATION) is True
        assert fsm.can_transition(CallState.NEGOTIATION) is False
        assert fsm.can_transition(CallState.WRAP_UP) is True

    def test_states_visited_tracking(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        fsm.transition(CallState.NEGOTIATION)
        fsm.transition(CallState.BOOKING)
        fsm.transition(CallState.WRAP_UP)
        assert fsm.context.states_visited == [
            "GREETING", "QUALIFICATION", "NEGOTIATION", "BOOKING", "WRAP_UP"
        ]

    def test_states_visited_with_backtrack(self):
        fsm = CallStateMachine()
        fsm.transition(CallState.QUALIFICATION)
        fsm.transition(CallState.NEGOTIATION)
        fsm.transition(CallState.QUALIFICATION)  # Go back
        fsm.transition(CallState.NEGOTIATION)    # Try again
        assert fsm.context.states_visited == [
            "GREETING", "QUALIFICATION", "NEGOTIATION", "QUALIFICATION", "NEGOTIATION"
        ]


class TestCallContext:
    """Tests for context accumulation during a call."""

    def test_context_stores_tenant_info(self):
        fsm = CallStateMachine(tenant_id="abc", company_name="ABC Logistics")
        assert fsm.context.tenant_id == "abc"
        assert fsm.context.company_name == "ABC Logistics"

    def test_context_driver_info(self):
        fsm = CallStateMachine()
        fsm.context.driver_mc_number = "MC123456"
        fsm.context.driver_name = "John Smith"
        fsm.context.driver_equipment = "Dry Van"
        assert fsm.context.driver_mc_number == "MC123456"
        assert fsm.context.driver_name == "John Smith"

    def test_context_load_info(self):
        fsm = CallStateMachine()
        fsm.context.selected_load_id = "1001"
        fsm.context.selected_lane_id = "IL-TX"
        assert fsm.context.selected_load_id == "1001"
        assert fsm.context.selected_lane_id == "IL-TX"

    def test_context_negotiation_tracking(self):
        fsm = CallStateMachine()
        fsm.context.base_rate = 2.50
        fsm.context.agreed_rate = 2.35
        fsm.context.negotiation_rounds = 2
        assert fsm.context.negotiation_rounds == 2

    def test_tool_invocation_recording(self):
        fsm = CallStateMachine()
        fsm.record_tool_invocation("search_loads")
        fsm.record_tool_invocation("get_rate")
        fsm.record_tool_invocation("negotiate_rate")
        assert fsm.context.tools_invoked == ["search_loads", "get_rate", "negotiate_rate"]

    def test_call_summary(self):
        fsm = CallStateMachine(tenant_id="abc", company_name="ABC")
        fsm.context.driver_mc_number = "MC123"
        fsm.context.booking_confirmed = True
        fsm.transition(CallState.QUALIFICATION)
        fsm.transition(CallState.NEGOTIATION)

        summary = fsm.get_call_summary()
        assert summary["tenant_id"] == "abc"
        assert summary["driver_mc"] == "MC123"
        assert summary["booking_confirmed"] is True
        assert summary["final_state"] == "NEGOTIATION"
        assert "call_id" in summary
        assert "duration_seconds" in summary

    def test_call_duration(self):
        fsm = CallStateMachine()
        duration = fsm.get_call_duration()
        assert duration >= 0.0

    def test_unique_call_ids(self):
        fsm1 = CallStateMachine()
        fsm2 = CallStateMachine()
        assert fsm1.context.call_id != fsm2.context.call_id


class TestTransitionMap:
    """Tests for the transition map configuration."""

    def test_all_states_have_entries(self):
        for state in CallState:
            assert state in TRANSITION_MAP

    def test_wrap_up_is_terminal(self):
        assert TRANSITION_MAP[CallState.WRAP_UP] == []

    def test_greeting_transitions(self):
        expected = [CallState.QUALIFICATION, CallState.WRAP_UP]
        assert TRANSITION_MAP[CallState.GREETING] == expected
