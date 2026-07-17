"""
Nexus — OpenAI LLM Client

Direct OpenAI, as an alternative primary or as the fallback leg.

This exists because Groq — the original fallback — is unreachable from the
deployment network: `api.groq.com` returns Cloudflare error 1010 ("banned based
on browser signature"), which is an edge-level block on the request's origin, not
an API key problem. A fallback that cannot be dialled is worse than no fallback,
because it makes the failover path look healthy in config while doing nothing.

Model guidance, since it is easy to pick wrong here:

- `gpt-4o-mini` is cheap and fast, but it is a 2024-era small model and is
  noticeably weaker at holding a nuanced persona over a long call. It tends to
  drift toward generic-salesperson register — which is exactly the "overacting"
  failure mode we are trying to avoid.
- `gpt-4o` follows tone instructions considerably better and is the one to reach
  for if OpenAI is the primary and delivery quality matters more than cost.
- `gemini-2.5-flash` is the current default primary: comparable latency, strong
  instruction-following, implicit prompt caching (which the shared prompt prefix
  is built around), and the key is already provisioned and working.
"""

from livekit.plugins import openai

from config.settings import settings


def create_openai_llm(
    model_name: str = "",
    temperature: float | None = None,
) -> openai.LLM:
    """
    Creates a LiveKit-compatible LLM instance using OpenAI.

    Args:
        model_name: OpenAI model ID. Defaults to settings.openai_model.
        temperature: LLM temperature. Defaults to settings.groq_temperature.

    Raises:
        ValueError: if no OPENAI_API_KEY is configured. Raising here rather than
            returning a dead client means a misconfiguration surfaces at worker
            start, not as silence on a live call.
    """
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set — add it to .env to use the OpenAI provider"
        )

    return openai.LLM(
        api_key=settings.openai_api_key,
        model=model_name or settings.openai_model,
        temperature=temperature if temperature is not None else settings.groq_temperature,
    )
