"""
Nexus RAG — Ingest CLI

Turns a markdown corpus into embedded chunks and pushes them to the TMS backend,
which owns the pgvector store.

Embedding happens here rather than in the backend so that exactly one component
in the system loads the ONNX model, and so the query-side and ingest-side vectors
can never drift out of the same space. The backend just stores float arrays.

Usage:
    # Verify chunking + embedding without writing anything
    python -m rag.ingest --tenant lumenia --dry-run

    # Ingest the default corpus for a tenant into the backend
    python -m rag.ingest --tenant lumenia

    # Ingest a corpus from an explicit path against a specific backend
    python -m rag.ingest --tenant lumenia --corpus ./rag/corpus/lumenia \
        --backend http://localhost:8001

    # Chunk, embed, and immediately query it — end-to-end retrieval smoke test
    python -m rag.ingest --tenant lumenia --dry-run --query "do you build AI agents?"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

from rag.chunker import chunk_corpus
from rag.embeddings import EMBEDDING_MODEL, embed_texts
from rag.index import KnowledgeIndex

DEFAULT_CORPUS_ROOT = Path(__file__).parent / "corpus"
DEFAULT_BACKEND = os.getenv("TMS_BASE_URL", "http://localhost:8001")
SERVICE_KEY = os.getenv("NEXUS_SERVICE_KEY", "")


def _push(backend: str, tenant_id: str, chunks: list) -> dict:
    payload = {
        "tenant_id": tenant_id,
        "embedding_model": EMBEDDING_MODEL,
        "chunks": [c.to_payload() for c in chunks],
    }
    headers = {"X-Service-Key": SERVICE_KEY} if SERVICE_KEY else {}
    # Embedding payloads are large (chunks x 384 floats); give it room.
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            f"{backend.rstrip('/')}/kb/ingest", json=payload, headers=headers
        )
        response.raise_for_status()
        return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a markdown corpus into the Nexus knowledge base")
    parser.add_argument("--tenant", required=True, help="Tenant id, e.g. 'lumenia'")
    parser.add_argument("--corpus", default=None, help="Corpus directory (default: rag/corpus/<tenant>)")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help=f"TMS backend URL (default: {DEFAULT_BACKEND})")
    parser.add_argument("--dry-run", action="store_true", help="Chunk and embed but do not write to the backend")
    parser.add_argument("--query", default="", help="After building, run this query against the index and print hits")
    parser.add_argument(
        "--build-cache",
        action="store_true",
        help="Write the on-disk vector cache that agent workers load at prewarm, then exit. "
             "Run at image build time so workers never embed the corpus on boot.",
    )
    args = parser.parse_args(argv)

    corpus_dir = Path(args.corpus) if args.corpus else DEFAULT_CORPUS_ROOT / args.tenant
    if not corpus_dir.is_dir():
        print(f"error: corpus directory not found: {corpus_dir}", file=sys.stderr)
        return 1

    # ── Chunk ──
    chunks = chunk_corpus(corpus_dir, tenant_id=args.tenant)
    if not chunks:
        print(f"error: no chunks produced from {corpus_dir} (are there .md files?)", file=sys.stderr)
        return 1

    docs = sorted({c.doc_name for c in chunks})
    words = sum(c.word_count for c in chunks)
    print(f"chunked  : {len(chunks)} chunks from {len(docs)} docs ({words:,} words)")
    print(f"  avg {words // len(chunks)} words/chunk, "
          f"longest {max(c.word_count for c in chunks)}, "
          f"shortest {min(c.word_count for c in chunks)}")

    by_category: dict[str, int] = {}
    for c in chunks:
        by_category[c.category] = by_category.get(c.category, 0) + 1
    print(f"  categories: {', '.join(f'{k}={v}' for k, v in sorted(by_category.items()))}")

    # ── Embed ──
    started = time.perf_counter()
    vectors = embed_texts([c.embed_text() for c in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector
    print(f"embedded : {len(vectors)} vectors x {len(vectors[0])}d "
          f"in {round((time.perf_counter() - started) * 1000)}ms using {EMBEDDING_MODEL}")

    # ── Optional retrieval smoke test ──
    if args.query:
        index = KnowledgeIndex(args.tenant, chunks)
        started = time.perf_counter()
        hits = index.search(args.query, k=3)
        elapsed = (time.perf_counter() - started) * 1000
        print(f"\nquery    : {args.query!r} → {len(hits)} hits in {elapsed:.1f}ms")
        for i, hit in enumerate(hits, 1):
            print(f"  {i}. [{hit.score:.3f} {hit.matched_by:8}] {hit.chunk.title} — {hit.chunk.heading}")
            print(f"     {hit.chunk.text[:160].replace(chr(10), ' ')}...")
        if not hits:
            print("  (nothing cleared the relevance floor — the agent would say it doesn't know)")

    # ── Vector cache ──
    if args.build_cache:
        from rag import cache
        path = cache.save(DEFAULT_CORPUS_ROOT / ".cache", args.tenant, chunks)
        print(f"\ncached   : {path} ({path.stat().st_size // 1024}KB) — workers will load this at prewarm")
        return 0

    # ── Push ──
    if args.dry_run:
        print("\ndry run — nothing written to the backend")
        return 0

    try:
        result = _push(args.backend, args.tenant, chunks)
    except httpx.HTTPStatusError as e:
        print(f"error: backend rejected ingest: {e.response.status_code} {e.response.text[:400]}", file=sys.stderr)
        return 1
    except httpx.HTTPError as e:
        print(f"error: could not reach backend at {args.backend}: {e}", file=sys.stderr)
        return 1

    print(f"\ningested : {result.get('inserted', 0)} new, {result.get('updated', 0)} updated, "
          f"{result.get('deleted', 0)} removed → {args.backend}")
    print(f"           tenant '{args.tenant}' now has {result.get('total', 0)} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
