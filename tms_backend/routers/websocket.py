"""
Nexus Dispatch — WebSocket Router for Live Call Monitoring

Provides real-time WebSocket connections for:
- /ws/calls/live — Stream all active call events (transcript + status) for the tenant
- /ws/calls/{call_id} — Subscribe to a single call's transcript
- /ws/calls/{call_id}/whisper — Send text instructions to the AI mid-call

Uses Redis Pub/Sub as the message bus between agent workers and dashboard clients.
"""

import asyncio
import json
import os
import structlog
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import redis.asyncio as aioredis

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


# ── Connection Manager ──

class ConnectionManager:
    """Manages WebSocket connections grouped by tenant_id."""

    def __init__(self):
        # tenant_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # call_id -> set of WebSocket connections (for single-call subscriptions)
        self.call_connections: Dict[str, Set[WebSocket]] = {}
        self._redis: aioredis.Redis | None = None
        self._subscriber_task: asyncio.Task | None = None

    async def get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        self.active_connections[tenant_id].add(websocket)
        logger.info("WebSocket connected", tenant_id=tenant_id, total=len(self.active_connections[tenant_id]))

    async def connect_call(self, websocket: WebSocket, call_id: str):
        await websocket.accept()
        if call_id not in self.call_connections:
            self.call_connections[call_id] = set()
        self.call_connections[call_id].add(websocket)

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].discard(websocket)
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]

    def disconnect_call(self, websocket: WebSocket, call_id: str):
        if call_id in self.call_connections:
            self.call_connections[call_id].discard(websocket)
            if not self.call_connections[call_id]:
                del self.call_connections[call_id]

    async def broadcast_to_tenant(self, tenant_id: str, message: dict):
        """Send a message to all dashboard WebSockets subscribed to this tenant."""
        if tenant_id not in self.active_connections:
            return
        dead = set()
        for ws in self.active_connections[tenant_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active_connections[tenant_id].discard(ws)

    async def broadcast_to_call(self, call_id: str, message: dict):
        """Send a message to all WebSockets subscribed to a specific call."""
        if call_id not in self.call_connections:
            return
        dead = set()
        for ws in self.call_connections[call_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.call_connections[call_id].discard(ws)

    async def start_redis_subscriber(self):
        """Subscribe to Redis pub/sub and fan out messages to WebSocket clients."""
        if self._subscriber_task is not None:
            return  # Already running

        async def _subscribe():
            try:
                r = await self.get_redis()
                pubsub = r.pubsub()
                await pubsub.psubscribe("nexus:live:*")
                logger.info("Redis subscriber started for nexus:live:*")

                async for message in pubsub.listen():
                    if message["type"] != "pmessage":
                        continue
                    try:
                        channel = message["channel"]
                        data = json.loads(message["data"])
                        tenant_id = data.get("tenant_id", "")
                        call_id = data.get("call_id", "")

                        # Broadcast to tenant-level subscribers
                        await self.broadcast_to_tenant(tenant_id, data)

                        # Broadcast to call-level subscribers
                        if call_id:
                            await self.broadcast_to_call(call_id, data)

                    except Exception as e:
                        logger.error("Error processing Redis message", error=str(e))
            except Exception as e:
                logger.error("Redis subscriber crashed", error=str(e))
                # Retry after delay
                await asyncio.sleep(5)
                self._subscriber_task = asyncio.create_task(_subscribe())

        self._subscriber_task = asyncio.create_task(_subscribe())

    async def stop_redis_subscriber(self):
        if self._subscriber_task:
            self._subscriber_task.cancel()
            self._subscriber_task = None


manager = ConnectionManager()


# ── WebSocket Endpoints ──

@router.websocket("/ws/calls/live")
async def ws_live_calls(websocket: WebSocket, token: str = Query("")):
    """
    Stream all active call events for the authenticated tenant.

    Messages sent to the client:
    - {"type": "transcript", "call_id": "...", "speaker": "user|agent", "text": "..."}
    - {"type": "call_started", "call_id": "...", "driver_name": "...", "driver_mc": "..."}
    - {"type": "call_ended", "call_id": "...", "outcome": "..."}
    - {"type": "state_changed", "call_id": "...", "new_state": "..."}
    - {"type": "alert", "call_id": "...", "level": "warning|critical", "message": "..."}
    """
    # Validate token (simplified — in production use proper JWT validation)
    from auth import decode_token
    try:
        payload = decode_token(token)
        tenant_id = payload.get("tenant_id", "")
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if not tenant_id:
        await websocket.close(code=4002, reason="No tenant_id in token")
        return

    # Ensure Redis subscriber is running
    await manager.start_redis_subscriber()

    await manager.connect(websocket, tenant_id)
    try:
        # Send current active calls snapshot
        try:
            r = await manager.get_redis()
            active_calls_raw = await r.smembers(f"nexus:active_calls:{tenant_id}")
            active_calls = []
            for call_id in active_calls_raw:
                call_data = await r.hgetall(f"nexus:call:{call_id}")
                if call_data:
                    active_calls.append(call_data)
            await websocket.send_json({
                "type": "snapshot",
                "active_calls": active_calls,
            })
        except Exception as e:
            logger.debug("Could not send snapshot", error=str(e))

        # Keep connection alive — listen for client messages
        while True:
            data = await websocket.receive_text()
            # Client can send ping/pong or whisper commands
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg.get("type") == "whisper":
                    # Forward whisper to the agent via Redis
                    call_id = msg.get("call_id")
                    text = msg.get("text", "")
                    if call_id and text:
                        r = await manager.get_redis()
                        await r.publish(
                            f"nexus:whisper:{call_id}",
                            json.dumps({"text": text, "from": "dashboard"})
                        )
                        await websocket.send_json({
                            "type": "whisper_sent",
                            "call_id": call_id,
                            "text": text,
                        })
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)
        logger.info("WebSocket disconnected", tenant_id=tenant_id)


@router.websocket("/ws/calls/{call_id}")
async def ws_single_call(websocket: WebSocket, call_id: str, token: str = Query("")):
    """Subscribe to a single call's live transcript."""
    from auth import decode_token
    try:
        payload = decode_token(token)
        tenant_id = payload.get("tenant_id", "")
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.start_redis_subscriber()
    await manager.connect_call(websocket, call_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect_call(websocket, call_id)
