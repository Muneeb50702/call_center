"""
Nexus RAG — Local embeddings

Encoding runs locally on CPU via fastembed (ONNX runtime). This is a deliberate
latency choice: a hosted embedding API costs 100-200ms of network round-trip on
every single conversational turn, which is a third of our entire latency budget
spent before the LLM has even seen the question. BAAI/bge-small-en-v1.5 is 384-d,
~50MB quantized, and encodes a short query in roughly 3-8ms on one core — small
enough to be free, good enough to retrieve well over a corpus this size.

The worker already runs a CPU turn-detector model, so ONNX inference is not a new
class of dependency in the deployment.

BGE models are trained asymmetrically: queries want an instruction prefix,
passages do not. fastembed's `query_embed` / `passage_embed` apply the correct
prefix per model, so always go through those rather than the generic `embed`.
"""

from __future__ import annotations

import threading
import time

import structlog

logger = structlog.get_logger()

# 384-dim. Keep in sync with the pgvector column width in the TMS migration and
# with EMBEDDING_DIM below — a mismatch fails at insert, not at query.
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

_encoder = None
_lock = threading.Lock()


def get_encoder():
    """Return the process-wide encoder, constructing it on first use.

    Construction downloads and initialises the ONNX model (seconds on a cold
    cache), so call `warm_encoder()` at worker startup rather than paying for it
    inside the first caller's turn.
    """
    global _encoder
    if _encoder is not None:
        return _encoder

    with _lock:
        if _encoder is not None:
            return _encoder
        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            raise RuntimeError(
                "fastembed is required for knowledge retrieval. "
                "Install it with: pip install 'fastembed>=0.4'"
            ) from e

        started = time.perf_counter()
        _encoder = TextEmbedding(model_name=EMBEDDING_MODEL)
        logger.info(
            "embedding_model_loaded",
            model=EMBEDDING_MODEL,
            dim=EMBEDDING_DIM,
            load_ms=round((time.perf_counter() - started) * 1000),
        )
        return _encoder


def warm_encoder() -> bool:
    """Load the model and run one throwaway encode so the first real query does
    not eat model-init and ONNX graph warmup. Returns False if unavailable, so a
    missing model degrades the agent to no-retrieval instead of killing the call.
    """
    try:
        encoder = get_encoder()
        started = time.perf_counter()
        list(encoder.query_embed(["warmup"]))
        logger.info(
            "embedding_model_warm",
            warm_ms=round((time.perf_counter() - started) * 1000),
        )
        return True
    except Exception as e:
        logger.warning("embedding_warmup_failed", error=str(e))
        return False


def embed_query(text: str) -> list[float]:
    """Encode a single search query. This is the only embedding call on the
    conversational hot path."""
    encoder = get_encoder()
    vectors = list(encoder.query_embed([text]))
    if not vectors:
        raise RuntimeError(f"encoder returned no vector for query: {text!r}")
    return [float(x) for x in vectors[0]]


def embed_texts(texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
    """Encode corpus passages. Ingest-time only — never on the hot path."""
    if not texts:
        return []
    encoder = get_encoder()
    started = time.perf_counter()
    vectors = [
        [float(x) for x in v]
        for v in encoder.passage_embed(texts, batch_size=batch_size)
    ]
    logger.info(
        "passages_embedded",
        count=len(vectors),
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )
    return vectors
