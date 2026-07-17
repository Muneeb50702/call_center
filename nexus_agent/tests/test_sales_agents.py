"""
Nexus — Sales persona tests

These exist because of a bug that reached a running container: every state prompt
passed `disclosure_mode` positionally to `get_sales_base_prompt`, where it was
keyword-only. Importing the modules did not catch it — the TypeError only fired
when an agent was actually constructed, which is the first thing that happens on
a real call and the last thing a smoke test does.

So: construct every agent, render every prompt. Cheap, and it covers the entire
class of "the persona explodes the moment someone calls".
"""

from __future__ import annotations

import pytest

from llm.sales_prompts import (
    get_closing_prompt,
    get_discovery_prompt,
    get_objection_prompt,
    get_pitch_prompt,
    get_sales_base_prompt,
    get_sales_opening_prompt,
    get_sales_wrap_up_prompt,
)
from state.machine import CallState, CallStateMachine
from state.sales_agents import (
    ClosingAgent,
    DiscoveryAgent,
    ObjectionAgent,
    PitchAgent,
    SalesOpeningAgent,
    SalesWrapUpAgent,
)

ALL_AGENTS = [
    SalesOpeningAgent,
    DiscoveryAgent,
    PitchAgent,
    ObjectionAgent,
    ClosingAgent,
    SalesWrapUpAgent,
]

ALL_PROMPTS = [
    get_sales_opening_prompt,
    get_discovery_prompt,
    get_pitch_prompt,
    get_objection_prompt,
    get_closing_prompt,
    get_sales_wrap_up_prompt,
]


# ── Construction ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("agent_cls", ALL_AGENTS, ids=lambda c: c.__name__)
def test_agent_constructs_with_full_persona(agent_cls):
    """The exact call agent.py makes on every inbound sales call."""
    agent = agent_cls(
        company_name="Lumenia",
        agent_name="Aria",
        disclosure_mode="if_asked",
    )
    assert agent.instructions
    assert "Lumenia" in agent.instructions
    assert "Aria" in agent.instructions


@pytest.mark.parametrize("agent_cls", ALL_AGENTS, ids=lambda c: c.__name__)
def test_agent_constructs_with_defaults(agent_cls):
    assert agent_cls().instructions


@pytest.mark.parametrize("prompt_fn", ALL_PROMPTS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("mode", ["if_asked", "upfront"])
def test_prompt_renders_positionally_and_by_keyword(prompt_fn, mode):
    """Both call styles must work — the original bug was that only one did."""
    positional = prompt_fn("Lumenia", "Aria", mode)
    keyword = prompt_fn(company_name="Lumenia", agent_name="Aria", disclosure_mode=mode)
    assert positional == keyword
    assert len(positional) > 400


# ── Prompt content ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt_fn", ALL_PROMPTS, ids=lambda f: f.__name__)
def test_every_state_shares_an_identical_cacheable_prefix(prompt_fn):
    """All states must share a byte-identical prefix or the LLM's prompt cache
    misses on every agent handoff, which shows up directly as TTFT."""
    base = get_sales_base_prompt("Lumenia", "Aria", "if_asked")
    assert prompt_fn("Lumenia", "Aria", "if_asked").startswith(base)


@pytest.mark.parametrize("prompt_fn", ALL_PROMPTS, ids=lambda f: f.__name__)
def test_grounding_rule_present_in_every_state(prompt_fn):
    """The agent must never be in a state where it thinks it may invent facts."""
    text = prompt_fn("Lumenia", "Aria", "if_asked")
    assert "search_knowledge_base" in text
    assert "NO_RESULTS" in text or "knowledge base" in text.lower()


def test_if_asked_mode_never_denies_being_an_ai():
    """The dispatch persona denies being an AI. For outbound cold calling that is
    a legal exposure, so this persona must answer honestly when asked."""
    text = get_sales_base_prompt("Lumenia", "Aria", "if_asked").lower()
    assert "never deny being an ai" in text
    assert "do not announce it unprompted" in text


def test_upfront_mode_discloses_in_the_opener():
    text = get_sales_base_prompt("Lumenia", "Aria", "upfront").lower()
    assert "opening line" in text


@pytest.mark.parametrize("prompt_fn", ALL_PROMPTS, ids=lambda f: f.__name__)
def test_prompts_forbid_written_formatting(prompt_fn):
    """Everything here is spoken aloud; markdown is read out as noise."""
    text = prompt_fn("Lumenia", "Aria", "if_asked")
    assert "markdown" in text.lower()


# ── FSM ───────────────────────────────────────────────────────────────────────

def test_sales_flow_starts_in_sales_opening_and_stamps_mode():
    fsm = CallStateMachine(
        tenant_id="lumenia", company_name="Lumenia", initial_state=CallState.SALES_OPENING
    )
    assert fsm.current_state == CallState.SALES_OPENING
    assert fsm.context.call_mode == "outbound_sales"


def test_dispatch_flow_is_unchanged_by_the_sales_addition():
    fsm = CallStateMachine(tenant_id="abc", company_name="ABC")
    assert fsm.current_state == CallState.GREETING
    assert fsm.context.call_mode == ""
    assert fsm.can_transition(CallState.QUALIFICATION)


def test_personas_cannot_cross_into_each_other():
    """A sales call must never be able to reach the freight dispatch graph."""
    sales = CallStateMachine(initial_state=CallState.SALES_OPENING)
    for dispatch_state in (
        CallState.QUALIFICATION,
        CallState.NEGOTIATION,
        CallState.BOOKING,
        CallState.CHECK_CALL,
        CallState.DETENTION,
    ):
        assert not sales.can_transition(dispatch_state)

    dispatch = CallStateMachine(initial_state=CallState.GREETING)
    for sales_state in (
        CallState.SALES_OPENING,
        CallState.DISCOVERY,
        CallState.PITCH,
        CallState.CLOSING,
    ):
        assert not dispatch.can_transition(sales_state)


def test_every_sales_state_can_reach_wrap_up():
    """Any call can end at any moment — a state that cannot hang up is a trap."""
    for state in (
        CallState.SALES_OPENING,
        CallState.DISCOVERY,
        CallState.PITCH,
        CallState.OBJECTION,
        CallState.CLOSING,
    ):
        assert CallStateMachine(initial_state=state).can_transition(CallState.WRAP_UP)


def test_discovery_pitch_objection_loop_freely():
    """A prospect drives the order, not the funnel."""
    fsm = CallStateMachine(initial_state=CallState.SALES_OPENING)
    for target in (
        CallState.DISCOVERY,
        CallState.PITCH,
        CallState.OBJECTION,
        CallState.PITCH,
        CallState.DISCOVERY,
        CallState.CLOSING,
        CallState.OBJECTION,
        CallState.CLOSING,
        CallState.WRAP_UP,
    ):
        assert fsm.transition(target), f"blocked transition to {target.value}"
