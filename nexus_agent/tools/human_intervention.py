"""
Nexus Dispatch — Human Intervention Subsystem (LiveKit Agents 1.x)

Listens on Redis for mid-call "whispers" from a human supervisor in the dashboard
and injects them into the live agent as an instruction for its next reply.

The pre-1.0 approach (mutating `session.chat_ctx.messages`) silently no-op'd on
1.x because `chat_ctx` is a read-only copy. The 1.x path is
`session.generate_reply(instructions=...)`, which steers the agent's next turn
without a fragile handle to the (possibly since-handed-off) current agent.
"""

import asyncio
import json
import os
import structlog
import redis.asyncio as aioredis

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
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                except (ValueError, TypeError):
                    continue
                text = (data.get("text") or "").strip()
                if not text:
                    continue

                logger.info("Received whisper from dashboard", call_id=self.call_id, text=text)
                instruction = (
                    "A senior human dispatcher supervising this call has given you this "
                    f"instruction — follow it naturally in your next response: {text}"
                )
                try:
                    # Steers the agent's next reply. Respects turn-taking / interruptions.
                    self.session.generate_reply(instructions=instruction)
                except Exception as e:
                    logger.error("Failed to apply whisper", call_id=self.call_id, error=str(e))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error in human intervention listener", error=str(e))
        finally:
            try:
                await self._redis.aclose()
            except Exception:
                pass
