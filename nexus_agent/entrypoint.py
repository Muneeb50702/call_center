import asyncio
import structlog
from livekit.agents import cli, WorkerOptions
from config.logging_config import setup_logging
from agent import run_agent

setup_logging()
logger = structlog.get_logger()

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=run_agent,
            agent_name="nexus-agent"
        )
    )
