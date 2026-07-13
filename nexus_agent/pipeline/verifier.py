"""
Nexus Dispatch — Anti-Hallucination Verifier (Phase 0)

A cheap, deterministic guardrail that runs over the agent's DRAFT utterance
*before* it is synthesized to speech. It enforces the core no-hallucination
rule for dispatch: the agent must never state a critical value (a rate, a
dollar amount, an MC/DOT/load/booking number) unless that value is grounded in
something a tool returned this turn, or something the caller just said.

Design goals
------------
- **Deterministic first.** Pure regex + set-membership. No LLM call on the hot
  path (an optional LLM verifier can be layered on later behind a flag).
- **Conservative.** Only the highest-risk categories are enforced — money,
  per-mile rates, and prefixed identifiers (MC/DOT/USDOT/load/booking/PO/ref).
  Small counts ("3 loads", "2 hours", "one moment") are intentionally ignored
  so the agent is not constantly hedging on harmless numbers.
- **Sentence-level redaction.** Only the offending sentence is replaced with a
  brief hedge; the rest of the turn is spoken normally. This keeps the UX
  natural while still refusing to voice an invented number.

This module is dependency-light (only the stdlib) so it can be unit-tested
without the LiveKit stack. The Agent integration (running it inside `tts_node`)
lives in state/agents.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# ── What we refuse to voice unless grounded ──────────────────────────────────

# Prefixed identifiers: MC 123456, USDOT-1234567, load BK-99382, PO# 4471, ...
_ID_RE = re.compile(
    r"\b(MC|USDOT|DOT|BK|BOOK(?:ING)?|LOAD|PRO|PO|REF|ORDER)\b[\s#:._-]*"
    r"([A-Z]{0,3}[-\s]?\d[\d\-\s]{2,})",
    re.IGNORECASE,
)

# Money: $2,300  $2.30  $ 1250
_MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")

# Per-mile rate written as a bare decimal: 2.30, 3.1  (0.50–9.99 range)
_RATE_RE = re.compile(r"(?<![\d.])[0-9]\.\d{1,2}(?![\d.])")

# Any standalone number of 4+ digits (ids, big dollar amounts, weights) —
# these are almost never safe to invent.
_BIGNUM_RE = re.compile(r"(?<![\d.])\d{4,}(?![\d.])")

# Broad number matcher used to index the grounded sources.
_ANY_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Sentence splitter (keeps it simple — split on . ! ? followed by space/EOL).
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# What we say instead of an ungrounded critical fact.
HEDGE = "Let me pull that up so I can give you the exact details—one moment."


def _canon_number(raw: str) -> str:
    """Canonicalize a numeric token so '$2,300', '2300' and '2300.00' all match,
    and '2.30' matches '2.3'. Pure integers keep full precision (so 7-digit DOT
    numbers are not mangled by float formatting)."""
    s = raw.replace("$", "").replace(",", "").replace(" ", "").replace("-", "").strip()
    s = s.rstrip(".")
    if not s or not any(ch.isdigit() for ch in s):
        return ""
    if "." in s:
        try:
            return "%g" % float(s)  # 2.30 -> "2.3", 2.0 -> "2"
        except ValueError:
            return s
    return s.lstrip("0") or "0"     # integers: normalize leading zeros only


def _index_sources(sources: Iterable[str]) -> tuple[set[str], str]:
    """Return (set of canonical numbers found in the grounded sources,
    lowercased concatenated text for substring fallback)."""
    numbers: set[str] = set()
    parts: list[str] = []
    for src in sources:
        if not src:
            continue
        text = str(src)
        parts.append(text.lower())
        for m in _ANY_NUM_RE.findall(text):
            canon = _canon_number(m)
            if canon:
                numbers.add(canon)
    return numbers, " ".join(parts)


@dataclass
class Violation:
    """One ungrounded critical value the agent tried to speak."""
    kind: str      # "money" | "rate" | "id" | "bignum"
    token: str     # the raw text as it appeared in the utterance
    canon: str     # canonical numeric form used for the grounding check


@dataclass
class VerifyResult:
    ok: bool
    text: str                                  # final text to actually speak
    original: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def intervened(self) -> bool:
        return self.text.strip() != self.original.strip()


def _iter_candidates(sentence: str) -> list[tuple[str, str]]:
    """Yield (kind, raw_token) critical candidates found in a sentence."""
    out: list[tuple[str, str]] = []
    for m in _ID_RE.finditer(sentence):
        out.append(("id", m.group(0)))
    for m in _MONEY_RE.finditer(sentence):
        out.append(("money", m.group(0)))
    for m in _RATE_RE.finditer(sentence):
        out.append(("rate", m.group(0)))
    for m in _BIGNUM_RE.finditer(sentence):
        out.append(("bignum", m.group(0)))
    return out


def _sentence_violations(
    sentence: str, grounded_numbers: set[str], grounded_text: str
) -> list[Violation]:
    violations: list[Violation] = []
    seen: set[str] = set()
    for kind, token in _iter_candidates(sentence):
        # Pull the numeric core out of the raw token (handles "MC 123456").
        nums = _ANY_NUM_RE.findall(token)
        if not nums:
            continue
        for num in nums:
            canon = _canon_number(num)
            if not canon or canon in seen:
                continue
            seen.add(canon)
            grounded = (
                canon in grounded_numbers
                # substring fallback: the exact digits appear in a source
                or num.replace(",", "") in grounded_text.replace(",", "")
            )
            if not grounded:
                violations.append(Violation(kind=kind, token=token.strip(), canon=canon))
    return violations


def verify_utterance(
    utterance: str,
    grounded_sources: Iterable[str],
    *,
    mode: str = "redact",
) -> VerifyResult:
    """Check ``utterance`` against ``grounded_sources`` and return a VerifyResult.

    Args:
        utterance: the draft text the agent is about to speak.
        grounded_sources: strings the agent is ALLOWED to quote from — tool
            outputs gathered this turn plus the caller's recent utterance(s).
        mode: "redact" (default) replaces offending sentences with a hedge;
            "flag" leaves the text intact and only reports violations.

    A value is "grounded" if its canonical numeric form (or exact digit string)
    appears in any grounded source. Ungrounded critical values are treated as
    potential hallucinations.
    """
    if not utterance or not utterance.strip():
        return VerifyResult(ok=True, text=utterance, original=utterance)

    grounded_numbers, grounded_text = _index_sources(grounded_sources)

    out_sentences: list[str] = []
    all_violations: list[Violation] = []
    for sentence in _SENTENCE_SPLIT_RE.split(utterance.strip()):
        if not sentence:
            continue
        v = _sentence_violations(sentence, grounded_numbers, grounded_text)
        if v:
            all_violations.extend(v)
            if mode == "flag":
                out_sentences.append(sentence)
            else:  # redact: drop the offending sentence, insert a single hedge
                if not out_sentences or out_sentences[-1] != HEDGE:
                    out_sentences.append(HEDGE)
        else:
            out_sentences.append(sentence)

    final = " ".join(out_sentences).strip() or HEDGE
    return VerifyResult(
        ok=not all_violations,
        text=final,
        original=utterance,
        violations=all_violations,
    )
