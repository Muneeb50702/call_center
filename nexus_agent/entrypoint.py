import structlog
from livekit.agents import cli, WorkerOptions

from config.logging_config import setup_logging
from agent import prewarm, run_agent

setup_logging()
logger = structlog.get_logger()

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=run_agent,
            # Loads the VAD, the embedding model, and every tenant's knowledge
            # index once per worker process. Without this, the first caller of
            # each process waits through model initialisation on their first turn.
            prewarm_fnc=prewarm,
            # LiveKit's default is 10s, which prewarm exceeded when a knowledge
            # index had to be embedded from scratch (~10s for 122 chunks) — the
            # process was killed mid-load and every job failed. The vector cache
            # (rag/cache.py) normally keeps prewarm well under a second; this
            # raised budget is the backstop for a genuine cold build, e.g. a
            # first run before the cache exists or right after a corpus edit.
            initialize_process_timeout=60.0,
            # Keep a warmed process ready. Without this the first caller after a
            # deploy hits "no warmed process available for job" and waits through
            # VAD + embedding-model + index load before the agent says a word —
            # which, on a demo where the first impression is the product, is the
            # worst possible place to spend several seconds.
            num_idle_processes=1,
            agent_name="nexus-agent",
        )
    )
