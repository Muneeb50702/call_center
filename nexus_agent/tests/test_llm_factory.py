"""
Nexus — LLM factory tests

These lock in a bug that took a working demo off the air.

`llm.FallbackAdapter` defaults to `attempt_timeout=5.0`, and that value becomes
the LLM request deadline. Gemini rejects any deadline under 10s with a
non-retryable HTTP 400 ("Manually set deadline 5s is too short"). So wrapping
Gemini in the adapter — the obvious, correct-looking thing to do for resilience —
made every single Gemini call fail. The agent transcribed the caller perfectly
and then never spoke, which reads exactly like a rate limit and is not one.

The second lesson encoded here: the fallback vendor was Groq, which returns
Cloudflare error 1010 from this network. An unreachable fallback is worse than
none, because config looks healthy while the failover path is inert.
"""

from __future__ import annotations

import pytest

from llm import factory
from llm.google_client import MINIMUM_DEADLINE_SECONDS


@pytest.fixture(autouse=True)
def clear_probe_cache():
    factory._reachable.clear()
    yield
    factory._reachable.clear()


def _reachable(*providers):
    """Force the probe result so tests never touch the network."""
    return lambda p, **kw: p in providers


# ── The deadline bug ──────────────────────────────────────────────────────────

def test_attempt_timeout_never_dips_below_gemini_minimum(monkeypatch):
    """The regression. Below 10s, Gemini 400s every request and the agent is mute."""
    monkeypatch.setattr(factory, "probe", _reachable("gemini", "openai"))
    monkeypatch.setattr(factory, "_build", lambda provider, model, temperature: object())
    # Someone lowers this for "faster failover" and silently breaks every call.
    monkeypatch.setattr(factory.settings, "llm_attempt_timeout", 5.0)

    built = {}

    class FakeAdapter:
        def __init__(self, llms, attempt_timeout=5.0):
            built["attempt_timeout"] = attempt_timeout

    monkeypatch.setattr(factory, "LLMFallbackAdapter", FakeAdapter)
    factory.create_llm(provider="gemini")

    assert built["attempt_timeout"] >= MINIMUM_DEADLINE_SECONDS, (
        "attempt_timeout below Gemini's 10s minimum — every Gemini call will 400"
    )


def test_configured_attempt_timeout_is_honoured_when_above_the_floor(monkeypatch):
    monkeypatch.setattr(factory, "probe", _reachable("gemini", "openai"))
    monkeypatch.setattr(factory, "_build", lambda provider, model, temperature: object())
    monkeypatch.setattr(factory.settings, "llm_attempt_timeout", 20.0)

    built = {}

    class FakeAdapter:
        def __init__(self, llms, attempt_timeout=5.0):
            built["attempt_timeout"] = attempt_timeout

    monkeypatch.setattr(factory, "LLMFallbackAdapter", FakeAdapter)
    factory.create_llm(provider="gemini")
    assert built["attempt_timeout"] == 20.0


# ── Fallback selection ────────────────────────────────────────────────────────

def test_unreachable_vendor_is_never_wired_as_the_fallback(monkeypatch):
    """Groq is Cloudflare-blocked here. It must not occupy the failover slot."""
    monkeypatch.setattr(factory, "probe", _reachable("gemini"))  # groq/openai down
    sentinel = object()
    monkeypatch.setattr(factory, "_build", lambda provider, model, temperature: sentinel)

    class FakeAdapter:
        def __init__(self, *a, **kw):
            raise AssertionError("built a fallback chain with no reachable second vendor")

    monkeypatch.setattr(factory, "LLMFallbackAdapter", FakeAdapter)
    assert factory.create_llm(provider="gemini") is sentinel


def test_every_reachable_vendor_is_chained(monkeypatch):
    """Free tiers allow only ~4-5 turns/min at our prompt size, so the primary
    running dry mid-demo is expected. One spare is not enough — chain them all."""
    monkeypatch.setattr(factory, "probe", _reachable("gemini", "openai", "groq"))
    seen = []
    monkeypatch.setattr(
        factory, "_build",
        lambda provider, model, temperature: seen.append(provider) or object(),
    )
    chained = {}

    def FakeAdapter(llms, attempt_timeout=5.0):
        chained["n"] = len(llms)
        return object()

    monkeypatch.setattr(factory, "LLMFallbackAdapter", FakeAdapter)
    factory.create_llm(provider="gemini")

    assert chained["n"] == 3, "all three reachable vendors should be in the chain"
    assert seen[0] == "gemini", "configured primary must lead"
    assert len(set(seen)) == len(seen), "a vendor must never appear twice"


def test_openai_is_preferred_as_the_first_fallback(monkeypatch):
    """OpenAI has ~13x the free-tier headroom, so it should catch the primary first."""
    monkeypatch.setattr(factory, "probe", _reachable("gemini", "openai", "groq"))
    seen = []
    monkeypatch.setattr(
        factory, "_build",
        lambda provider, model, temperature: seen.append(provider) or object(),
    )
    monkeypatch.setattr(factory, "LLMFallbackAdapter", lambda llms, attempt_timeout=5.0: object())

    factory.create_llm(provider="gemini")
    assert seen[1] == "openai"


def test_dead_primary_promotes_a_reachable_vendor(monkeypatch):
    """Being answered by the second-choice model beats silence on a client call."""
    monkeypatch.setattr(factory, "probe", _reachable("openai"))
    seen = []
    monkeypatch.setattr(
        factory, "_build",
        lambda provider, model, temperature: seen.append(provider) or object(),
    )
    factory.create_llm(provider="gemini")
    assert seen == ["openai"]


def test_openai_primary_still_gets_independent_fallbacks(monkeypatch):
    """The default config: LLM_PROVIDER=openai, with the free tiers as spares."""
    monkeypatch.setattr(factory, "probe", _reachable("gemini", "openai"))
    seen = []
    monkeypatch.setattr(
        factory, "_build",
        lambda provider, model, temperature: seen.append(provider) or object(),
    )
    monkeypatch.setattr(factory, "LLMFallbackAdapter", lambda llms, attempt_timeout=5.0: object())

    factory.create_llm(provider="openai")
    assert seen == ["openai", "gemini"]
    assert seen[0] == "openai", "the configured primary must not be demoted"


def test_unknown_provider_is_rejected_loudly(monkeypatch):
    monkeypatch.setattr(factory, "probe", lambda p, **kw: True)
    with pytest.raises(ValueError, match="unknown LLM provider"):
        factory._build("anthropic-but-not-configured", "some-model", 0.0)


# ── Model resolution ──────────────────────────────────────────────────────────

def test_tier_aliases_never_leak_across_providers(monkeypatch):
    """TIER1_MODEL holds a Groq model (llama-3.1-8b-instant) in this project's
    real .env files. Resolving Gemini's model through a "tier 1 = primary" alias
    sends Google a Llama name and fails every call."""
    monkeypatch.setattr(factory.settings, "tier1_model", "llama-3.1-8b-instant")
    monkeypatch.setattr(factory.settings, "tier2_model", "llama-3.3-70b-versatile")
    monkeypatch.setattr(factory.settings, "gemini_model", "gemini-2.5-flash")

    resolved = factory._model_for("gemini")
    assert "llama" not in resolved.lower(), f"a Groq model leaked into Gemini: {resolved}"
    assert resolved.startswith("gemini")


@pytest.mark.parametrize(
    "provider,expected_prefix",
    [("gemini", "gemini"), ("openai", "gpt"), ("groq", "llama")],
)
def test_each_provider_resolves_its_own_model_family(provider, expected_prefix):
    assert factory._model_for(provider).lower().startswith(expected_prefix)


def test_explicit_model_overrides_the_provider_default(monkeypatch):
    """Tenant config sets llm_model; it must win over the settings default."""
    monkeypatch.setattr(factory, "probe", _reachable("gemini"))
    seen = []
    monkeypatch.setattr(
        factory, "_build",
        lambda provider, model, temperature: seen.append((provider, model)) or object(),
    )
    factory.create_llm(model="gemini-2.0-flash-exp", provider="gemini")
    assert seen[0] == ("gemini", "gemini-2.0-flash-exp")
