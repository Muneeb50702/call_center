"""
Nexus Dispatch — Pipeline Hooks & Observability

Hooks into the LiveKit AgentSession event system for:
- End-to-end latency measurement (user speech end → agent speech start)
- Barge-in detection logging
- Tool execution timing
- Call duration tracking
- State transition logging

All metrics are emitted as structured JSON via structlog for ingestion
by any monitoring stack (Datadog, Grafana, CloudWatch, etc.).
"""

import time
import structlog

from state.machine import CallStateMachine

logger = structlog.get_logger()


def setup_hooks(session, state_machine: CallStateMachine | None = None):
    """
    Wire observability hooks into the AgentSession.
    
    Args:
        session: The LiveKit AgentSession instance.
        state_machine: Optional CallStateMachine for enriched logging.
    """
    # Timing state for latency measurement
    timing = {
        "user_speech_end_time": None,
        "agent_speech_start_time": None,
        "tool_start_times": {},
    }

    call_id = state_machine.context.call_id if state_machine else "unknown"

    # ── User Speech Events ──

    @session.on("user_speech_started")
    def on_user_speech_started():
        logger.info(
            "user_speech_started",
            call_id=call_id,
            event="barge_in_possible",
            current_state=state_machine.current_state.value if state_machine else "unknown",
        )

    @session.on("user_speech_finished")
    def on_user_speech_finished():
        timing["user_speech_end_time"] = time.monotonic()
        logger.debug(
            "user_speech_finished",
            call_id=call_id,
        )

    # ── Agent Speech Events ──

    @session.on("agent_speech_started")
    def on_agent_speech_started():
        timing["agent_speech_start_time"] = time.monotonic()

        # Calculate end-to-end latency
        if timing["user_speech_end_time"] is not None:
            e2e_latency_ms = round(
                (timing["agent_speech_start_time"] - timing["user_speech_end_time"]) * 1000
            )
            logger.info(
                "latency_metric",
                call_id=call_id,
                metric="e2e_latency_ms",
                value=e2e_latency_ms,
                current_state=state_machine.current_state.value if state_machine else "unknown",
            )
            # Reset for next turn
            timing["user_speech_end_time"] = None

    @session.on("agent_speech_finished")
    def on_agent_speech_finished():
        logger.debug(
            "agent_speech_finished",
            call_id=call_id,
        )

    # ── Function Call Events (Tool Execution) ──

    if hasattr(session, "llm_node") and session.llm_node:
        @session.llm_node.on("function_call_start")
        def on_function_call_start(tool):
            tool_name = str(tool)
            timing["tool_start_times"][tool_name] = time.monotonic()
            logger.info(
                "tool_execution_started",
                call_id=call_id,
                tool=tool_name,
                current_state=state_machine.current_state.value if state_machine else "unknown",
            )

        @session.llm_node.on("function_call_end")
        def on_function_call_end(tool, result):
            tool_name = str(tool)
            start_time = timing["tool_start_times"].pop(tool_name, None)
            duration_ms = 0
            if start_time:
                duration_ms = round((time.monotonic() - start_time) * 1000)

            logger.info(
                "tool_execution_finished",
                call_id=call_id,
                tool=tool_name,
                duration_ms=duration_ms,
                current_state=state_machine.current_state.value if state_machine else "unknown",
            )
