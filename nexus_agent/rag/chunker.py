"""
Nexus RAG — Corpus chunker

Turns a directory of markdown documents into retrieval chunks.

The corpus convention (see rag/corpus/<tenant>/*.md) is:

    ---
    title: Lumenia Company Overview
    source_url: https://lumenialab.com/
    category: overview
    ---

    ## What Lumenia Does
    ...100-250 words, self-contained...

    ## Markets Served
    ...

Splitting happens on `## ` headings because the corpus is authored so that each
`## ` section stands alone semantically. That beats blind fixed-width splitting:
a voice agent reading a chunk aloud needs the chunk to be a complete thought, not
a window that starts mid-sentence.

Oversized sections are further split on paragraph boundaries with a sentence
overlap, so a fact that straddles the split survives in both halves.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

# A chunk much longer than this dilutes its own embedding and wastes prompt
# budget when injected into a latency-sensitive turn.
MAX_CHUNK_WORDS = 260
# Below this a section is too thin to retrieve well on its own, so it is merged
# forward into the next section.
MIN_CHUNK_WORDS = 25
# Sentences of overlap carried across a hard split.
OVERLAP_SENTENCES = 1

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


@dataclass
class Chunk:
    """One retrievable unit of knowledge."""

    chunk_id: str
    tenant_id: str
    title: str
    heading: str
    text: str
    source_url: str
    category: str
    doc_name: str
    ordinal: int
    embedding: list[float] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def embed_text(self) -> str:
        """The string that actually gets encoded.

        The document title and heading are prepended to the body so the vector
        carries the topic even when the body itself never restates it — a section
        headed "Pricing" whose body says only "Engagements start at..." should
        still match the query "how much does it cost".
        """
        return f"{self.title} — {self.heading}\n\n{self.text}".strip()

    def to_payload(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "tenant_id": self.tenant_id,
            "title": self.title,
            "heading": self.heading,
            "text": self.text,
            "source_url": self.source_url,
            "category": self.category,
            "doc_name": self.doc_name,
            "ordinal": self.ordinal,
            "embedding": self.embedding,
        }


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Extract the YAML-ish frontmatter block. Only flat `key: value` pairs are
    supported, which is all the corpus convention uses — avoids a yaml dep."""
    m = _FRONTMATTER.match(raw)
    if not m:
        return {}, raw

    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip("\"'")
    return meta, raw[m.end():]


def _split_oversized(heading: str, body: str) -> list[str]:
    """Split a too-long section on paragraph boundaries, carrying a sentence of
    overlap so facts spanning the seam remain retrievable from either side."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paragraphs:
        return []

    parts: list[str] = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        para_words = len(para.split())

        if current and current_words + para_words > MAX_CHUNK_WORDS:
            parts.append("\n\n".join(current))
            tail = _SENTENCE.split(current[-1])
            overlap = tail[-OVERLAP_SENTENCES:] if len(tail) > OVERLAP_SENTENCES else []
            current = list(overlap)
            current_words = sum(len(s.split()) for s in current)

        current.append(para)
        current_words += para_words

    if current:
        parts.append("\n\n".join(current))

    return [p for p in parts if p.strip()]


def chunk_markdown(raw: str, *, tenant_id: str, doc_name: str) -> list[Chunk]:
    """Chunk a single markdown document into self-contained sections."""
    meta, body = _parse_frontmatter(raw)
    title = meta.get("title") or doc_name.replace("-", " ").replace("_", " ").title()
    source_url = meta.get("source_url", "")
    category = meta.get("category", "general")

    # Build (heading, body) pairs by walking the H2 boundaries. Any prose that
    # appears before the first H2 becomes an implicit intro section.
    sections: list[tuple[str, str]] = []
    matches = list(_H2.finditer(body))

    if not matches:
        sections.append((title, body.strip()))
    else:
        preamble = body[: matches[0].start()].strip()
        if preamble:
            sections.append((title, preamble))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
            sections.append((m.group(1).strip(), body[m.end():end].strip()))

    # Merge sections too thin to stand on their own into the following one.
    merged: list[tuple[str, str]] = []
    carry_heading: str | None = None
    carry_body = ""
    for heading, text in sections:
        if not text:
            continue
        if carry_body:
            heading = carry_heading or heading
            text = f"{carry_body}\n\n{text}"
            carry_heading, carry_body = None, ""
        if len(text.split()) < MIN_CHUNK_WORDS:
            carry_heading, carry_body = heading, text
            continue
        merged.append((heading, text))
    if carry_body:
        if merged:
            h, t = merged[-1]
            merged[-1] = (h, f"{t}\n\n{carry_body}")
        else:
            merged.append((carry_heading or title, carry_body))

    chunks: list[Chunk] = []
    for heading, text in merged:
        for part in _split_oversized(heading, text) or [text]:
            ordinal = len(chunks)
            # Content-addressed id: re-ingesting an unchanged corpus is a no-op
            # upsert rather than a duplicate row.
            digest = hashlib.sha256(
                f"{tenant_id}|{doc_name}|{heading}|{part}".encode()
            ).hexdigest()[:16]
            chunks.append(
                Chunk(
                    chunk_id=digest,
                    tenant_id=tenant_id,
                    title=title,
                    heading=heading,
                    text=part.strip(),
                    source_url=source_url,
                    category=category,
                    doc_name=doc_name,
                    ordinal=ordinal,
                )
            )
    return chunks


def chunk_corpus(corpus_dir: str | Path, *, tenant_id: str) -> list[Chunk]:
    """Chunk every `.md` file in a corpus directory, sorted by filename so
    ordinals are stable across runs."""
    path = Path(corpus_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"corpus directory not found: {path}")

    chunks: list[Chunk] = []
    for md in sorted(path.glob("*.md")):
        raw = md.read_text(encoding="utf-8")
        chunks.extend(chunk_markdown(raw, tenant_id=tenant_id, doc_name=md.stem))
    return chunks
