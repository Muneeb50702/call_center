"""
Nexus RAG — Vector cache

Persists a tenant's embedded chunks so worker processes load vectors from disk
instead of re-embedding the corpus on every boot.

This exists because of a real failure, not a hypothetical one: embedding the
122-chunk Lumenia corpus takes ~10s, and LiveKit gives `prewarm_fnc` a 10s budget
before it kills the process with a TimeoutError. Every job process paid that cost
and then died. Loading the cache instead takes single-digit milliseconds.

The corpus is static between deploys, so embedding it per process was pure waste
even when it fit in the budget. The cache is built once (at image build, or by
the ingest CLI) and read many times.

Staleness is handled by fingerprint, not by timestamps: the key covers the
embedding model name, the vector width, and the content hash of every chunk. Edit
the corpus or change the model and the fingerprint no longer matches, so the
cache is ignored and rebuilt rather than silently serving vectors for text that
no longer exists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import structlog

from rag.chunker import Chunk
from rag.embeddings import EMBEDDING_DIM, EMBEDDING_MODEL

logger = structlog.get_logger()

CACHE_VERSION = 1


def fingerprint(chunks: list[Chunk]) -> str:
    """Identity of a corpus + the model that embedded it.

    Covers chunk ids (which are themselves content-addressed) and the model, so
    any change to the text or the encoder invalidates the cache.
    """
    digest = hashlib.sha256()
    digest.update(f"v{CACHE_VERSION}|{EMBEDDING_MODEL}|{EMBEDDING_DIM}".encode())
    for chunk_id in sorted(c.chunk_id for c in chunks):
        digest.update(chunk_id.encode())
    return digest.hexdigest()[:32]


def cache_path(cache_dir: str | Path, tenant_id: str) -> Path:
    return Path(cache_dir) / f"{tenant_id}.npz"


def save(cache_dir: str | Path, tenant_id: str, chunks: list[Chunk]) -> Path:
    """Write embedded chunks to disk. Chunks must already carry embeddings."""
    if not chunks:
        raise ValueError("refusing to cache an empty corpus")
    missing = [c.chunk_id for c in chunks if len(c.embedding) != EMBEDDING_DIM]
    if missing:
        raise ValueError(f"{len(missing)} chunks have no/short embedding; embed before caching")

    path = cache_path(cache_dir, tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    vectors = np.asarray([c.embedding for c in chunks], dtype=np.float32)
    metadata = [
        {
            "chunk_id": c.chunk_id, "tenant_id": c.tenant_id, "title": c.title,
            "heading": c.heading, "text": c.text, "source_url": c.source_url,
            "category": c.category, "doc_name": c.doc_name, "ordinal": c.ordinal,
        }
        for c in chunks
    ]

    np.savez_compressed(
        path,
        vectors=vectors,
        metadata=np.array(json.dumps(metadata), dtype=object),
        fingerprint=np.array(fingerprint(chunks), dtype=object),
        model=np.array(EMBEDDING_MODEL, dtype=object),
    )
    logger.info(
        "vector_cache_written",
        tenant_id=tenant_id, path=str(path), chunks=len(chunks),
        size_kb=round(path.stat().st_size / 1024, 1),
    )
    return path


def load(cache_dir: str | Path, tenant_id: str, expected: list[Chunk]) -> list[Chunk] | None:
    """Load cached chunks, or None if absent or stale.

    `expected` is the freshly-chunked corpus; its fingerprint must match the
    cached one. Returning None is normal and means "embed it yourself".
    """
    path = cache_path(cache_dir, tenant_id)
    if not path.is_file():
        return None

    try:
        with np.load(path, allow_pickle=True) as data:
            cached_fp = str(data["fingerprint"].item())
            wanted_fp = fingerprint(expected)
            if cached_fp != wanted_fp:
                logger.info(
                    "vector_cache_stale",
                    tenant_id=tenant_id, cached=cached_fp[:12], expected=wanted_fp[:12],
                    hint="corpus or embedding model changed; re-embedding",
                )
                return None

            vectors = data["vectors"]
            metadata = json.loads(str(data["metadata"].item()))

        if len(vectors) != len(metadata):
            logger.warning("vector_cache_corrupt", tenant_id=tenant_id)
            return None

        chunks = [
            Chunk(**meta, embedding=[float(x) for x in vector])
            for meta, vector in zip(metadata, vectors)
        ]
        logger.info("vector_cache_hit", tenant_id=tenant_id, chunks=len(chunks))
        return chunks

    except Exception as e:
        # A bad cache must never take a worker down — just rebuild.
        logger.warning("vector_cache_unreadable", tenant_id=tenant_id, error=str(e))
        return None
