import structlog
import time

logger = structlog.get_logger()

def setup_hooks(session):
    """
    Hooks into the AgentSession event system to handle barge-in logging
    and latency metrics gathering.
    """
    
    @session.on("user_speech_started")
    def on_user_speech_started():
        logger.info("User speech started - possible barge-in detected")

    @session.on("agent_speech_finished")
    def on_agent_speech_finished():
        logger.info("Agent finished speaking")

    # Access pipeline nodes if needed
    if hasattr(session, "llm_node") and session.llm_node:
        @session.llm_node.on("function_call_start")
        def on_function_call_start(tool):
            logger.info("Function call started", tool=tool)

        @session.llm_node.on("function_call_end")
        def on_function_call_end(tool, result):
            logger.info("Function call ended", tool=tool)
