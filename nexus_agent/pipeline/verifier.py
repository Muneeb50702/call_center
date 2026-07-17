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
- **Conservative.** Only the highest-risk categories are enforced. Small counts
  ("3 loads", "2 hours", "one moment") are intentionally ignored so the agent is
  not constantly hedging on harmless numbers.

Threat model, and why it grew
-----------------------------
This started as a freight-dispatch guard, so it only understood dispatch's risky
values: ``$``-prefixed money, per-mile decimals, and prefixed ids (MC/DOT/load).
When the same guard was pointed at an outbound SALES agent, three holes opened
that a live test caught immediately — the agent was free to say all of these
with nothing behind them:

    "We cut their costs by 73%."                  → 73 is 2 digits; BIGNUM wants 4+
    "A two million dollar contract."              → no "$" sign; MONEY never matched
    "We did this for Maersk."                     → not a number at all; out of scope

The third is the worst. Fabricating a *client name* to the founder of the company
being represented is instantly, obviously false to the one person in the room who
knows the real client list — it destroys the deal in a way a wrong number does
not. Percentages and word-form money are the classic invented "results" a sales
LLM reaches for when it wants to sound impressive.

So the guard now also covers percentages, money written as words, and capitalised
entities that appear in no grounded source. Entity checking is necessarily
heuristic; see ``_ENTITY_STOPWORDS`` for how false positives are held down, and
note that a false positive only costs a hedge while a false negative costs the
deal.
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

# Money written as words: "2 million dollars", "45 thousand dollars", "5k".
# A sales agent reaches for these constantly and none of them carry a "$", so
# _MONEY_RE never saw them.
_WORD_MONEY_RE = re.compile(
    r"\b\d[\d,.]*\s*(?:k|m|bn)\b"
    r"|\b\d[\d,.]*\s*(?:hundred|thousand|million|billion)\b"
    r"|\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:hundred|thousand|million|billion)\b",
    re.IGNORECASE,
)

# Percentages: "73%", "up 40 percent". The signature invented sales metric, and
# usually only 1-2 digits, so _BIGNUM_RE (4+ digits) never caught them.
#
# NOTE the two alternatives. A single `(?:%|percent)\b` looks tidier and is
# broken: "%" is a non-word character, so a trailing \b after it demands a word
# character next, and "73% in the quarter" (percent-sign then space) never
# matches. That bug let every "%" figure through. Only the word form takes \b.
_PERCENT_RE = re.compile(
    r"\b\d[\d,.]*\s*%|\b\d[\d,.]*\s*percent\b",
    re.IGNORECASE,
)

# Per-mile rate written as a bare decimal: 2.30, 3.1  (0.50–9.99 range)
_RATE_RE = re.compile(r"(?<![\d.])[0-9]\.\d{1,2}(?![\d.])")

# Any standalone number of 4+ digits (ids, big dollar amounts, weights) —
# these are almost never safe to invent.
_BIGNUM_RE = re.compile(r"(?<![\d.])\d{4,}(?![\d.])")

# Broad number matcher used to index the grounded sources.
_ANY_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# ── Entity (client/company name) checking ────────────────────────────────────
# A capitalised token that appears in no grounded source is a candidate invented
# entity. This is a heuristic, so the stoplist matters more than the regex: a
# false positive costs one hedged sentence, but a false negative means the agent
# names a client that does not exist to the person who knows every real one.

_CAP_TOKEN_RE = re.compile(r"\b[A-Z][A-Za-z0-9&.\-]{2,}\b")

# Never treated as an invented entity. Sentence-initial words are also skipped
# (see _entity_violations) since capitalisation there carries no signal.
_ENTITY_STOPWORDS = frozenset(
    w.lower()
    for w in """
    I I'd I'll I'm I've We We'd We'll We're We've You You'd You'll You're You've
    They They're He She It Its This That These Those There Here What When Where
    Which Who Why How And But Or So If Then Than Because While Although Yes No
    Not Sure Right Okay OK Yeah Yep Nope Hi Hey Hello Thanks Thank Please Sorry
    Let Lets Let's Well Actually Honestly Basically Look Listen Great Good Nice
    Perfect Absolutely Definitely Maybe Perhaps Monday Tuesday Wednesday Thursday
    Friday Saturday Sunday January February March April May June July August
    September October November December Today Tomorrow Yesterday Morning
    Afternoon Evening Tonight AI API APIs SaaS CRM ERP LLM RAG MVP POC SOW ROI
    B2B B2C UI UX QA IT HR CEO CTO CFO COO VP The A An Our Your Their His Her

    Canada Canadian America American USA US UK Britain British England Australia
    Australian Pakistan Pakistani India Indian UAE Emirates Qatar Europe European
    Asia Asian Africa German France French Spain Spanish Mexico Dutch Italy
    Italian China Chinese Japan Japanese Toronto Vancouver Montreal London
    Dubai Karachi Islamabad York Francisco Angeles Texas California Florida
    """.split()
)
# Geography is stoplisted deliberately. Countries and demonyms are high-frequency
# and low-risk — the lie a sales agent tells is "we built this for Maersk", never
# "we work in Canada". They also collide constantly: a source saying "Canadian
# carrier" does not contain the substring "canada", so every mention of the
# country got hedged. Cities not listed here still have to be grounded, which is
# fine because the KB names the ones that matter.


def _entity_candidates(sentence: str) -> list[str]:
    """Capitalised tokens in a sentence, minus the sentence-initial word."""
    tokens = _CAP_TOKEN_RE.findall(sentence)
    if not tokens:
        return []
    stripped = sentence.strip()
    # Drop the first word: capitalisation at a sentence start means nothing.
    if stripped and tokens and stripped.startswith(tokens[0]):
        tokens = tokens[1:]
    return [t for t in tokens if t.lower() not in _ENTITY_STOPWORDS]

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
    # Distinct kind from plain "money" on purpose. "$"-money is checked by
    # canonical number, so "$2,300" correctly matches a source saying "$2300".
    # Word-money must instead be checked as a PHRASE: the digits in "40 thousand"
    # are just "40", which a source mentioning any 40 would wrongly authorise.
    for m in _WORD_MONEY_RE.finditer(sentence):
        out.append(("word_money", m.group(0)))
    for m in _PERCENT_RE.finditer(sentence):
        out.append(("percent", m.group(0)))
    for m in _RATE_RE.finditer(sentence):
        out.append(("rate", m.group(0)))
    for m in _BIGNUM_RE.finditer(sentence):
        out.append(("bignum", m.group(0)))
    return out


def _entity_violations(sentence: str, grounded_text: str) -> list[Violation]:
    """Flag capitalised entities that appear in no grounded source.

    Catches the invented client name — the failure that ends a sales call the
    instant the listener recognises a company they have never worked with.
    """
    violations: list[Violation] = []
    seen: set[str] = set()
    for token in _entity_candidates(sentence):
        key = token.lower().rstrip(".")
        if key in seen:
            continue
        seen.add(key)
        if key not in grounded_text:
            violations.append(Violation(kind="entity", token=token, canon=key))
    return violations


def _sentence_violations(
    sentence: str,
    grounded_numbers: set[str],
    grounded_text: str,
    *,
    check_entities: bool = False,
) -> list[Violation]:
    violations: list[Violation] = []
    seen: set[str] = set()
    squashed_sources = grounded_text.replace(" ", "").replace(",", "")

    for kind, token in _iter_candidates(sentence):
        # Pull the numeric core out of the raw token (handles "MC 123456").
        nums = _ANY_NUM_RE.findall(token)

        if not nums:
            # Word-form money ("two million") carries no digits at all, so the
            # numeric path below cannot see it — it used to fall straight through
            # and get spoken. Ground it on the phrase instead.
            phrase = token.lower().strip()
            if phrase and phrase in seen:
                continue
            seen.add(phrase)
            if phrase and phrase.replace(" ", "") not in squashed_sources:
                violations.append(Violation(kind=kind, token=token.strip(), canon=phrase))
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
            # Unit discipline, for percentages and word-money ONLY. These must be
            # grounded as the whole unit, not as a loose digit: a source saying
            # "50+ systems" must not authorise "50% faster" or "50 thousand".
            #
            # Deliberately NOT applied to "$"-money, which is matched by canonical
            # number so that "$2,300" still matches a source written "$2300".
            # Comparing those raw would fail on the comma and hedge a real rate.
            if grounded and kind in ("percent", "word_money"):
                grounded = token.lower().replace(" ", "").replace(",", "") in squashed_sources
            if not grounded:
                violations.append(Violation(kind=kind, token=token.strip(), canon=canon))

    if check_entities:
        violations.extend(_entity_violations(sentence, grounded_text))
    return violations


def verify_utterance(
    utterance: str,
    grounded_sources: Iterable[str],
    *,
    mode: str = "redact",
    check_entities: bool = False,
) -> VerifyResult:
    """Check ``utterance`` against ``grounded_sources`` and return a VerifyResult.

    Args:
        utterance: the draft text the agent is about to speak.
        grounded_sources: strings the agent is ALLOWED to quote from — tool
            outputs gathered this turn plus the caller's recent utterance(s).
            For entity checking, callers MUST also include the agent's own
            company and persona names, or the agent gets flagged for saying who
            it works for on a turn that made no tool call.
        mode: "redact" (default) replaces offending sentences with a hedge;
            "flag" leaves the text intact and only reports violations.
        check_entities: also flag capitalised entities absent from every source.
            On for the sales persona, where an invented client name is fatal. Off
            for dispatch, where proper nouns are mostly place names the caller
            supplied and the false-positive cost is not worth it.

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
        v = _sentence_violations(
            sentence, grounded_numbers, grounded_text, check_entities=check_entities
        )
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
