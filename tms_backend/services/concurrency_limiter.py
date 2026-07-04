"""
Nexus Dispatch — Concurrent Call Limiter

Redis-backed rate limiter that enforces max_concurrent_calls per tenant.
Used by the agent worker to check capacity before accepting new SIP sessions.

Usage in agent.py:
    limiter = ConcurrencyLimiter()
    if not await limiter.acquire(tenant_id, max_calls):
        # Reject call — at capacity
        return
    try:
        await run_call(...)
    finally:
        await limiter.release(tenant_id)
"""

import os
import structlog
import redis.asyncio as aioredis

logger = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class ConcurrencyLimiter:
    """
    Redis-backed concurrent call limiter.
    
    Uses a Redis SET to track active call IDs per tenant.
    Atomic check-and-add via Lua script to prevent race conditions.
    """

    def __init__(self, redis_url: str = ""):
        self._redis = aioredis.from_url(redis_url or REDIS_URL, decode_responses=True)

    def _key(self, tenant_id: str) -> str:
        return f"nexus:active_calls:{tenant_id}"

    async def acquire(self, tenant_id: str, call_id: str, max_concurrent: int) -> bool:
        """
        Try to acquire a slot for a new call.
        
        Returns True if the call was accepted (under limit).
        Returns False if the tenant has reached max_concurrent_calls.
        """
        key = self._key(tenant_id)
        
        # Lua script for atomic check-and-add
        # This prevents race conditions between checking count and adding
        lua_script = """
        local current = redis.call('SCARD', KEYS[1])
        if current < tonumber(ARGV[1]) then
            redis.call('SADD', KEYS[1], ARGV[2])
            return 1
        else
            return 0
        end
        """
        
        try:
            result = await self._redis.eval(lua_script, 1, key, str(max_concurrent), call_id)
            
            if result == 1:
                logger.info(
                    "Call slot acquired",
                    tenant_id=tenant_id,
                    call_id=call_id,
                    active_after=await self.get_active_count(tenant_id),
                    max_concurrent=max_concurrent,
                )
                return True
            else:
                logger.warning(
                    "Call rejected — at capacity",
                    tenant_id=tenant_id,
                    call_id=call_id,
                    active=await self.get_active_count(tenant_id),
                    max_concurrent=max_concurrent,
                )
                return False
        except Exception as e:
            logger.error("Concurrency limiter error", error=str(e), tenant_id=tenant_id)
            # Fail open — accept the call if Redis is down
            return True

    async def release(self, tenant_id: str, call_id: str):
        """Release a call slot when the call ends."""
        key = self._key(tenant_id)
        try:
            await self._redis.srem(key, call_id)
            logger.info(
                "Call slot released",
                tenant_id=tenant_id,
                call_id=call_id,
                active_after=await self.get_active_count(tenant_id),
            )
        except Exception as e:
            logger.error("Failed to release call slot", error=str(e), tenant_id=tenant_id)

    async def get_active_count(self, tenant_id: str) -> int:
        """Get the number of currently active calls for a tenant."""
        try:
            return await self._redis.scard(self._key(tenant_id))
        except Exception:
            return 0

    async def get_active_calls(self, tenant_id: str) -> set:
        """Get the set of active call IDs for a tenant."""
        try:
            return await self._redis.smembers(self._key(tenant_id))
        except Exception:
            return set()

    async def cleanup_stale(self, tenant_id: str, valid_call_ids: set):
        """
        Remove any call IDs from Redis that are no longer actually active.
        Call this periodically to clean up calls that crashed without releasing.
        """
        key = self._key(tenant_id)
        try:
            stored = await self._redis.smembers(key)
            stale = stored - valid_call_ids
            if stale:
                await self._redis.srem(key, *stale)
                logger.info(
                    "Cleaned up stale call slots",
                    tenant_id=tenant_id,
                    removed=len(stale),
                    stale_ids=list(stale),
                )
        except Exception as e:
            logger.error("Failed to cleanup stale calls", error=str(e))
