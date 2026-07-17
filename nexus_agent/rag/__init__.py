"""
Nexus — Retrieval-Augmented Generation

Knowledge retrieval for voice agents, designed around one constraint: retrieval
sits on the critical path of a live conversation, so it must not make a network
call. The hot path is:

    query text → local ONNX embedding (~5ms) → in-process cosine over a numpy
    matrix (~1ms) → top-k chunks

Postgres/pgvector (owned by the TMS backend) is the system of record and the
multi-tenant store. Each agent worker pulls a snapshot of its tenant's chunks at
startup and keeps them resident in memory. Nothing in the request path talks to
the database or to an embedding API.

Layout:
    chunker    — markdown corpus → semantically self-contained Chunks
    embeddings — local fastembed/ONNX encoder (shared by ingest and query)
    index      — in-memory hybrid index (dense cosine + lexical overlap)
    ingest     — CLI: corpus → chunks → vectors → POST to the TMS backend
"""

from rag.chunker import Chunk, chunk_corpus, chunk_markdown
from rag.embeddings import embed_query, embed_texts, get_encoder, warm_encoder
from rag.index import KnowledgeIndex, RetrievedChunk, get_index, load_index

__all__ = [
    "Chunk",
    "chunk_corpus",
    "chunk_markdown",
    "embed_query",
    "embed_texts",
    "get_encoder",
    "warm_encoder",
    "KnowledgeIndex",
    "RetrievedChunk",
    "get_index",
    "load_index",
]
