"""
Nexus — Deepgram STT

Nova-3 with keyterm prompting, for two personas: freight dispatch (noisy truck
cab, dense jargon) and outbound sales (proper nouns the agent must not fumble).

This module previously documented Nova-3 while actually loading
`nova-2-conversationalai`, and boosted vocabulary with Nova-2's `keywords`
parameter — a blunt instrument that raises a token's acoustic prior globally, so
it hallucinates the boosted word into unrelated audio. The old code even had to
divide every weight by three to stop "Hello" transcribing as "Haul", which is a
workaround for the wrong mechanism rather than a tuning problem.

Nova-3's `keyterm` is a different thing: contextual term biasing, applied with
awareness of the surrounding words rather than as a flat prior. No weights, no
hallucination tax, and better accuracy on exactly the terms that matter. It is
Nova-3 only, which is why the model change and the parameter change ship
together.

Latency: `no_delay=True` and `endpointing_ms=25` keep interim results flowing so
the semantic turn detector and preemptive generation both get transcript text as
early as possible.
"""

from livekit.plugins import deepgram

# Deepgram caps keyterms per request, and each one costs a little accuracy
# elsewhere, so these lists are the terms that are genuinely misheard and
# genuinely matter — not every word in the domain.
MAX_KEYTERMS = 100

# ── Freight dispatch vocabulary ──
# Industry terms an out-of-the-box model reliably mangles. Plain terms now: no
# weights, because keyterm prompting does not take them.
DISPATCH_KEYTERMS = [
    # Equipment
    "reefer", "flatbed", "dry van", "bobtail", "step deck", "lowboy",
    "conestoga", "hot shot", "box truck",
    # Documents
    "BOL", "POD", "rate con", "rate confirmation", "lumper receipt",
    # Operations
    "deadhead", "detention", "TONU", "drayage", "drop and hook",
    "live load", "live unload", "backhaul", "accessorial",
    # Shipping modes
    "LTL", "FTL", "partial",
    # Identifiers
    "MC number", "DOT number", "PRO number", "SCAC",
    # Rates
    "per mile", "all in", "line haul", "fuel surcharge",
    # Hours of service
    "HOS", "ELD", "sleeper berth",
    # Parties
    "FMCSA", "broker", "shipper", "consignee", "dispatcher",
    # Check calls & exceptions
    "check call", "ETA", "breakdown", "roadside assistance",
]

# ── Outbound sales vocabulary ──
# On a sales call the words that must land are product and company names. A
# generic model has no prior for "Lumenia" and will produce "Luminaria",
# "Lumina", "Lumen AI" — and an SDR that cannot pronounce its own employer's
# name back to a prospect is a dead demo. These are the highest-value keyterms in
# the entire system.
SALES_KEYTERMS = [
    # Technical terms that come up on discovery calls
    "API", "SaaS", "CRM", "ERP", "LLM", "RAG", "webhook", "integration",
    "multi-tenant", "onboarding", "automation", "agentic", "workflow",
    # Stack names a prospect might name-drop
    "Laravel", "React", "Next.js", "Node", "Python", "AWS", "Stripe",
    "QuickBooks", "Shopify", "WordPress", "Twilio", "Salesforce", "HubSpot",
    # Commercial vocabulary
    "proof of concept", "POC", "MVP", "scope", "retainer", "SOW",
    "milestone", "discovery call", "budget", "timeline", "roadmap",
]


def create_stt(
    extra_keywords: list[str] | None = None,
    *,
    profile: str = "dispatch",
) -> deepgram.STT:
    """Create a Nova-3 STT tuned for the given persona.

    Args:
        extra_keywords: Tenant-specific terms — company name, product names,
            client names. These matter most, so they go first in the list.
        profile: "dispatch" for freight, "sales" for outbound SDR. Selects the
            base vocabulary; an unknown profile gets no base terms rather than
            the wrong ones.
    """
    base = {"dispatch": DISPATCH_KEYTERMS, "sales": SALES_KEYTERMS}.get(profile, [])

    # Tenant terms lead: they are the ones the model has never seen and the ones
    # a caller will notice being mispronounced. If anything gets truncated at the
    # cap, it should be generic domain vocabulary, not the company's own name.
    keyterms: list[str] = []
    seen: set[str] = set()
    for term in list(extra_keywords or []) + base:
        # Tolerate legacy "term:weight" entries still sitting in tenants.json.
        term = term.rsplit(":", 1)[0].strip() if ":" in term else term.strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            keyterms.append(term)

    return deepgram.STT(
        model="nova-3",
        language="en-US",
        keyterm=keyterms[:MAX_KEYTERMS],
        # Emit interims immediately. The semantic turn detector and preemptive
        # generation both read transcript text before the turn is final, so any
        # buffering here is charged directly to response latency.
        no_delay=True,
        endpointing_ms=25,
        interim_results=True,
        # Keep fillers. They look like noise but they are turn-taking signal: an
        # "um" tells the semantic turn detector the caller is thinking, not done,
        # which stops the agent cutting them off mid-thought.
        filler_words=True,
        smart_format=True,
        punctuate=True,
    )
