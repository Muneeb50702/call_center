"""
Nexus Dispatch — Call Analytics Pipeline

Accumulates per-call metrics and flushes them to Redis for
cross-worker aggregation and future dashboard consumption.

Metrics tracked:
- Call duration
- States visited
- Tools invoked  
- Negotiation outcome (accepted/rejected/transferred)
- End-to-end latency samples
- Transfer events
"""

import json
import time
from dataclasses import dataclass, field
import structlog

from state.machine import CallStateMachine

logger = structlog.get_logger()


@dataclass
class CallMetrics:
    """Accumulated metrics for a single call."""
    latency_samples_ms: list[int] = field(default_factory=list)
    tool_durations_ms: dict[str, list[int]] = field(default_factory=dict)
    state_durations_s: dict[str, float] = field(default_factory=dict)
    _state_entry_time: float = field(default_factory=time.time)


class CallAnalytics:
    """
    Analytics collector for a single call.
    Accumulates metrics during the call and flushes at wrap-up.
    """

    def __init__(self, state_machine: CallStateMachine, redis_client=None):
        self.fsm = state_machine
        self._redis = redis_client
        self._metrics = CallMetrics()
        self._start_time = time.time()

    def record_latency(self, e2e_latency_ms: int):
        """Record an end-to-end latency sample."""
        self._metrics.latency_samples_ms.append(e2e_latency_ms)

    def record_tool_duration(self, tool_name: str, duration_ms: int):
        """Record how long a tool execution took."""
        if tool_name not in self._metrics.tool_durations_ms:
            self._metrics.tool_durations_ms[tool_name] = []
        self._metrics.tool_durations_ms[tool_name].append(duration_ms)

    def record_state_entry(self):
        """Mark the current time as the entry point for the current state."""
        self._metrics._state_entry_time = time.time()

    def record_state_exit(self, state_name: str):
        """Record how long was spent in the given state."""
        duration = time.time() - self._metrics._state_entry_time
        self._metrics.state_durations_s[state_name] = round(duration, 2)

    def build_report(self) -> dict:
        """Build the final analytics report for this call."""
        call_summary = self.fsm.get_call_summary()

        # Compute latency stats
        latencies = self._metrics.latency_samples_ms
        latency_stats = {}
        if latencies:
            latency_stats = {
                "avg_ms": round(sum(latencies) / len(latencies)),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
                "p95_ms": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0],
                "samples": len(latencies),
            }

        return {
            **call_summary,
            "latency_stats": latency_stats,
            "tool_durations_ms": self._metrics.tool_durations_ms,
            "state_durations_s": self._metrics.state_durations_s,
            "report_generated_at": time.time(),
        }

    async def flush_to_redis(self):
        """Push the call analytics to Redis for aggregation."""
        if not self._redis:
            # Fallback: just log the report
            report = self.build_report()
            logger.info(
                "call_analytics_report",
                **report,
            )
            return

        try:
            report = self.build_report()
            call_id = self.fsm.context.call_id
            tenant_id = self.fsm.context.tenant_id

            # Store individual call report
            await self._redis.set(
                f"nexus:analytics:call:{call_id}",
                json.dumps(report),
                ex=86400 * 30,  # Expire after 30 days
            )

            # Push to tenant's call list for dashboard queries
            await self._redis.lpush(
                f"nexus:analytics:tenant:{tenant_id}:calls",
                call_id,
            )
            await self._redis.ltrim(
                f"nexus:analytics:tenant:{tenant_id}:calls",
                0,
                9999,  # Keep last 10K calls
            )

            # Increment counters
            await self._redis.incr(f"nexus:analytics:tenant:{tenant_id}:total_calls")
            if self.fsm.context.booking_confirmed:
                await self._redis.incr(f"nexus:analytics:tenant:{tenant_id}:bookings")
            if self.fsm.context.transferred_to_human:
                await self._redis.incr(f"nexus:analytics:tenant:{tenant_id}:transfers")

            logger.info(
                "Analytics flushed to Redis",
                call_id=call_id,
                tenant_id=tenant_id,
            )
        except Exception as e:
            logger.exception("Failed to flush analytics to Redis", error=str(e))
            # Don't fail the call — analytics are non-critical
