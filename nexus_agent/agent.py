"""
Nexus Dispatch — Agent Session Orchestrator

This is the core entrypoint for every incoming call.
Each call gets:
1. Tenant resolution (by dialed SIP number or default)
2. Tenant-specific STT/TTS/LLM configuration
3. A CallStateMachine for tracking call flow
4. TMSTools + BookingTools configured for the tenant's backend
5. The GreetingAgent as the starting agent (transitions happen via tools)

Scalability: This function runs once per call. LiveKit automatically
distributes calls across worker replicas. All state is per-session
(no shared mutable state between calls).
"""

import structlog
from livekit.agents import AgentSession, AutoSubscribe, JobContext

from config.settings import settings
from config.tenant import TenantRegistry, TenantConfig
from llm.google_client import create_google_llm
from stt.deepgram_stt import create_stt
from tts.deepgram_tts import create_tts
from vad.silero_vad import create_vad
from state.machine import CallStateMachine
from state.agents import GreetingAgent
from tools.tms_tools import TMSTools
from tools.booking_tools import BookingTools
from tools.check_call_tools import CheckCallTools
from tools.detention_tools import DetentionTools
from tools.document_tools import DocumentTools
from tools.onboarding_tools import OnboardingTools
from pipeline.hooks import setup_hooks

logger = structlog.get_logger()

# Global tenant registry — loaded once at worker startup, shared across calls
_tenant_registry: TenantRegistry | None = None


def get_tenant_registry() -> TenantRegistry:
    """Lazy-initialize the tenant registry."""
    global _tenant_registry
    if _tenant_registry is None:
        _tenant_registry = TenantRegistry(
            config_path=settings.tenants_config_path,
        )
    return _tenant_registry


def _extract_sip_number(ctx: JobContext) -> str:
    """
    Extract the dialed phone number from the SIP participant's attributes.
    LiveKit SIP bridge populates these automatically.
    Returns empty string for WebRTC (non-SIP) sessions.
    """
    try:
        for participant in ctx.room.remote_participants.values():
            attrs = participant.attributes
            # LiveKit SIP metadata keys
            dialed = attrs.get("sip.trunkPhoneNumber", "")
            if dialed:
                return dialed
            # Fallback to the called number
            called = attrs.get("sip.phoneNumber", "")
            if called:
                return called
    except Exception as e:
        logger.debug("Could not extract SIP number", error=str(e))
    return ""


async def _resolve_tenant(ctx: JobContext) -> TenantConfig:
    """
    Resolve which tenant owns this call.
    Priority: SIP number match → default tenant → hardcoded fallback.
    """
    registry = get_tenant_registry()
    sip_number = _extract_sip_number(ctx)

    if sip_number:
        tenant = await registry.resolve_tenant(sip_number)
        if tenant:
            logger.info(
                "Tenant resolved by SIP number",
                tenant_id=tenant.tenant_id,
                company=tenant.company_name,
                sip_number=sip_number,
            )
            return tenant

    # Fallback to default tenant
    default = registry.get_tenant(settings.default_tenant_id)
    if default:
        logger.info(
            "Using default tenant",
            tenant_id=default.tenant_id,
            company=default.company_name,
        )
        return default

    # Last resort fallback
    fallback = registry.get_default_tenant()
    if fallback:
        return fallback

    # Absolute fallback — should never reach here in production
    logger.warning("No tenant config found, using hardcoded defaults")
    return TenantConfig(
        tenant_id="default",
        company_name="Nexus Dispatch",
    )


async def run_agent(ctx: JobContext):
    """
    Main agent session handler — called once per incoming call.
    
    This function:
    1. Resolves the tenant from the SIP number
    2. Configures all plugins (STT/TTS/LLM/VAD) for the tenant
    3. Initializes the state machine and tools
    4. Starts the session with the GreetingAgent
    
    The call flow then progresses automatically through state transitions
    triggered by the LLM's tool calls.
    """
    # Connect to the LiveKit room (audio only — no video for voice calls)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Agent connected to room", room_name=ctx.room.name)

    # ── Step 1: Resolve tenant ──
    tenant = await _resolve_tenant(ctx)

    # ── Step 2: Configure plugins for this tenant ──
    llm = create_google_llm(
        model_name=tenant.llm_model,
        temperature=tenant.llm_temperature,
    )
    stt = create_stt(extra_keywords=tenant.custom_keywords)
    tts = create_tts(voice_model=tenant.voice_model)
    vad = create_vad()

    # ── Step 3: Initialize per-call state ──
    state_machine = CallStateMachine(
        tenant_id=tenant.tenant_id,
        company_name=tenant.company_name,
    )
    tms_tools = TMSTools(base_url=tenant.tms_api_url)
    booking_tools = BookingTools(base_url=tenant.tms_api_url)
    check_call_tools = CheckCallTools(base_url=tenant.tms_api_url)
    detention_tools = DetentionTools(base_url=tenant.tms_api_url)
    document_tools = DocumentTools(base_url=tenant.tms_api_url)
    onboarding_tools = OnboardingTools(base_url=tenant.tms_api_url)

    # ── Step 4: Create the starting agent ──
    greeting_agent = GreetingAgent(tenant_company=tenant.company_name)

    # ── Step 5: Build the session ──
    session = AgentSession(
        llm=llm,
        stt=stt,
        tts=tts,
        vad=vad,
        userdata={},
    )

    # Store shared context in session.userdata — accessible by all Agent subclasses
    session.userdata["state_machine"] = state_machine
    session.userdata["tms_tools"] = tms_tools
    session.userdata["booking_tools"] = booking_tools
    session.userdata["check_call_tools"] = check_call_tools
    session.userdata["detention_tools"] = detention_tools
    session.userdata["document_tools"] = document_tools
    session.userdata["onboarding_tools"] = onboarding_tools
    session.userdata["tenant_config"] = tenant.model_dump()
    session.userdata["room"] = ctx.room

    # ── Step 6: Wire observability hooks ──
    setup_hooks(session, state_machine)

    from tools.human_intervention import HumanInterventionService
    intervention_service = HumanInterventionService(session, state_machine.context.call_id)
    intervention_service.start()

    # ── Step 7: Start the session ──
    await session.start(room=ctx.room, agent=greeting_agent)

    logger.info(
        "Agent session started",
        call_id=state_machine.context.call_id,
        tenant_id=tenant.tenant_id,
        company=tenant.company_name,
    )

    # Clean up on exit
    intervention_service.stop()
