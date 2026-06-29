import structlog
from livekit.agents import AgentSession, Agent, JobContext, AutoSubscribe
from llm.groq_client import create_groq_llm
from llm.prompts import GREETING_PROMPT
from stt.deepgram_stt import create_stt
from tts.deepgram_tts import create_tts
from vad.silero_vad import create_vad
from tools.registry import get_tools_for_state
from pipeline.hooks import setup_hooks

logger = structlog.get_logger()

async def run_agent(ctx: JobContext):
    """
    Initializes and starts the LiveKit AgentSession for a given room.
    """
    # Connect to room
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    logger.info("Agent connected to room", room_name=ctx.room.name)
    
    # Instantiate plugins
    llm = create_groq_llm()
    stt = create_stt()
    tts = create_tts()
    vad = create_vad()
    
    # Setup initial state and tools
    initial_state = "GREETING"
    tools = get_tools_for_state(initial_state)
    
    # Define the Agent
    agent = Agent(
        instructions=GREETING_PROMPT,
        tools=tools
    )
    
    # Initialize the session orchestrator
    session = AgentSession(
        llm=llm,
        stt=stt,
        tts=tts,
        vad=vad
    )
    
    # Wire pipeline hooks
    setup_hooks(session)
    
    # Kick off the session
    await session.start(room=ctx.room, agent=agent)
    logger.info("Agent session started")
