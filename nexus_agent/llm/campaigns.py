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
    # Facts the agent may state WITHOUT calling search_knowledge_base, because
    # each was verified against the corpus when this campaign was written.
    #
    # These exist to stop the agent narrating a lookup ("let me pull that up")
    # during its own pitch. A real rep knows their own case studies cold; making
    # the agent search before it can say what it built is what made it sound
    # junior. Anything NOT listed here still requires a tool call, so the
    # grounding guarantee is unchanged — the set is just pre-verified rather than
    # verified live. They are also loaded into the FSM's standing_facts so the
    # pre-TTS verifier treats them as grounded.
    preloaded_facts: tuple[str, ...] = field(default_factory=tuple)
    # The literal opening line, with ElevenLabs v3 Audio Tags. Pre-rendered on v3
    # for a full-emotion first impression (tts/expressive_opener.py), then handoff
    # to streaming Flash for the rest of the call. Fixed text — states no company
    # fact that needs retrieval. {agent} and {company} are filled at render time.
    v3_opener: str = ""

    def prompt_block(self) -> str:
        """Render the campaign as a prompt section."""
        hyp = "\n".join(f'  - "{h}"' for h in self.hypotheses)
        offers = "\n".join(f"  - If they say: {pain}\n      → You offer: {cap}"
                           for pain, cap in self.offer_map)
        preloaded = ""
        if self.preloaded_facts:
            facts = "\n".join(f"  - {f}" for f in self.preloaded_facts)
            preloaded = f"""
WHAT YOU ALREADY KNOW — SAY IT, DO NOT LOOK IT UP:
These are verified and yours to state the moment they are relevant. You do NOT
need a tool call for any of them:
{facts}

You are a rep who knows their own work cold. NEVER narrate a lookup — no "let me
pull that up", "one moment", "let me check", "bear with me", "give me a second".
A cold caller who has to go and check what their own company built has already
lost the call. If a question needs the knowledge base, call it SILENTLY and
answer when it returns — the caller should never hear that a tool exists.
"""

        return f"""--- WHO YOU ARE CALLING (this call, specifically) ---
You are calling {self.prospect_label}.

THEIR WORLD — you already understand this, so do not ask them to explain it:
{self.prospect_world}
{preloaded}

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
    # The FIXED opening line. Rendered to audio up front (v3 for warmth, Flash if
    # v3 is down) and played as the first utterance, so it is identical every call
    # and never routes through the grounding verifier — that is what stops the
    # "let me pull that up" hedge from ever landing on the greeting.
    #
    # ONE emotion tag, at the very start, on purpose. Multiple tags mid-line make
    # v3 lurch between registers ("cheerful... then warm... then deep") which
    # reads as erratic. A single opening [warmly] sets one consistent tone and
    # lets the words carry the rest. Flash ignores the tag (it is stripped).
    #
    # Structure: who I am → own the cold call → the hook question → the ask.
    # Kept tight — v3 speaks slowly, so this measures ~9-10s. Do not lengthen
    # without re-checking the duration; a 19s opener (an earlier draft) is a
    # Write "AI", never "A.I." — Deepgram Aura-2 reads the periods aloud, so the
    # opener came out as "A dot I dot products", which instantly sounds synthetic.
    # Plain "AI" is voiced correctly as the two letters.
    v3_opener=(
        "[warmly] Hey — I'm {agent}, calling from {company}. "
        "I'll be straight with you, this is a cold call. "
        "We build the AI products marketing agencies sell to their own clients — "
        "the thing your clients keep asking you for. "
        "Give me thirty seconds and you can decide if it's worth more?"
    ),
)

# ── Logistics operator ───────────────────────────────────────────────────────
#
# Chosen for the demo because it is the best-EVIDENCED pitch in the corpus, and
# on a sales call evidence is what separates a pitch from a claim. Everything
# below traces to 15-project-saas-trucking-dispatch.md:
#   multi-tenant logistics SaaS for Canadian trucking  → project overview
#   carrier + order management, multi-stop routing     → "what Lumenia built"
#   QuickBooks integration, automated invoicing        → named testimonial
#   full-stack engineering as the role                 → project overview
#
# NOTE ON WHAT IT MUST NOT SELL: there is no AI-voice-agent capability anywhere
# in the corpus — the chatbot page states plainly that it publishes no case
# studies, and no page documents voice or telephony work. So this agent must
# never pitch "we build AI phone agents", however tempting that is while one is
# demonstrably talking to you. The pre-TTS verifier would redact it and the
# agent would audibly hedge, which is worse than not saying it. Conversational
# work is grounded ONLY as the AI Agentic Automation / AI Development service
# lines, and it is framed that way below.
LOGISTICS_OPERATOR = Campaign(
    campaign_id="logistics-dispatch-automation",
    prospect_label="the owner or operations lead at a small trucking or logistics company",
    prospect_world=(
        "  They move freight with a fleet they can count. Dispatch runs on phone\n"
        "  calls, a whiteboard and somebody's spreadsheet. The same person who\n"
        "  books loads also chases paperwork, and invoicing happens at night or on\n"
        "  a Sunday because that is the only quiet hour. They have looked at the big\n"
        "  TMS platforms and found them priced for fleets ten times their size and\n"
        "  full of modules they will never open. Nothing they use talks to anything\n"
        "  else, so the same load gets typed in three times."
    ),
    reason_for_call=(
        "  You have already built exactly this for a Canadian trucking operator — a\n"
        "  multi-tenant dispatch platform with carrier and order management,\n"
        "  multi-stop route coordination, and QuickBooks wired in so invoicing stops\n"
        "  being a manual night job. You are calling operators who are still doing\n"
        "  that by hand."
    ),
    hypotheses=(
        "Most operators your size tell me invoicing is the thing that eats their "
        "evenings — the driving pays, the paperwork just costs. Is that about right "
        "for you?",
        "Usually it's one of two things: either dispatch lives in someone's head and "
        "a spreadsheet, or the accounting side never matches what actually moved. "
        "Which one bites you more?",
        "Most people I call have looked at the big TMS platforms and walked away "
        "because they're priced for a fleet ten times the size. Has that been your "
        "experience too?",
    ),
    offer_map=(
        ("invoicing is manual and eats evenings",
         "the QuickBooks integration from the trucking platform — the operator we "
         "built it for says their invoicing is fully automated now"),
        ("dispatch lives in a spreadsheet and someone's head",
         "the dispatch system itself: carrier and order management, with dispatchers "
         "building multi-stop trip sequences instead of holding routes in memory"),
        ("the big TMS platforms are too expensive and too heavy",
         "a platform built for their operation specifically — the trucking system was "
         "custom full-stack work, not a seat licence for software built for someone else"),
        ("our systems don't talk to each other",
         "systems integration work — the trucking build connected dispatch and "
         "accounting so a load is entered once"),
        ("we want to grow without hiring more back office",
         "AI agentic automation on the repeatable admin, so headcount tracks trucks "
         "rather than paperwork"),
    ),
    # Every line traced to 15-project-saas-trucking-dispatch.md before being put
    # here. Phrasing stays close to the corpus wording so the agent cannot drift
    # into a stronger claim than the source supports — note "a Canadian trucking
    # enterprise", never a named client, because the corpus names none.
    preloaded_facts=(
        "Lumenia built a multi-tenant SaaS trucking management and dispatch "
        "platform for Canadian trucking enterprises. Lumenia's role was "
        "full-stack engineering.",
        "That platform does carrier management and order management, and lets "
        "dispatchers build complex trip sequences and coordinate multi-stop routes.",
        "It integrates QuickBooks. A logistics founder Lumenia worked with is "
        "quoted saying: Lumenia rebuilt our dispatch system from scratch and "
        "integrated QuickBooks flawlessly, our invoicing is fully automated now.",
        "Lumenia's published logistics work also includes Ezanias TMS, a "
        "peer-to-peer rideshare platform, and My Moving Journey.",
        "Lumenia's other service lines include AI agentic automation, AI "
        "development and integration, multi-tenant SaaS development, and "
        "chatbot and conversational work.",
    ),
    proof_search="trucking dispatch platform QuickBooks integration multi-stop routing",
    close_target=(
        "  A booked call with the team — a specific day, and an email address you have\n"
        "  read back to them. You are NOT closing a build on this call and must not\n"
        "  try. Nobody signs a development contract to a stranger on a cold call, and\n"
        "  pushing for it is the exact moment a caller starts sounding like a bot.\n"
        "  Book the meeting, then get off the phone."
    ),
    energy=(
        "  Grounded and unhurried. These are practical people who are busy and have\n"
        "  been called by a lot of software salesmen — the way to lose them is to\n"
        "  sound polished. Be plain, be concrete, use their vocabulary (loads, lanes,\n"
        "  deadhead, invoicing), and never oversell. One real detail about what you\n"
        "  built beats three adjectives about how good it is.\n"
        "  Match their energy DOWNWARD, never upward: if they are short with you, get\n"
        "  quieter and more direct, not brighter. Pushing energy at a guarded person\n"
        "  is the single clearest tell of a script."
    ),
    # Emotion markers here are Fish S2 / ElevenLabs v3 syntax and are STRIPPED
    # automatically on engines that would pronounce them (state/agents.py), so
    # this one line is safe on every voice in the catalog.
    #
    # Three markers, each doing a specific job, and none of them decoration:
    #   [warmly]        sets one consistent register for the whole opener
    #   [break]         a real beat after admitting the cold call — the pause is
    #                   what makes the admission read as candour rather than a
    #                   scripted line delivered at speed
    #   [slightly amused] on the exit offer, so "tell me to get lost" lands as
    #                   self-aware rather than as pleading
    # MEASURED, not estimated: this renders at 12.2s on Fish. The first draft was
    # a sentence longer and measured 17.5s, which is well into the range this
    # file already flags as a failed opener — a cold call is lost in the first
    # fifteen seconds, and [break] spends real time on top of the words. If you
    # edit this line, re-synthesize it and check the duration before shipping.
    v3_opener=(
        "[warmly] Hey — I'm {agent} from {company}. "
        "Straight up, this is a cold call. [break] "
        "We built the dispatch and invoicing system for a Canadian trucking outfit. "
        "[slightly amused] Thirty seconds, then you can tell me to get lost?"
    ),
)

CAMPAIGNS: dict[str, Campaign] = {
    DIGITAL_MARKETING_AGENCY.campaign_id: DIGITAL_MARKETING_AGENCY,
    LOGISTICS_OPERATOR.campaign_id: LOGISTICS_OPERATOR,
}

DEFAULT_CAMPAIGN_ID = LOGISTICS_OPERATOR.campaign_id


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
        # NO tool call here, deliberately. Instructing a search before the
        # greeting is what produced "let me pull that up, one moment" ahead of
        # "hi, this is Sarah" — the model narrated the lookup it had been told to
        # perform. The reason for calling is campaign text, already verified
        # against the corpus, so it needs no retrieval.
        f"  3. ONE sentence on why you called THEM specifically. You already know "
        f"this — say it, do not look anything up:\n"
        f"     {campaign.reason_for_call.strip()}\n"
        f"  4. Ask for a specific slice of time and hand them the exit:\n"
        f"     \"Can I borrow ninety seconds to tell you why, and if it's not "
        f"relevant you can tell me to go away?\"\n"
        f"Under twelve seconds of speech. Do NOT list services. Do NOT ask how they "
        f"are. Then stop talking and let them respond."
    )
