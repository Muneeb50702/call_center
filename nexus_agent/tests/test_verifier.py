"""
Tests for the anti-hallucination verifier (pipeline/verifier.py).

Dependency-light so it runs under pytest OR as a plain script:
    python3 tests/test_verifier.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.verifier import verify_utterance, HEDGE, _canon_number  # noqa: E402


def test_grounded_money_passes():
    r = verify_utterance(
        "I can do this load for $2,300 all in.",
        ["Load L-1 rate is $2300 for the lane"],
    )
    assert r.ok
    assert r.text == "I can do this load for $2,300 all in."
    assert not r.intervened


def test_ungrounded_money_is_redacted():
    r = verify_utterance(
        "I can pay you $2,800 for this one.",
        ["Best available rate on this lane is $2300"],
    )
    assert not r.ok
    assert HEDGE in r.text
    assert "$2,800" not in r.text
    assert r.violations[0].kind == "money"


def test_user_readback_mc_passes():
    # The caller stated their MC; the agent reads it back to confirm. It is not
    # in any tool output but IS grounded in the caller's utterance.
    r = verify_utterance(
        "Got it, so that's MC 123456, correct?",
        ["caller said: my mc number is 123456"],
    )
    assert r.ok, r.violations


def test_ungrounded_mc_is_redacted():
    r = verify_utterance(
        "Your authority looks good under MC 987654.",
        ["Verification returned status active for MC 123456"],
    )
    assert not r.ok
    assert HEDGE in r.text
    assert any(v.kind == "id" for v in r.violations)


def test_grounded_per_mile_rate_passes():
    r = verify_utterance(
        "That works out to 2.30 per mile.",
        ["rate_per_mile: 2.3, miles: 1000"],
    )
    assert r.ok, r.violations


def test_ungrounded_per_mile_rate_redacted():
    r = verify_utterance(
        "That works out to 3.50 per mile.",
        ["rate_per_mile: 2.3"],
    )
    assert not r.ok
    assert any(v.kind == "rate" for v in r.violations)


def test_small_counts_are_ignored():
    # "3 loads" and "2 hours" must NOT trip the verifier — no grounding needed.
    r = verify_utterance(
        "I found 3 loads for you, and detention starts after 2 hours.",
        [],
    )
    assert r.ok, r.violations
    assert not r.intervened


def test_mixed_sentence_only_bad_redacted():
    r = verify_utterance(
        "I found a load from Chicago to Dallas. The rate is $9,999.",
        ["Load LD-7 Chicago to Dallas, rate $2400"],
    )
    assert not r.ok
    assert "Chicago to Dallas" in r.text   # good sentence survives
    assert "$9,999" not in r.text          # bad sentence redacted
    assert HEDGE in r.text


def test_decimal_and_comma_normalization():
    assert _canon_number("$2,300") == _canon_number("2300")
    assert _canon_number("2.30") == _canon_number("2.3")
    assert _canon_number("1234567") == "1234567"   # DOT number, not mangled


def test_empty_utterance():
    r = verify_utterance("", ["anything"])
    assert r.ok
    assert r.text == ""


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL  {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failures}/{len(fns)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
