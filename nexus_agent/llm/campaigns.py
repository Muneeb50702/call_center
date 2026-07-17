"""
Nexus — Outbound campaigns

A campaign hardcodes WHO the agent is calling and WHY, so the agent stops being a
generic SDR and starts sounding like someone who called on purpose.

Without this, every call opens cold in both senses: the agent knows the company
it represents (via the knowledge base) but nothing about the person answering, so
it has to ask basic qualifying questions before it can say anything useful. That
is what reads as "inconsistent" — the agent improvises a different call each time
because nothing pins down the scenario.

A campaign pins three things:
  - the prospect  : who picks up, and what their world looks like
  - the hypotheses: the pains people like them usually have
  - the mapping   : which REAL capability answers each pain

The hypotheses are the reason the agent can lead with authority. But note how they
are phrased below — every one is a QUESTION, never a statement. "Most agencies
your size are drowning in client reporting — is that you?" is authoritative and
survives being wrong. "I know you're drowning in client reporting" is a guess
dressed as a fact, and the moment it misses, the prospect stops listening. The
first invites a correction that becomes discovery; the second ends the call.

Grounding is unchanged. A campaign may assert things about the PROSPECT'S WORLD
(general industry truth, framed as a hypothesis). It may never assert a new
capability, client, price, or result for the company being represented — those
still come only from `search_knowledge_base` and are still enforced by the pre-TTS
verifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Campaign:
    """One hardcoded outbound scenario."""

    campaign_id: str
    prospect_label: str          # "the owner of a digital marketing agency"
    prospect_world: str          # what their day looks like — grounds the empathy
    reason_for_call: str         # the ONE line that justifies the interruption
    hypotheses: tuple[str, ...]  # pain guesses, each phrased as a question
    offer_map: tuple[tuple[str, str], ...]  # (their pain, our real capability)
    proof_search: str            # the KB query that fetches relevant evidence
    close_target: str            # what "won" means on THIS call
    energy: str                  # delivery note for the opener

    def prompt_block(self) -> str:
        """Render the campaign as a prompt section."""
        hyp = "\n".join(f'  - "{h}"' for h in self.hypotheses)
        offers = "\n".join(f"  - If they say: {pain}\n      → You offer: {cap}"
                           for pain, cap in self.offer_map)
        return f"""--- WHO YOU ARE CALLING (this call, specifically) ---
You are calling {self.prospect_label}.

THEIR WORLD — you already understand this, so do not ask them to explain it:
{self.prospect_world}

WHY YOU CALLED — this is your one justification for interrupting them:
{self.reason_for_call}

LEAD WITH A HYPOTHESIS, NOT A QUESTIONNAIRE:
You are not a survey. You already know what people in their seat struggle with,
and saying so is what separates you from every other cold caller who opens with
"so tell me about your business". Pick the ONE most likely pain and put it to them
as a question they can correct:
{hyp}

Say it like you have had this conversation fifty times, because you have. Then
STOP and let them confirm or correct you. Their correction IS your discovery — you
do not need a script of questions, you need one good guess and then silence.

NEVER say "I know you're struggling with X" as a statement of fact. You do not
know. You are guessing, well. A guess put as a question sounds expert and survives
being wrong; a guess put as a fact ends the call the moment it misses.

PRESCRIBE — do not present a menu:
When they confirm a pain, do not list options. Name the ONE thing that solves it
and say you can build it. Confidence is specificity.
{offers}

Before you name any capability, call `search_knowledge_base` (start with
"{self.proof_search}") and use ONLY what comes back. Prescribing something the
company does not actually do is the fastest way to lose a deal you had already won.

WHAT WINNING LOOKS LIKE ON THIS CALL:
{self.close_target}

DELIVERY:
{self.energy}
"""


# ── The demo campaign ────────────────────────────────────────────────────────
#
# Every capability in offer_map is real and present in the Lumenia corpus —
# verified against the knowledge base, not invented for the pitch:
#   WhatsApp chatbots / lead-qualification bots  → chatbot development page
#   Website AI assistants                        → chatbot development page
#   Multi-tier reseller hierarchy, white-label   → Reseller Domain Platform project
#   Multi-tenant SaaS, RBAC, Stripe              → SaaS platform service page
#   AI agentic automation / workflow automation  → AI Agentic Automation service
#   Client dashboards                            → Ecommerce Dashboard (Hakkidd)
#
# The angle: a marketing agency does not want to BUY software, it wants something
# to SELL. Lumenia's reseller/white-label/multi-tenant work is the reason this
# call is worth making, so the pitch is "we build the AI products you resell",
# not "we'll build you a website".

DIGITAL_MARKETING_AGENCY = Campaign(
    campaign_id="dm-agency-white-label",
    prospect_label="the founder or head of growth at a digital marketing agency",
    prospect_world=(
        "  They run campaigns, SEO, paid ads and social for a book of clients. Their\n"
        "  margin is people: every new client means more hours from a team that is\n"
        "  already stretched. They spend evenings on client reporting nobody enjoys.\n"
        "  Their clients keep asking for 'AI' and they have no product to sell them.\n"
        "  Competitors are starting to bundle AI and win pitches on it. They cannot\n"
        "  hire a dev team to build one, and they do not want to become a software\n"
        "  company."
    ),
    reason_for_call=(
        "  Agencies like theirs are being asked for AI by their own clients and have\n"
        "  nothing to sell them. You build the AI products they can put their own name\n"
        "  on and resell — so they get the revenue without becoming a software shop."
    ),
    hypotheses=(
        "Most agency owners I speak to are getting asked for AI by their clients "
        "and have nothing to actually sell them. Is that landing anywhere near you?",
        "Usually the pinch is either client reporting eating your evenings, or "
        "lead qualification eating your team. Which one's worse for you?",
        "Most agencies your size can't take on more clients without hiring — is "
        "headcount the thing standing between you and the next ten accounts?",
    ),
    offer_map=(
        ("clients keep asking for AI and we have nothing to sell",
         "a white-label AI product under THEIR brand — the reseller platform work, "
         "multi-tier so their clients never see us"),
        ("we're drowning in client reporting",
         "an AI client dashboard that generates the reporting automatically"),
        ("lead qualification eats our team's time",
         "a WhatsApp or website chatbot that qualifies leads before a human touches them"),
        ("we can't scale without hiring",
         "agentic workflow automation that takes the repeatable work off the team"),
        ("we want recurring revenue, not project fees",
         "a multi-tenant SaaS platform they own and bill their clients for monthly"),
    ),
    proof_search="white label reseller platform and chatbot development for agencies",
    close_target=(
        "  A booked call with the team — a specific day, and a confirmed email address\n"
        "  you have read back to them. You are NOT closing a build on this call and you\n"
        "  must not try: nobody signs a development contract to a stranger on a cold\n"
        "  call, and pushing for it is exactly what makes a caller sound like a bot.\n"
        "  Book the meeting, then get off the phone. That is the win."
    ),
    energy=(
        "  Professional and genuinely energetic. You are pleased to be making this\n"
        "  call because you think it is actually relevant to them — not because you\n"
        "  are performing enthusiasm. Brisk, warm, a little direct. Think a good rep\n"
        "  who is busy and has something worth saying, not a telemarketer reading a\n"
        "  card.\n"
        "  Match their energy DOWNWARD, never upward: if they are guarded, get\n"
        "  quieter and slower, not louder. Pushing energy at a guarded person is the\n"
        "  single clearest tell of a script."
    ),
)

CAMPAIGNS: dict[str, Campaign] = {
    DIGITAL_MARKETING_AGENCY.campaign_id: DIGITAL_MARKETING_AGENCY,
}

DEFAULT_CAMPAIGN_ID = DIGITAL_MARKETING_AGENCY.campaign_id


def get_campaign(campaign_id: str = "") -> Campaign | None:
    """Look up a campaign. Returns None for the generic (uncampaigned) SDR."""
    if not campaign_id:
        return None
    return CAMPAIGNS.get(campaign_id)


def opening_line(campaign: Campaign, agent_name: str, company_name: str) -> str:
    """The literal instruction for the first thing the agent says.

    Kept here rather than in agent.py so the opener and the campaign it belongs to
    cannot drift apart.
    """
    return (
        f"Deliver the opener NOW, in one breath, professionally and with real energy.\n"
        f"  1. \"Hey, this is {agent_name} from {company_name}.\"\n"
        f"  2. Say plainly that you're reaching out cold — do not pretend otherwise.\n"
        f"  3. ONE sentence on why you called THEM specifically. Call "
        f"search_knowledge_base FIRST and use only what it returns:\n"
        f"     {campaign.reason_for_call.strip()}\n"
        f"  4. Ask for a specific slice of time and hand them the exit:\n"
        f"     \"Can I borrow ninety seconds to tell you why, and if it's not "
        f"relevant you can tell me to go away?\"\n"
        f"Under twelve seconds of speech. Do NOT list services. Do NOT ask how they "
        f"are. Then stop talking and let them respond."
    )
