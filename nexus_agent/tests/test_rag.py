"""
Nexus RAG — retrieval tests

The important tests here are the relevance-gate ones. The gate thresholds in
rag/index.py were calibrated against measured score distributions over the real
Lumenia corpus, and those numbers are load-bearing: too low and the agent recites
irrelevant paragraphs at a prospect, too high and it claims not to know things
its own website says. These tests pin the behaviour so a future tweak to
QUERY_RELEVANCE_GATE has to justify itself against real queries.

The embedding model loads once per session (~10s cold).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag.chunker import chunk_corpus, chunk_markdown
from rag.embeddings import EMBEDDING_DIM, embed_texts
from rag.index import KnowledgeIndex

CORPUS = Path(__file__).parent.parent / "rag" / "corpus" / "lumenia"


@pytest.fixture(scope="module")
def index() -> KnowledgeIndex:
    chunks = chunk_corpus(CORPUS, tenant_id="lumenia")
    for chunk, vector in zip(chunks, embed_texts([c.embed_text() for c in chunks])):
        chunk.embedding = vector
    return KnowledgeIndex("lumenia", chunks)


# ── Chunking ──────────────────────────────────────────────────────────────────

def test_frontmatter_is_parsed_and_stripped():
    chunks = chunk_markdown(
        "---\ntitle: Test Doc\nsource_url: https://example.com/x\ncategory: service\n---\n\n"
        "## First Section\n" + "word " * 60 + "\n\n## Second Section\n" + "term " * 60,
        tenant_id="t", doc_name="doc",
    )
    assert len(chunks) == 2
    assert chunks[0].title == "Test Doc"
    assert chunks[0].source_url == "https://example.com/x"
    assert chunks[0].category == "service"
    assert chunks[0].heading == "First Section"
    # Frontmatter must never leak into text the agent could read aloud.
    assert "---" not in chunks[0].text
    assert "source_url" not in chunks[0].text


def test_thin_sections_merge_forward():
    """A heading with two words under it is not independently retrievable, so it
    must be folded into a neighbour rather than becoming its own chunk."""
    chunks = chunk_markdown(
        "---\ntitle: T\n---\n\n## Tiny\nToo short.\n\n## Real Section\n" + "content " * 60,
        tenant_id="t", doc_name="doc",
    )
    assert len(chunks) == 1
    assert "Too short." in chunks[0].text


def test_chunk_ids_are_content_addressed():
    """Re-ingesting an unchanged corpus must be an idempotent upsert."""
    raw = "---\ntitle: T\n---\n\n## S\n" + "word " * 60
    first = chunk_markdown(raw, tenant_id="t", doc_name="d")
    again = chunk_markdown(raw, tenant_id="t", doc_name="d")
    assert [c.chunk_id for c in first] == [c.chunk_id for c in again]

    changed = chunk_markdown(raw + " extra", tenant_id="t", doc_name="d")
    assert changed[0].chunk_id != first[0].chunk_id


def test_corpus_chunks_are_bounded(index: KnowledgeIndex):
    """Oversized chunks dilute their own embedding and waste the prompt budget on
    a latency-critical turn."""
    assert len(index) > 50
    assert all(c.word_count <= 300 for c in index.chunks)
    assert all(c.text.strip() for c in index.chunks)


def test_embeddings_match_declared_width(index: KnowledgeIndex):
    """A width mismatch would fail at pgvector insert time, far from the cause."""
    assert all(len(c.embedding) == EMBEDDING_DIM for c in index.chunks)


# ── Relevance gate ────────────────────────────────────────────────────────────

ON_DOMAIN = [
    "have you ever built software for trucking or logistics?",
    "can you integrate QuickBooks?",
    "where is the company located?",
    "do you do WHMCS domain reselling?",
    "tell me about the Medaan food delivery project",
    "what is your delivery process?",
    "do you build AI agents and automation?",
    "who are your clients?",
    "what services do you offer?",
    "how do I get in touch?",
]

OFF_DOMAIN = [
    "what's the weather in Karachi today?",
    "how do I bake sourdough bread?",
    "who won the world cup in 2018?",
    "recommend a good action movie",
    "what is the capital of France?",
]


@pytest.mark.parametrize("query", ON_DOMAIN)
def test_on_domain_queries_retrieve(index: KnowledgeIndex, query: str):
    hits = index.search(query, k=3)
    assert hits, f"on-domain query retrieved nothing: {query!r}"
    assert hits[0].score >= 0.5


@pytest.mark.parametrize("query", OFF_DOMAIN)
def test_off_domain_queries_retrieve_nothing(index: KnowledgeIndex, query: str):
    """An empty result is what lets the agent say 'I don't have that' instead of
    reading out the nearest irrelevant chunk."""
    assert index.search(query, k=3) == [], f"off-domain query leaked chunks: {query!r}"


# ── Retrieval quality ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query,expected_substring",
    [
        ("have you built trucking or dispatch software?", "trucking"),
        ("tell me about the food delivery platform", "medaan"),
        ("do you do domain registrar and WHMCS work?", "domain"),
        ("what is your four step process?", "process"),
        ("how do I contact you?", "contact"),
    ],
)
def test_retrieves_the_right_document(index: KnowledgeIndex, query: str, expected_substring: str):
    hits = index.search(query, k=3)
    assert hits, f"no hits for {query!r}"
    blob = " ".join(f"{h.chunk.doc_name} {h.chunk.title} {h.chunk.heading}" for h in hits).lower()
    assert expected_substring in blob, f"{query!r} did not surface {expected_substring!r}; got {blob[:200]}"


def test_rare_proper_noun_is_found_by_keyword_path(index: KnowledgeIndex):
    """The case dense retrieval is worst at and a sales agent must never fumble:
    a rare product name a 384-d model has no useful representation of."""
    hits = index.search("WHMCS", k=3)
    assert hits
    assert any(h.lexical_rank is not None for h in hits), "BM25 did not contribute to a proper-noun query"


def test_search_is_fast_enough_for_a_live_turn(index: KnowledgeIndex):
    """Retrieval sits on the conversational hot path. Anything above ~30ms here
    means a network call crept in."""
    import time

    index.search("warmup", k=3)
    started = time.perf_counter()
    for _ in range(20):
        index.search("do you build AI agents for logistics companies?", k=3)
    per_query_ms = (time.perf_counter() - started) / 20 * 1000
    assert per_query_ms < 30, f"retrieval too slow for a live call: {per_query_ms:.1f}ms/query"


def test_empty_index_degrades_quietly():
    """A tenant with no knowledge base is a normal configuration, not an error."""
    empty = KnowledgeIndex("nobody", [])
    assert empty.is_empty
    assert empty.search("anything at all", k=3) == []
