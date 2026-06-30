"""
Nexus Dispatch — Tool Registry (Utility Module)

In the new architecture, each Agent subclass defines its own tools inline.
This module is kept as a utility for:
- Dynamic tool loading in fallback/test scenarios
- Listing all available tools for diagnostics
"""

from state.machine import CallState


def get_available_tool_names_for_state(state: str) -> list[str]:
    """
    Returns a list of tool names available in a given state.
    Useful for diagnostics, logging, and the admin dashboard.
    """
    state_tools = {
        CallState.GREETING: [
            "transition_to_qualification",
            "transfer_to_human",
        ],
        CallState.QUALIFICATION: [
            "search_loads",
            "check_driver_availability",
            "lookup_driver_by_mc",
            "transition_to_negotiation",
            "wrap_up_no_match",
            "transfer_to_human",
        ],
        CallState.NEGOTIATION: [
            "get_rate",
            "negotiate_rate",
            "transition_to_booking",
            "go_back_to_qualification",
            "transfer_to_human",
        ],
        CallState.BOOKING: [
            "lookup_load",
            "confirm_booking",
            "transition_to_wrap_up",
            "transfer_to_human",
        ],
        CallState.WRAP_UP: [
            "end_call",
        ],
    }
    try:
        return state_tools.get(CallState(state), [])
    except ValueError:
        return []
