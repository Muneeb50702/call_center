"""
Nexus Dispatch — Pipeline Hooks & Observability (LiveKit Agents 1.x)

Wires the AgentSession event stream to:
- Live transcript + state publishing to Redis (channel nexus:live:{tenant}) for the
  dashboard live-monitor.
- End-to-end latency capture via `metrics_collected`.
- Tool-output capture into the per-turn grounding facts (feeds the anti-hallucination
  verifier in state/agents.py).
- Structured logging.

This replaces the pre-1.0 event names (`user_speech_committed`, `agent_speech_*`,
`session.llm_node.on(...)`) and the `transition_to` monkeypatch — all of which
silently no-op'd on livekit-agents 1.x, so the live monitor never showed anything.

Verified against livekit-agents 1.6.5 event surface:
  user_input_transcribed · conversation_item_added · metrics_collected ·
  function_tools_executed · agent_state_changed · error
"""

import asyncio
import json
import os
import structlog

from livekit.agents import metrics as lk_metrics
from state.machine import CallStateMachine, CallState

logger = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def setup_hooks(
    session,
    state_machine: CallStateMachine | None = None,
    analytics=None,
    redis_client=None,
    telemetry=None,
):
    """Attach observability hooks to a running AgentSession.

    Args:
        session: the LiveKit AgentSession.
        state_machine: per-call CallStateMachine (for context + transcript accrual).
        analytics: optional CallAnalytics to receive latency samples.
        redis_client: optional shared redis.asyncio client. If None, one is created
            (the caller owns closing whichever it passed).
        telemetry: optional TurnTelemetry. When present, every event published to
            the supervisor dashboard is also published to the room's data channel,
            which is what the demo page's live HUD renders.
    """
    if redis_client is None:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

    ctx = state_machine.context if state_machine else None
    call_id = ctx.call_id if ctx else "unknown"
    tenant_id = ctx.tenant_id if ctx else "unknown"

    def _publish(message: dict):
        # The dashboard consumes Redis; the demo page consumes the room data
        # channel. Same event stream, two transports.
        if telemetry is not None:
            telemetry.publish(message)

        async def _do():
            try:
                payload = {**message, "tenant_id": tenant_id, "call_id": call_id}
                await redis_client.publish(f"nexus:live:{tenant_id}", json.dumps(payload))
            except Exception as e:
                logger.debug("redis publish failed", error=str(e))
        try:
            asyncio.create_task(_do())
        except RuntimeError:
            pass  # no running loop (shouldn't happen inside the session)

    # ── State transitions (replaces the broken monkeypatch) ──
    if state_machine is not None:
        def _on_transition(previous: CallState, new: CallState):
            _publish({"type": "state_changed", "old_state": previous.value, "new_state": new.value})
        state_machine.on_transition = _on_transition

    # ── User transcript (partial + final) ──
    @session.on("user_input_transcribed")
    def _on_user_transcribed(ev):
        text = getattr(ev, "transcript", "") or ""
        is_final = bool(getattr(ev, "is_final", False))
        _publish({"type": "transcript", "speaker": "user", "text": text, "is_final": is_final})
        if is_final and ctx is not None and text.strip():
            ctx.transcript.append({"speaker": "user", "text": text})

    # ── Committed messages (we publish the agent's finished turns) ──
    @session.on("conversation_item_added")
    def _on_item_added(ev):
        item = getattr(ev, "item", None)
        role = getattr(item, "role", None)
        text = getattr(item, "text_content", None) or ""
        if role == "assistant" and text.strip():
            _publish({"type": "transcript", "speaker": "agent", "text": text})
            if ctx is not None:
                ctx.transcript.append({"speaker": "agent", "text": text})

    # ── Latency / usage metrics ──
    @session.on("metrics_collected")
    def _on_metrics(ev):
        m = getattr(ev, "metrics", None)
        try:
            lk_metrics.log_metrics(m)
        except Exception:
            pass

        # Assemble the true per-turn breakdown (EOU + LLM TTFT + TTS TTFB). The
        # telemetry object publishes a turn once all three stages have reported.
        if telemetry is not None:
            try:
                telemetry.record(m)
            except Exception as e:
                logger.debug("telemetry record failed", error=str(e))

        # Keep feeding TTFT to the legacy analytics store so the existing
        # dashboard charts keep working.
        ttft = getattr(m, "ttft", None)
        if ttft and ttft > 0 and not getattr(m, "cancelled", False):
            ms = round(ttft * 1000)
            if analytics is not None:
                analytics.record_latency(ms)
            _publish({"type": "latency", "metric": "ttft_ms", "value": ms})

    # ── Tool executions → grounding facts (anti-hallucination) + trace ──
    @session.on("function_tools_executed")
    def _on_tools(ev):
        try:
            pairs = list(ev.zipped())
        except Exception:
            pairs = []
        for call, out in pairs:
            name = getattr(call, "name", "tool")
            output = getattr(out, "output", None) if out is not None else None
            if state_machine is not None and output:
                # The verifier only lets the agent speak values present in these outputs.
                state_machine.add_turn_fact(output)
            _publish({"type": "tool", "name": name})
            logger.info("tool_executed", call_id=call_id, tool=name)

            # Retrieval gets its own event: the demo HUD shows which chunks
            # grounded the answer, which is the whole argument that the agent is
            # reading from the client's site rather than improvising.
            if name == "search_knowledge_base" and ctx is not None:
                _publish({
                    "type": "kb_retrieval",
                    "sources": ctx.kb_last_sources,
                    "latency_ms": ctx.kb_last_latency_ms,
                    "queries": ctx.kb_queries,
                    "misses": ctx.kb_misses,
                    "hit": bool(ctx.kb_last_sources),
                })

    # ── Agent state (initializing/idle/listening/thinking/speaking) ──
    @session.on("agent_state_changed")
    def _on_agent_state(ev):
        _publish({"type": "agent_state", "state": getattr(ev, "new_state", "")})

    # ── Pipeline errors ──
    @session.on("error")
    def _on_error(ev):
        err = str(getattr(ev, "error", "error"))
        _publish({"type": "alert", "level": "warning", "message": err})
        logger.warning("session_error", call_id=call_id, error=err)

    logger.info("Pipeline hooks wired (livekit-agents 1.x)", call_id=call_id, tenant_id=tenant_id)
    return redis_client
