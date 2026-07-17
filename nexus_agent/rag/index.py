"""
Nexus RAG — In-process hybrid index

Retrieval runs entirely inside the agent worker. At startup the worker loads its
tenant's chunks (from the TMS backend, or from the local corpus in dev) into a
single normalised numpy matrix. A query then costs one local embedding plus one
matrix multiply — roughly 5-10ms total, with no network call on the hot path.

Retrieval is hybrid, and that is not decoration. Dense vectors are good at intent
("do they build chatbots?" → the AI agents page) and reliably bad at rare proper
nouns — a 384-d model has no useful representation of "WHMCS", "Deliverect" or
"Verisign". Those are exactly the terms a sales agent must never fumble, and they
are exactly what BM25 nails. Each retriever ranks independently and the two
rankings are fused with Reciprocal Rank Fusion, which needs no score calibration
between the two very differently-scaled scoring functions.

Chunks scoring below a relevance floor are dropped rather than returned. An empty
result is a feature: it lets the agent say "I don't have that" instead of reading
out the nearest irrelevant paragraph, which is how RAG systems hallucinate.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import structlog

from rag.chunker import Chunk, chunk_corpus
from rag.embeddings import EMBEDDING_DIM, embed_query, embed_texts

logger = structlog.get_logger()

# RRF damping. 60 is the value from the original Cormack et al. paper and behaves
# well when fusing exactly two rankers.
RRF_K = 60

# ── Relevance gating ──
# These are calibrated against the actual corpus, not guessed. Measured cosine
# with bge-small over the Lumenia corpus:
#
#   on-domain  queries: dense_max 0.592 .. 0.701   (worst: "who are your clients?")
#   off-domain queries: dense_max 0.434 .. 0.554   (worst: "what is 2 plus 2?")
#
# The separation is real but narrow, so the gate is set at 0.52 — below the
# on-domain floor with margin, above the clearly-unrelated band. That deliberately
# lets a couple of borderline off-domain queries (~0.53-0.55) retrieve something,
# because the failure modes are not symmetric: returning an irrelevant chunk is
# harmless (the LLM reads it, sees it does not answer, and declines — the system
# prompt is a second gate), whereas returning nothing for a question the site DOES
# answer looks like broken retrieval in front of a client. Bias to recall.
#
# Critically, this gate is on the DENSE score only. BM25 cannot gate relevance:
# off-domain "tell me a joke about cats" scores 5.88 while on-domain "who are your
# clients?" scores 3.10, so a BM25 threshold would admit junk and reject good hits.
# BM25 ranks; dense decides whether anything is relevant at all.
QUERY_RELEVANCE_GATE = 0.52
# Once a query is admitted, a chunk still needs some topical relation to be worth
# returning. This is looser than the query gate so BM25 can promote an exact-term
# match that dense ranked poorly — the WHMCS/Deliverect/Verisign case.
CHUNK_ADMISSION_FLOOR = 0.45
# How deep each retriever's ranking goes into the fusion.
FUSION_DEPTH = 8

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    """a an and are as at be by do does for from has have how i in is it its of on or
    that the this to was what when where which who why will with you your we our us""".split()
)


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


@dataclass
class RetrievedChunk:
    """A chunk plus why it was retrieved. The scores are surfaced to the demo HUD
    and to the grounding verifier, so they are part of the contract, not debug."""

    chunk: Chunk
    score: float
    dense_rank: int | None
    lexical_rank: int | None

    @property
    def matched_by(self) -> str:
        if self.dense_rank is not None and self.lexical_rank is not None:
            return "hybrid"
        if self.lexical_rank is not None:
            return "keyword"
        return "semantic"

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk.chunk_id,
            "title": self.chunk.title,
            "heading": self.chunk.heading,
            "text": self.chunk.text,
            "source_url": self.chunk.source_url,
            "category": self.chunk.category,
            "score": round(self.score, 4),
            "matched_by": self.matched_by,
        }


class _BM25:
    """Compact BM25-Okapi over the chunk corpus.

    Sized for hundreds of chunks, not millions: it scores every document on every
    query. At this corpus size that is ~0.1ms and buys exact-term recall that the
    dense retriever cannot provide.
    """

    __slots__ = ("_docs", "_df", "_idf", "_avg_len", "_n", "_k1", "_b")

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self._docs = [Counter(toks) for toks in corpus_tokens]
        self._n = len(corpus_tokens)
        self._k1 = k1
        self._b = b
        self._avg_len = (
            sum(len(t) for t in corpus_tokens) / self._n if self._n else 0.0
        )

        self._df: Counter[str] = Counter()
        for toks in corpus_tokens:
            self._df.update(set(toks))

        # Probabilistic IDF with the +1 floor, so a term appearing in more than
        # half the corpus contributes ~0 rather than going negative.
        self._idf = {
            term: math.log(1 + (self._n - df + 0.5) / (df + 0.5))
            for term, df in self._df.items()
        }

    def scores(self, query_tokens: list[str]) -> np.ndarray:
        out = np.zeros(self._n, dtype=np.float32)
        if not self._n:
            return out
        for i, doc in enumerate(self._docs):
            length = sum(doc.values())
            norm = self._k1 * (1 - self._b + self._b * length / (self._avg_len or 1))
            total = 0.0
            for term in query_tokens:
                tf = doc.get(term, 0)
                if not tf:
                    continue
                total += self._idf.get(term, 0.0) * (tf * (self._k1 + 1)) / (tf + norm)
            out[i] = total
        return out


class KnowledgeIndex:
    """A tenant's knowledge base, resident in memory and queryable in ~5-10ms."""

    def __init__(self, tenant_id: str, chunks: list[Chunk]):
        self.tenant_id = tenant_id
        self.chunks = chunks
        self.loaded_at = time.time()

        if chunks:
            matrix = np.asarray([c.embedding for c in chunks], dtype=np.float32)
            if matrix.shape[1] != EMBEDDING_DIM:
                raise ValueError(
                    f"embedding width {matrix.shape[1]} != expected {EMBEDDING_DIM}; "
                    "the corpus was ingested with a different model"
                )
            # Pre-normalise once at load so each query is a plain dot product
            # rather than a per-query cosine with repeated norm computation.
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            self._matrix = matrix / np.clip(norms, 1e-9, None)
        else:
            self._matrix = np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

        self._bm25 = _BM25([_tokenize(f"{c.heading} {c.text}") for c in chunks])

        logger.info(
            "knowledge_index_ready",
            tenant_id=tenant_id,
            chunks=len(chunks),
            docs=len({c.doc_name for c in chunks}),
        )

    def __len__(self) -> int:
        return len(self.chunks)

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    def search(self, query: str, *, k: int = 3) -> list[RetrievedChunk]:
        """Hybrid search. Returns at most `k` chunks, ordered best-first, and an
        empty list when the query is not about this knowledge base at all."""
        if self.is_empty or not query.strip():
            return []

        # ── Dense: decides relevance, and ranks ──
        query_vector = np.asarray(embed_query(query), dtype=np.float32)
        query_vector /= max(float(np.linalg.norm(query_vector)), 1e-9)
        dense_scores = self._matrix @ query_vector
        best_dense = float(dense_scores.max())

        # Gate on the query as a whole. If nothing in the corpus is even close,
        # the honest answer is "I don't know" — returning the least-bad chunk here
        # is precisely how a RAG agent ends up confidently reciting an irrelevant
        # paragraph at a prospect.
        if best_dense < QUERY_RELEVANCE_GATE:
            logger.info(
                "kb_query_off_domain",
                tenant_id=self.tenant_id,
                query=query[:80],
                best_score=round(best_dense, 3),
                gate=QUERY_RELEVANCE_GATE,
            )
            return []

        admissible = {int(i) for i in np.nonzero(dense_scores >= CHUNK_ADMISSION_FLOOR)[0]}

        dense_ranks = {
            int(idx): rank
            for rank, idx in enumerate(np.argsort(-dense_scores)[:FUSION_DEPTH])
            if int(idx) in admissible
        }

        # ── Lexical: ranks only, never admits ──
        query_tokens = _tokenize(query)
        lexical_ranks: dict[int, int] = {}
        if query_tokens:
            lexical_scores = self._bm25.scores(query_tokens)
            lexical_ranks = {
                int(idx): rank
                for rank, idx in enumerate(np.argsort(-lexical_scores)[:FUSION_DEPTH])
                if lexical_scores[idx] > 0 and int(idx) in admissible
            }

        if not dense_ranks and not lexical_ranks:
            logger.info("kb_no_match", tenant_id=self.tenant_id, query=query[:80])
            return []

        # ── Reciprocal Rank Fusion ──
        fused: dict[int, float] = {}
        for idx, rank in dense_ranks.items():
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
        for idx, rank in lexical_ranks.items():
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)

        ordered = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [
            RetrievedChunk(
                chunk=self.chunks[idx],
                # Report cosine rather than the RRF score: cosine is interpretable
                # on the demo HUD ("0.72 similar"), an RRF score is not.
                score=float(dense_scores[idx]),
                dense_rank=dense_ranks.get(idx),
                lexical_rank=lexical_ranks.get(idx),
            )
            for idx, _ in ordered
        ]


# ── Process-wide registry ─────────────────────────────────────────────────────
# One index per tenant, shared across all concurrent calls on this worker. The
# index is read-only after construction, so sharing needs no per-call locking.

_indexes: dict[str, KnowledgeIndex] = {}
_registry_lock = threading.Lock()


def load_index(
    tenant_id: str,
    *,
    corpus_dir: str | Path | None = None,
    chunks: list[Chunk] | None = None,
    cache_dir: str | Path | None = None,
) -> KnowledgeIndex:
    """Build and register a tenant's index.

    Pass `chunks` when they arrive pre-embedded. Pass `corpus_dir` to build from
    local markdown.

    When `cache_dir` is given, embeddings are read from the on-disk vector cache
    if it matches the corpus, and written to it otherwise. This is what keeps
    worker prewarm inside LiveKit's process-init budget: embedding the corpus
    takes ~10s and the budget is 10s, whereas loading the cache takes single-digit
    milliseconds. See rag/cache.py.
    """
    if chunks is None:
        if corpus_dir is None:
            raise ValueError("load_index needs either chunks or corpus_dir")

        chunks = chunk_corpus(corpus_dir, tenant_id=tenant_id)

        cached = None
        if cache_dir is not None:
            from rag import cache
            cached = cache.load(cache_dir, tenant_id, chunks)

        if cached is not None:
            chunks = cached
        else:
            vectors = embed_texts([c.embed_text() for c in chunks])
            for chunk, vector in zip(chunks, vectors):
                chunk.embedding = vector
            if cache_dir is not None:
                from rag import cache
                try:
                    cache.save(cache_dir, tenant_id, chunks)
                except Exception as e:
                    # A read-only filesystem is a normal deployment; the index is
                    # already built in memory, so this is not fatal.
                    logger.warning("vector_cache_save_failed", tenant_id=tenant_id, error=str(e))

    index = KnowledgeIndex(tenant_id, chunks)
    with _registry_lock:
        _indexes[tenant_id] = index
    return index


def get_index(tenant_id: str) -> KnowledgeIndex | None:
    """Return a loaded index, or None if this tenant has no knowledge base.

    Callers must treat None as "retrieval unavailable" and degrade gracefully —
    a tenant without a KB is a normal configuration, not an error.
    """
    return _indexes.get(tenant_id)
