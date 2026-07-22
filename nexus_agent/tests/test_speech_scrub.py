"""
Nexus — Stage-direction leak guard

Everything the LLM emits is spoken verbatim, so any markup it invents gets
PRONOUNCED. A voice that says "warmly" or "asterisk smiles" mid-pitch ends a
client demo. The prompt forbids all of it, but a prompt is guidance — this is the
guarantee.

Both directions are load-bearing, and the second one bit us for real. A first
version stripped any short parenthetical by SHAPE, which duly removed the leaks
and also destroyed legitimate speech: "(thirty) agencies" became "agencies" and
"weeks (depending on scope)" became "weeks". Silently mangling a real sentence is
worse than the leak it prevents, so the rules are whitelist-driven — they match
known stage-direction vocabulary, never a generic pattern.
"""

from __future__ import annotations

import pytest

from state.agents import scrub_for_speech

MARKUP = ("[", "]", "*")


# ── Leaks that must never reach the speaker ──────────────────────────────────

@pytest.mark.parametrize(
    "utterance",
    [
        "[warmly] Hey, I'm Sarah.",
        "[sighs] Yeah, that's a common one.",
        "(energetic) Hi there!",
        "(chuckles) Fair enough.",
        "(pause) So, what do you think?",
        "*smiles* Good to meet you.",
        "*pauses* Let me think.",
        "Energetic: Hey, I'm Sarah.",
        "Tone: friendly. How are things?",
        "Sarah: Hi there.",
        "Agent: We build AI tools.",
        "[sighs] Yeah, (chuckles) that's common.",
    ],
)
def test_stage_directions_are_stripped(utterance):
    out = scrub_for_speech(utterance)
    assert not any(m in out for m in MARKUP), f"markup survived: {out!r}"
    for word in ("warmly", "sighs", "energetic", "chuckles", "smiles", "pauses"):
        assert word not in out.lower(), f"direction word survived: {out!r}"


def test_output_is_never_empty_when_there_were_real_words():
    assert scrub_for_speech("[warmly] Hey there.").strip() == "Hey there."


# ── Real speech that must survive untouched ──────────────────────────────────

@pytest.mark.parametrize(
    "utterance",
    [
        "We work with about (thirty) agencies.",
        "It's roughly 2 to 3 weeks (depending on scope, honestly).",
        "Can I borrow ninety seconds?",
        "That's a good problem to have, honestly.",
        "We build AI tools your clients ask for.",
        "Are you around Tuesday or Thursday?",
        "Yeah, that's frustrating. What happens when it breaks?",
    ],
)
def test_real_speech_is_not_damaged(utterance):
    """A shape-based rule destroyed these. Precision beats recall — the prompt is
    the primary defence, this is only the backstop for known forms."""
    assert scrub_for_speech(utterance) == utterance


def test_markdown_emphasis_keeps_the_word():
    """**Great** is emphasis, not a roleplay action. Deleting the word silently
    ate real speech: '**Great** to hear.' became 'to hear.'"""
    assert scrub_for_speech("**Great** to hear.") == "Great to hear."


def test_punctuation_is_tidied_after_a_removal():
    """A stripped tag must not leave a stranded space before punctuation."""
    assert " ." not in scrub_for_speech("It takes two weeks (pause).")


# ── v3 keeps its tags ────────────────────────────────────────────────────────

def test_elevenlabs_v3_keeps_bracket_tags():
    """v3 PERFORMS [sighs] rather than reading it, so on that engine only, the
    bracket tags must survive."""
    out = scrub_for_speech("[sighs] Yeah, that's common.", keep_bracket_tags=True)
    assert "[sighs]" in out


def test_v3_still_strips_the_forms_it_cannot_perform():
    """Even on v3, asterisks and stage labels are not performable."""
    out = scrub_for_speech("*smiles* Tone: Hello there.", keep_bracket_tags=True)
    assert "*" not in out
    assert "Tone:" not in out


# ── Dotted acronyms ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "utterance,expected",
    [
        ("We build the A.I. products agencies sell.", "We build the AI products agencies sell."),
        ("Our A.P.I. handles that.", "Our API handles that."),
    ],
)
def test_dotted_acronyms_are_flattened(utterance, expected):
    """Deepgram pronounces the periods, so "A.I." came out as "A dot I dot" —
    the most obviously synthetic thing the agent could say."""
    assert scrub_for_speech(utterance) == expected


@pytest.mark.parametrize(
    "utterance",
    [
        "It costs 2.50 per mile.",
        "We build AI products agencies sell.",
        "That's roughly 1.5 times what you pay now.",
    ],
)
def test_decimals_and_plain_acronyms_are_untouched(utterance):
    """The acronym rule must not eat decimal points."""
    assert scrub_for_speech(utterance) == utterance
