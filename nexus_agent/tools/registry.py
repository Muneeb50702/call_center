from tools.tms_tools import TMSTools

tms_tools = TMSTools()

def get_tools_for_state(state: str) -> list:
    """
    Returns a list of @function_tool decorated functions
    based on the current conversation state.
    """
    if state == "GREETING" or state == "WRAP_UP":
        return []
    elif state == "QUALIFICATION":
        return [tms_tools.search_loads, tms_tools.check_driver_availability]
    elif state == "NEGOTIATION":
        return [tms_tools.get_rate, tms_tools.negotiate_rate]
    elif state == "BOOKING":
        return [tms_tools.lookup_load]
    
    # Default fallback
    return [
        tms_tools.lookup_load,
        tms_tools.search_loads,
        tms_tools.get_rate,
        tms_tools.negotiate_rate,
        tms_tools.check_driver_availability
    ]
