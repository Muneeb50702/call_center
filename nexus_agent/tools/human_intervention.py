"""
Nexus Dispatch — Human Intervention Subsystem

Listens to Redis for mid-call instructions (whispers) from human operators
and injects them into the agent's LLM context.
"""

import asyncio
import json
import os
import structlog
import redis.asyncio as aioredis
from livekit.agents.llm import ChatMessage, ChatRole

logger = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class HumanInterventionService:
    def __init__(self, session, call_id: str):
        self.session = session
        self.call_id = call_id
        self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self._task = None

    def start(self):
        """Start listening for dashboard whispers in the background."""
        self._task = asyncio.create_task(self._listen())
        logger.info("Human intervention listener started", call_id=self.call_id)

    def stop(self):
        """Stop listening."""
        if self._task:
            self._task.cancel()
            self._task = None

    async def _listen(self):
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(f"nexus:whisper:{self.call_id}")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    text = data.get("text")
                    if text and hasattr(self.session, "chat_ctx"):
                        logger.info("Received whisper from dashboard", call_id=self.call_id, text=text)
                        
                        # Inject the whisper as a system prompt into the active chat context
                        instruction = (
                            f"[URGENT INSTRUCTION FROM YOUR MANAGER]: {text}\n"
                            "Acknowledge this internally and weave this instruction into your next response naturally."
                        )
                        
                        self.session.chat_ctx.messages.append(
                            ChatMessage(
                                role=ChatRole.SYSTEM,
                                content=instruction
                            )
                        )
                        
                        # If the agent is idle, we could force a turn, but usually 
                        # the driver is talking or will talk soon. If we need to force
                        # the agent to speak immediately, we can generate a turn:
                        # asyncio.create_task(self.session.generate_reply())
                        # For now, just injecting it into context is safest.
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in human intervention listener", error=str(e))
