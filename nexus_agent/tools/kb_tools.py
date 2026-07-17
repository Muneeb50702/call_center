"""
Nexus — Knowledge base tools

The retrieval tool exposed to sales agents. Wraps the in-process hybrid index
(rag/index.py) and formats hits for the LLM.

Two details matter more than they look:

1. The returned string is captured by `pipeline/hooks.py:_on_tools` into the
   per-turn grounding facts, which is what the pre-TTS verifier checks spoken
   numbers against. So retrieved text is not just context — it is the allow-list
   of what the agent is permitted to say out loud this turn. Return the chunk
   text verbatim; paraphrasing here would break grounding downstream.

2. On a miss this returns an explicit NO_RESULTS instruction rather than an empty
   string. An LLM handed "" will happily invent an answer; an LLM handed "say you
   don't know and offer to connect them" will do that instead.
"""

from __future__ import annotations

import time

import structlog

from rag.index import RetrievedChunk, get_index

logger = structlog.get_logger()

MAX_CHUNKS = 3

NO_RESULTS = (
    "NO_RESULTS: The knowledge base has nothing on this. Do NOT guess or invent an "
    "answer. Tell the caller honestly that you don't have that detail to hand, and "
    "offer to have someone follow up with it by email."
)


def _format(hits: list[RetrievedChunk]) -> str:
    """Render hits for the LLM.

    Sources are labelled and scored so the model can weigh them, and told
    explicitly that these are the only facts it may state. The wording is blunt
    on purpose: this text competes with the model's prior about the company, and
    a polite hint loses that competition.
    """
    parts = [
        "KNOWLEDGE BASE RESULTS — these are the ONLY facts you may state on this "
        "topic. Do not add detail that is not written below.\n"
    ]
    for i, hit in enumerate(hits, 1):
        parts.append(
            f"[Source {i} — {hit.chunk.title} › {hit.chunk.heading} "
            f"(relevance {hit.score:.2f})]\n{hit.chunk.text}\n"
        )
    return "\n".join(parts)


class KnowledgeTools:
    """Tenant-scoped retrieval. Holds no connection and does no I/O — the index is
    already resident in this worker's memory."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._last_hits: list[RetrievedChunk] = []
        self._last_latency_ms: float = 0.0
        self._queries = 0
        self._misses = 0

    @property
    def last_hits(self) -> list[RetrievedChunk]:
        """The most recent hits, for the demo HUD and call analytics."""
        return self._last_hits

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    @property
    def stats(self) -> dict:
        return {
            "queries": self._queries,
            "misses": self._misses,
            "hit_rate": round(1 - self._misses / self._queries, 3) if self._queries else None,
        }

    def search(self, query: str, *, k: int = MAX_CHUNKS) -> str:
        index = get_index(self.tenant_id)
        if index is None or index.is_empty:
            logger.warning("kb_unavailable", tenant_id=self.tenant_id)
            return NO_RESULTS

        started = time.perf_counter()
        hits = index.search(query, k=k)
        self._last_latency_ms = (time.perf_counter() - started) * 1000
        self._last_hits = hits
        self._queries += 1

        if not hits:
            self._misses += 1
            logger.info(
                "kb_miss",
                tenant_id=self.tenant_id,
                query=query[:80],
                latency_ms=round(self._last_latency_ms, 1),
            )
            return NO_RESULTS

        logger.info(
            "kb_hit",
            tenant_id=self.tenant_id,
            query=query[:80],
            hits=len(hits),
            top_score=round(hits[0].score, 3),
            matched_by=hits[0].matched_by,
            latency_ms=round(self._last_latency_ms, 1),
        )
        return _format(hits)
