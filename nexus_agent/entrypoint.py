import asyncio
import structlog
from livekit.agents import cli, AgentServer
from config.logging_config import setup_logging
from agent import run_agent

setup_logging()
logger = structlog.get_logger()

server = AgentServer()

@server.rtc_session(agent_name="nexus-agent")
async def handle_session(ctx):
    """
    Entrypoint for new LiveKit rooms.
    The AgentServer natively dispatches incoming SIP calls here based on agent_name.
    """
    logger.info("Handling new RTC session", room_name=ctx.room.name)
    try:
        await run_agent(ctx)
    except Exception as e:
        logger.exception("Error running agent session", error=str(e))

if __name__ == "__main__":
    cli.run_app(server)
