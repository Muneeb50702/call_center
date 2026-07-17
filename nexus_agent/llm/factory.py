"""
Nexus — LLM factory

Builds the call's LLM: a primary, plus a fallback from a *different vendor*, so
that a rate limit or an outage on one does not take the call down.

This exists because of one production failure worth remembering in detail, since
its symptom pointed at entirely the wrong cause.

**`FallbackAdapter`'s default `attempt_timeout=5.0` silently broke both LLMs.**
That timeout becomes the request deadline for every attempt:

- Gemini rejects any deadline under 10s with a NON-RETRYABLE 400
  ("Manually set deadline 5s is too short"), so every Gemini call failed outright.
- Groq accepted the 5s but Llama-70B needed longer once the chat context grew
  with retrieved chunks, so it was cancelled — surfacing as "Connection error".

Both legs died and the agent went mute. It transcribed the caller perfectly and
never spoke, which looks exactly like a rate limit and is not one: a rate limit is
429, this was 400. The first turn of each call worked because the opening prompt
was short enough for Groq to answer inside 5s, which made it look like the system
"degraded over the call" rather than being broken from the start.

`settings.llm_attempt_timeout` is therefore floored at Gemini's minimum deadline.

Why a different vendor for the fallback: a second model behind the same API key
shares the same quota and the same outage. On a live client demo the failure to
survive is "Gemini free tier 429s at turn thirty", and only another vendor
survives that.
"""

from __future__ import annotations

import time

import structlog
from livekit.agents.llm import FallbackAdapter as LLMFallbackAdapter

from config.settings import settings
from llm.google_client import MINIMUM_DEADLINE_SECONDS, create_google_llm

logger = structlog.get_logger()

# Ordered by preference when picking a fallback vendor.
_FALLBACK_ORDER = ["openai", "gemini", "groq"]

# Cached across calls within a worker process — a health probe per call would add
# a network round-trip to call setup for no benefit.
_reachable: dict[str, bool] = {}


def _has_key(provider: str) -> bool:
    return bool({
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "groq": settings.groq_api_key,
    }.get(provider, ""))


def probe(provider: str, *, timeout: float = 8.0) -> bool:
    """Check a provider actually answers, once per worker process.

    Best-effort and cached. A provider that fails the probe is skipped when
    assembling the fallback chain.

    The probe MUST use httpx, because that is what the provider SDKs use, and the
    HTTP client is not an implementation detail here. An earlier version used
    urllib and reported Groq as dead with Cloudflare error 1010 — Cloudflare bans
    the `Python-urllib/3.x` User-Agent at the edge, while the same request over
    httpx returns 200. That false negative would have disabled a perfectly
    healthy fallback. Probe with the client you actually call with.
    """
    if provider in _reachable:
        return _reachable[provider]
    if not _has_key(provider):
        _reachable[provider] = False
        return False

    import httpx

    url, headers = {
        "gemini": (
            f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.gemini_api_key}",
            {},
        ),
        "openai": (
            "https://api.openai.com/v1/models",
            {"Authorization": f"Bearer {settings.openai_api_key}"},
        ),
        "groq": (
            "https://api.groq.com/openai/v1/models",
            {"Authorization": f"Bearer {settings.groq_api_key}"},
        ),
    }[provider]

    try:
        response = httpx.get(url, headers=headers, timeout=timeout)
        ok = response.status_code == 200
        if not ok:
            logger.warning(
                "llm_provider_unreachable",
                provider=provider,
                status=response.status_code,
                hint=(
                    "401/403 here means the key is rejected — a Cloudflare edge block "
                    "would not reach this code path via httpx"
                    if response.status_code in (401, 403)
                    else "provider returned a non-200"
                ),
            )
    except Exception as e:
        ok = False
        logger.warning("llm_provider_unreachable", provider=provider, error=str(e)[:120])

    if ok:
        logger.info("llm_provider_ready", provider=provider)
    _reachable[provider] = ok
    return ok


async def warm_prompt_cache(model, system_prompt: str) -> float | None:
    """Fire one throwaway generation to warm the provider's prompt-prefix cache.

    Measured on gpt-4o-mini with this agent's ~1,700-token system prompt:

        first call with a cold prefix : 2442ms TTFT
        subsequent calls (cached)     :  852ms median, 708ms best

    That ~1.6s penalty lands entirely on the FIRST turn of a call — which is the
    agent's greeting, i.e. the first thing a prospect ever hears and the whole
    first impression of the product. Paying it here, during connection setup
    while the human is still saying hello, moves it off the critical path.

    Every state prompt shares an identical base prefix (see llm/sales_prompts.py),
    so warming once covers all of them — providers cache the longest matching
    prefix, not the exact string.

    Costs ~1,700 input tokens (fractions of a cent). Best-effort: never let a
    warmup failure touch the call.
    """
    from livekit.agents import llm as lkllm

    try:
        started = time.perf_counter()
        chat_ctx = lkllm.ChatContext()
        chat_ctx.add_message(role="system", content=system_prompt)
        # One token of output is enough — the point is the input prefix.
        chat_ctx.add_message(role="user", content="Reply with the single word: ok")
        async for _ in model.chat(chat_ctx=chat_ctx):
            pass
        elapsed = (time.perf_counter() - started) * 1000
        logger.info("llm_prompt_cache_warmed", elapsed_ms=round(elapsed))
        return elapsed
    except Exception as e:
        logger.debug("llm_prompt_cache_warm_failed", error=str(e)[:120])
        return None


def _build(provider: str, model: str, temperature: float):
    if provider == "gemini":
        return create_google_llm(model_name=model or settings.tier1_model, temperature=temperature)
    if provider == "openai":
        from llm.openai_client import create_openai_llm
        return create_openai_llm(model_name=model or settings.openai_model, temperature=temperature)
    if provider == "groq":
        from llm.groq_client import create_groq_llm
        return create_groq_llm(model_name=model or settings.tier2_model, temperature=temperature)
    raise ValueError(f"unknown LLM provider: {provider!r}")


def _model_for(provider: str) -> str:
    """The default model for a provider.

    Reads the per-provider settings, never the tier aliases: TIER1_MODEL holds a
    Groq model name in this project's real .env files, so resolving Gemini
    through "tier 1 = primary" hands Google a Llama model.
    """
    return {
        "gemini": settings.gemini_model,
        "openai": settings.openai_model,
        "groq": settings.groq_model,
    }.get(provider, "")


def create_llm(*, model: str = "", temperature: float = 0.0, provider: str = ""):
    """Build the LLM for a call.

    Returns a bare LLM when no usable second vendor exists, and a FallbackAdapter
    when one does. Never returns an adapter wrapping an unreachable provider.
    """
    primary_provider = provider or settings.llm_provider

    if not probe(primary_provider):
        # Primary is down. Rather than fail the call, promote the first reachable
        # vendor — being answered by the second-choice model beats silence.
        for candidate in _FALLBACK_ORDER:
            if candidate != primary_provider and probe(candidate):
                logger.error(
                    "llm_primary_unreachable_promoting_fallback",
                    primary=primary_provider, promoted=candidate,
                )
                primary_provider, model = candidate, ""
                break
        else:
            # Nothing answered. Build the configured primary anyway so the error
            # surfaces as itself rather than as a confusing NoneType later.
            logger.error("llm_no_reachable_provider", configured=primary_provider)
            return _build(primary_provider, model or _model_for(primary_provider), temperature)

    primary_model = model or _model_for(primary_provider)
    primary = _build(primary_provider, primary_model, temperature)

    # Chain EVERY reachable vendor, not just one. Measured free-tier headroom at
    # our ~3k-token prompt is brutal — Gemini free allows 5 turns/min (5 RPM) and
    # Groq free allows ~4 (12k TPM ÷ 3k) — so during a long demo the primary
    # running dry is the expected case, not the exceptional one. A second spare
    # vendor is what keeps the call alive after the first one taps out.
    chain = [primary]
    # Track (provider, model) pairs so the log reports what was ACTUALLY built.
    # An earlier version logged _model_for(provider) instead, which printed
    # "gemini:llama-3.1-8b-instant" for a session genuinely running gemini-2.5-flash
    # — a log that invents a state the system was never in is worse than no log.
    used = [(primary_provider, primary_model)]
    for candidate in _FALLBACK_ORDER:
        if candidate in (p for p, _ in used) or not probe(candidate):
            continue
        candidate_model = _model_for(candidate)
        try:
            chain.append(_build(candidate, candidate_model, temperature))
            used.append((candidate, candidate_model))
        except Exception as e:
            logger.warning("llm_fallback_build_failed", provider=candidate, error=str(e))

    if len(chain) == 1:
        logger.warning(
            "llm_no_fallback",
            primary=primary_provider,
            impact="a rate limit or outage on the primary will drop the call mid-conversation",
            hint="set OPENAI_API_KEY — free tiers allow only ~4-5 turns/min",
        )
        return primary

    # Floored at Gemini's server-side minimum deadline. Below it, Gemini 400s
    # every request — see llm/google_client.py. Measured cost of the wrapper on
    # the happy path: none (225.1ms bare vs 214.8ms wrapped, i.e. within noise).
    attempt_timeout = max(settings.llm_attempt_timeout, MINIMUM_DEADLINE_SECONDS)

    logger.info(
        "llm_chain_ready",
        chain=" -> ".join(f"{p}:{m}" for p, m in used),
        attempt_timeout=attempt_timeout,
    )
    return LLMFallbackAdapter(chain, attempt_timeout=attempt_timeout)
