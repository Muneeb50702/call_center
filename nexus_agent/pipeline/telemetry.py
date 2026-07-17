"""
Nexus — Per-turn latency telemetry

Assembles a true, per-turn latency breakdown and streams it to the browser over
the LiveKit data channel, which is what the demo HUD renders.

The existing analytics only ever recorded LLM TTFT. TTFT is the most *quotable*
number but it is a minority of what a caller actually waits through:

    caller stops speaking
      │
      ├── end_of_utterance_delay   VAD silence + semantic turn detection
      ├── llm.ttft                 thinking (plus any tool round-trips)
      └── tts.ttfb                 first audio byte
      │
    caller hears the first syllable

Reporting only `ttft` on a pipeline whose VAD waited 800ms would have claimed
~400ms while the caller sat through more than a second of silence. So this sums
the three stages a human actually experiences, and publishes the breakdown rather
than just the total — the breakdown is what makes the number credible to a
technical buyer, and it is what tells you which stage to fix.

Correlation is by `speech_id`, which LiveKit stamps on EOU, LLM and TTS metrics
belonging to the same turn. Turns are emitted only once all three stages have
reported, so the HUD never shows a half-built number.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()

# The topic the demo page subscribes to.
TELEMETRY_TOPIC = "nexus.telemetry"

# Turns are dropped from the pending map after this long. A cancelled or
# interrupted turn never completes all three stages, and without eviction the map
# would grow for the life of the call.
TURN_TTL_SECONDS = 30.0


@dataclass
class TurnLatency:
    """One conversational turn's latency, assembled from several metric events."""

    speech_id: str
    started_at: float = field(default_factory=time.time)

    eou_delay_ms: float | None = None
    transcription_delay_ms: float | None = None
    llm_ttft_ms: float | None = None
    tts_ttfb_ms: float | None = None

    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0

    @property
    def is_complete(self) -> bool:
        return None not in (self.eou_delay_ms, self.llm_ttft_ms, self.tts_ttfb_ms)

    @property
    def total_ms(self) -> float:
        """What the caller actually waited: silence, then thinking, then speech."""
        return sum(v for v in (self.eou_delay_ms, self.llm_ttft_ms, self.tts_ttfb_ms) if v)

    @property
    def cache_hit_rate(self) -> float | None:
        """Share of prompt tokens served from the LLM's prefix cache.

        Directly visible in TTFT: the shared prompt prefix across agent handoffs
        exists to make this number high.
        """
        if not self.prompt_tokens:
            return None
        return round(self.cached_tokens / self.prompt_tokens, 3)

    def to_dict(self) -> dict:
        return {
            "speech_id": self.speech_id,
            "eou_delay_ms": round(self.eou_delay_ms or 0, 1),
            "transcription_delay_ms": round(self.transcription_delay_ms or 0, 1),
            "llm_ttft_ms": round(self.llm_ttft_ms or 0, 1),
            "tts_ttfb_ms": round(self.tts_ttfb_ms or 0, 1),
            "total_ms": round(self.total_ms, 1),
            "prompt_tokens": self.prompt_tokens,
            "cached_tokens": self.cached_tokens,
            "completion_tokens": self.completion_tokens,
            "cache_hit_rate": self.cache_hit_rate,
        }


class TurnTelemetry:
    """Correlates metric events into per-turn latency and publishes to the room.

    Every publish is best-effort: telemetry must never be able to break a call.
    """

    def __init__(self, room=None, call_id: str = ""):
        self._room = room
        self._call_id = call_id
        self._pending: dict[str, TurnLatency] = {}
        self._completed: list[TurnLatency] = []

    # ── Publishing ──

    def publish(self, payload: dict) -> None:
        """Fire-and-forget a JSON message to every participant in the room."""
        if self._room is None:
            return

        async def _send():
            try:
                await self._room.local_participant.publish_data(
                    json.dumps({**payload, "call_id": self._call_id}).encode(),
                    reliable=True,
                    topic=TELEMETRY_TOPIC,
                )
            except Exception as e:
                logger.debug("telemetry publish failed", error=str(e))

        try:
            asyncio.create_task(_send())
        except RuntimeError:
            pass  # no running loop; nothing to publish to anyway

    # ── Metric ingestion ──

    def _turn(self, speech_id: str) -> TurnLatency:
        turn = self._pending.get(speech_id)
        if turn is None:
            turn = TurnLatency(speech_id=speech_id)
            self._pending[speech_id] = turn
            self._evict_stale()
        return turn

    def _evict_stale(self) -> None:
        cutoff = time.time() - TURN_TTL_SECONDS
        for speech_id in [k for k, v in self._pending.items() if v.started_at < cutoff]:
            self._pending.pop(speech_id, None)

    def record(self, metric) -> None:
        """Feed one LiveKit metric event in. Emits a turn once all stages report."""
        kind = getattr(metric, "type", "")
        speech_id = getattr(metric, "speech_id", None)

        if kind == "eou_metrics" and speech_id:
            turn = self._turn(speech_id)
            turn.eou_delay_ms = getattr(metric, "end_of_utterance_delay", 0.0) * 1000
            turn.transcription_delay_ms = getattr(metric, "transcription_delay", 0.0) * 1000

        elif kind == "llm_metrics" and speech_id:
            # A cancelled generation is a barge-in, not a turn. Its TTFT is
            # meaningless and would drag the average down.
            if getattr(metric, "cancelled", False):
                self._pending.pop(speech_id, None)
                return
            turn = self._turn(speech_id)
            turn.llm_ttft_ms = getattr(metric, "ttft", 0.0) * 1000
            turn.prompt_tokens = getattr(metric, "prompt_tokens", 0)
            turn.cached_tokens = getattr(metric, "prompt_cached_tokens", 0)
            turn.completion_tokens = getattr(metric, "completion_tokens", 0)

        elif kind == "tts_metrics" and speech_id:
            if getattr(metric, "cancelled", False):
                self._pending.pop(speech_id, None)
                return
            turn = self._turn(speech_id)
            # A turn can synthesize several segments; the caller only waits for
            # the first, so never overwrite it with a later segment's TTFB.
            if turn.tts_ttfb_ms is None:
                turn.tts_ttfb_ms = getattr(metric, "ttfb", 0.0) * 1000
        else:
            return

        turn = self._pending.get(speech_id)
        if turn is not None and turn.is_complete:
            self._pending.pop(speech_id, None)
            self._completed.append(turn)
            self.publish({"type": "turn_latency", **turn.to_dict()})
            logger.info(
                "turn_latency",
                call_id=self._call_id,
                total_ms=round(turn.total_ms),
                eou_ms=round(turn.eou_delay_ms or 0),
                ttft_ms=round(turn.llm_ttft_ms or 0),
                tts_ttfb_ms=round(turn.tts_ttfb_ms or 0),
                cache_hit_rate=turn.cache_hit_rate,
            )

    # ── Aggregates ──

    @property
    def turns(self) -> list[TurnLatency]:
        return list(self._completed)

    def summary(self) -> dict:
        """Call-level latency stats over completed turns."""
        if not self._completed:
            return {}

        def pct(values: list[float], p: float) -> float:
            if not values:
                return 0.0
            ordered = sorted(values)
            # Nearest-rank; with the handful of turns in a demo call, interpolating
            # would imply a precision that is not there.
            return ordered[min(int(len(ordered) * p), len(ordered) - 1)]

        totals = [t.total_ms for t in self._completed]
        rates = [t.cache_hit_rate for t in self._completed if t.cache_hit_rate is not None]
        return {
            "turns": len(self._completed),
            "avg_ms": round(sum(totals) / len(totals), 1),
            "p50_ms": round(pct(totals, 0.5), 1),
            "p95_ms": round(pct(totals, 0.95), 1),
            "min_ms": round(min(totals), 1),
            "max_ms": round(max(totals), 1),
            "avg_eou_ms": round(sum(t.eou_delay_ms or 0 for t in self._completed) / len(self._completed), 1),
            "avg_llm_ttft_ms": round(sum(t.llm_ttft_ms or 0 for t in self._completed) / len(self._completed), 1),
            "avg_tts_ttfb_ms": round(sum(t.tts_ttfb_ms or 0 for t in self._completed) / len(self._completed), 1),
            "avg_cache_hit_rate": round(sum(rates) / len(rates), 3) if rates else None,
        }
