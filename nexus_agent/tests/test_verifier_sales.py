"""
Nexus — Verifier tests for the sales persona

The verifier was built for freight dispatch, so it only understood dispatch's
risky values: "$"-prefixed money, per-mile decimals, and prefixed ids. Pointed at
a sales agent it had three holes, all found by actually running it:

    "We cut their costs by 73%."       73 is 2 digits; the big-number rule wants 4+
    "A two million dollar contract."   no "$"; the money rule never matched
    "We did this for Maersk."          not a number; entities were out of scope

The entity hole is the dangerous one. Fabricating a client name to the founder of
the company being represented is instantly recognisable as false to the one
person who knows the real client list — worse than any wrong figure.

Both directions are tested. A verifier that hedges everything is as useless as
one that hedges nothing: the agent would sound evasive on every turn.
"""

from __future__ import annotations

import pytest

from pipeline.verifier import verify_utterance

# What the knowledge base actually returned this turn — the ONLY permitted facts.
GROUNDED = [
    "Lumenia has shipped 50+ systems. Markets served: CA, US, AE, QA. Lumenia built "
    "a SaaS Trucking Management & Dispatch System for a Canadian carrier, and Medaan, "
    "a food delivery platform in Calgary using Laravel.",
    "Lumenia Aria",  # the agent's own company + persona, always legitimate
]


def _blocked(text: str) -> bool:
    return verify_utterance(text, GROUNDED, check_entities=True).intervened


# ── Regressions: each of these leaked before ─────────────────────────────────

@pytest.mark.parametrize(
    "utterance",
    [
        "We cut their costs by 73% in the first quarter.",
        "Costs dropped 40 percent after launch.",
        "Efficiency went up 25%.",
    ],
)
def test_invented_percentages_are_blocked(utterance):
    """The signature fabricated sales metric. Only 1-2 digits, so the 4+ digit
    big-number rule never saw it."""
    assert _blocked(utterance)


@pytest.mark.parametrize(
    "utterance",
    [
        "We did this on a two million dollar contract.",
        "Our platform handles 40 thousand orders a day.",
        "That project came in around 45 thousand.",
    ],
)
def test_money_written_as_words_is_blocked(utterance):
    """No '$' character, so the money rule never matched it."""
    assert _blocked(utterance)


@pytest.mark.parametrize(
    "utterance",
    [
        "We did this for Maersk.",
        "We delivered it for DHL and Walmart last year.",
        "We've done work for Shopify.",
        "Our client Acme saw great results.",
    ],
)
def test_invented_client_names_are_blocked(utterance):
    """The fatal one: naming a client the listener knows they never were."""
    assert _blocked(utterance)


def test_percent_regex_matches_before_a_space():
    """The bug: a trailing \\b after '%' demands a word char next, so '73% in'
    never matched. Only the spelled-out 'percent' form can take a boundary."""
    assert _blocked("We cut costs by 73% in the first quarter.")
    assert _blocked("We cut costs by 73%.")
    assert _blocked("We cut costs by 73%")


# ── Grounded and harmless speech must pass ───────────────────────────────────

@pytest.mark.parametrize(
    "utterance",
    [
        "We've shipped 50+ systems.",
        "Medaan was a food delivery build in Calgary, on Laravel.",
        "We built a trucking dispatch platform for a carrier in Canada.",
    ],
)
def test_grounded_facts_are_spoken(utterance):
    assert not _blocked(utterance)


@pytest.mark.parametrize(
    "utterance",
    [
        "I'm Aria, calling from Lumenia.",
        "Yeah, that's a common one. How many people does that tie up?",
        "That's frustrating. What happens today when it breaks?",
        "Honestly, I'd need to check the exact number and come back to you.",
        "Hm. Ouch. Yeah, we see that a lot with dispatch teams.",
        "Is now a terrible time?",
        "Are you around Tuesday or Thursday?",
    ],
)
def test_natural_speech_is_not_over_hedged(utterance):
    """A verifier that hedges ordinary conversation makes the agent sound evasive
    on every turn, which fails the demo just as surely as a hallucination."""
    assert not _blocked(utterance)


def test_agent_may_always_name_its_own_company():
    """Callers pass the company/persona names in as grounded. Without that the
    agent gets hedged for introducing itself on a turn with no tool call."""
    result = verify_utterance(
        "I'm Aria with Lumenia.", ["Lumenia Aria"], check_entities=True
    )
    assert not result.intervened


def test_country_names_are_not_treated_as_clients():
    """A source saying 'Canadian carrier' does not contain the substring 'canada',
    so the country was hedged on every mention. The lie is never the country."""
    assert not _blocked("We work with carriers across Canada and the US.")


# ── Unit discipline ──────────────────────────────────────────────────────────

def test_a_bare_digit_does_not_license_the_same_digit_as_a_percentage():
    """'50+ systems' in a source must not authorise '50% faster' in the reply —
    the number matches but the unit is a fabrication."""
    assert _blocked("That made them 50% faster.")


# ── Dispatch persona is unchanged ────────────────────────────────────────────

def test_entity_checking_is_off_by_default():
    """Dispatch proper nouns are mostly cities and facilities the caller just
    said; entity checking there costs false positives for no benefit."""
    result = verify_utterance("We did this for Maersk.", GROUNDED)
    assert not result.intervened


def test_dispatch_money_and_ids_still_blocked_without_entity_checking():
    assert verify_utterance("The rate is $2,300.", GROUNDED).intervened
    assert verify_utterance("That's load BK-99382.", GROUNDED).intervened
