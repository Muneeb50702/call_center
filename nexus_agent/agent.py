"""
Nexus Dispatch — Agent Session Orchestrator (LiveKit Agents 1.x)

Runs once per call. It:
1. Resolves the tenant (by dialed SIP number, or job metadata for outbound).
2. Configures the cascaded pipeline (STT → LLM(+fallback) → TTS) with semantic
   turn detection for low-latency endpointing.
3. Creates the per-call state machine + tenant-scoped tool clients.
4. Wires observability hooks, the human-whisper listener, call analytics, the
   live-call registry (for the dashboard), call persistence, and (optionally)
   egress recording.
5. Starts the GreetingAgent and, on inbound, prompts the opening greeting.
6. On shutdown, persists the final call record and releases resources.
"""

import json

import structlog
from livekit.agents import AgentSession, AutoSubscribe, JobContext, get_job_context
from livekit.agents.llm import FallbackAdapter as LLMFallbackAdapter

from config.settings import settings
from config.tenant import TenantRegistry, TenantConfig
from llm.google_client import create_google_llm
from llm.groq_client import create_groq_llm
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
from tools.call_reporter import CallReporter
from tools.human_intervention import HumanInterventionService
from pipeline.hooks import setup_hooks
from pipeline.analytics import CallAnalytics

logger = structlog.get_logger()

# Global tenant registry — loaded once at worker startup, shared across calls.
_tenant_registry: TenantRegistry | None = None


def get_tenant_registry() -> TenantRegistry:
    global _tenant_registry
    if _tenant_registry is None:
        _tenant_registry = TenantRegistry(config_path=settings.tenants_config_path)
    return _tenant_registry


def _extract_sip_number(ctx: JobContext) -> str:
    """The dialed (tenant) phone number, from SIP participant attributes."""
    try:
        for participant in ctx.room.remote_participants.values():
            attrs = participant.attributes
            dialed = attrs.get("sip.trunkPhoneNumber", "")
            if dialed:
                return dialed
            called = attrs.get("sip.phoneNumber", "")
            if called:
                return called
    except Exception as e:
        logger.debug("Could not extract SIP number", error=str(e))
    return ""


def _extract_caller_number(ctx: JobContext) -> str:
    """Best-effort caller (from) number."""
    try:
        for participant in ctx.room.remote_participants.values():
            attrs = participant.attributes
            n = attrs.get("sip.phoneNumber", "") or attrs.get("sip.from", "")
            if n:
                return n
    except Exception:
        pass
    return ""


async def _resolve_tenant(ctx: JobContext, meta: dict) -> TenantConfig:
    """Resolve the tenant: explicit metadata (outbound) → SIP number → default."""
    registry = get_tenant_registry()

    meta_tenant = meta.get("tenant_id")
    if meta_tenant:
        t = registry.get_tenant(meta_tenant)
        if t:
            return t

    sip_number = _extract_sip_number(ctx)
    if sip_number:
        tenant = await registry.resolve_tenant(sip_number)
        if tenant:
            logger.info("Tenant resolved by SIP number", tenant_id=tenant.tenant_id, sip_number=sip_number)
            return tenant

    default = registry.get_tenant(settings.default_tenant_id) or registry.get_default_tenant()
    if default:
        return default

    logger.warning("No tenant config found, using hardcoded defaults")
    return TenantConfig(tenant_id="default", company_name="Nexus Dispatch")


def _build_llm(tenant: TenantConfig):
    """Primary Gemini LLM with a Groq/Llama fallback (if configured)."""
    primary = create_google_llm(model_name=tenant.llm_model, temperature=tenant.llm_temperature)
    if settings.groq_api_key:
        try:
            fallback = create_groq_llm(model_name=settings.tier2_model, temperature=tenant.llm_temperature)
            return LLMFallbackAdapter([primary, fallback])
        except Exception as e:
            logger.warning("Groq fallback unavailable, using Gemini only", error=str(e))
    return primary


def _build_turn_detection():
    """Semantic end-of-turn detector (CPU). Falls back to VAD endpointing."""
    try:
        from livekit.plugins.turn_detector.english import EnglishModel
        return EnglishModel()
    except Exception as e:
        logger.warning("Turn detector unavailable, using VAD endpointing", error=str(e))
        return None


def _derive_outcome(sm: CallStateMachine) -> str:
    c = sm.context
    if c.booking_confirmed:
        return "booked"
    if c.transferred_to_human:
        return "transferred"
    return "completed"


async def run_agent(ctx: JobContext):
    """Main per-call handler."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Agent connected to room", room_name=ctx.room.name)

    # ── Job metadata (outbound dispatch passes direction/campaign/tenant here) ──
    try:
        meta = json.loads(ctx.job.metadata) if ctx.job.metadata else {}
    except Exception:
        meta = {}
    direction = meta.get("direction", "inbound")

    # ── Tenant + pipeline ──
    tenant = await _resolve_tenant(ctx, meta)
    llm = _build_llm(tenant)
    stt = create_stt(extra_keywords=tenant.custom_keywords)
    tts = create_tts(voice_model=tenant.voice_model)
    vad = create_vad()
    turn_detection = _build_turn_detection()

    # ── Per-call state ──
    state_machine = CallStateMachine(tenant_id=tenant.tenant_id, company_name=tenant.company_name)
    state_machine.context.direction = direction
    state_machine.context.campaign_id = meta.get("campaign_id", "")
    call_id = state_machine.context.call_id
    caller_number = _extract_caller_number(ctx)

    tms_tools = TMSTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
    booking_tools = BookingTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
    check_call_tools = CheckCallTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
    detention_tools = DetentionTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
    document_tools = DocumentTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
    onboarding_tools = OnboardingTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)

    # ── Shared infra ──
    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    analytics = CallAnalytics(state_machine, redis_client=redis_client)
    reporter = CallReporter(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)

    # ── Session ──
    session_kwargs = dict(llm=llm, stt=stt, tts=tts, vad=vad, userdata={})
    if turn_detection is not None:
        session_kwargs["turn_detection"] = turn_detection
        session_kwargs["min_endpointing_delay"] = 0.4
        session_kwargs["max_endpointing_delay"] = 3.0
    session = AgentSession(**session_kwargs)

    session.userdata["state_machine"] = state_machine
    session.userdata["tms_tools"] = tms_tools
    session.userdata["booking_tools"] = booking_tools
    session.userdata["check_call_tools"] = check_call_tools
    session.userdata["detention_tools"] = detention_tools
    session.userdata["document_tools"] = document_tools
    session.userdata["onboarding_tools"] = onboarding_tools
    session.userdata["tenant_config"] = tenant.model_dump()
    session.userdata["room"] = ctx.room

    # ── Observability + human-in-the-loop ──
    setup_hooks(session, state_machine, analytics=analytics, redis_client=redis_client)
    intervention = HumanInterventionService(session, call_id)
    intervention.start()

    # ── Optional egress recording ──
    recording_path = ""
    if settings.recording_enabled:
        try:
            from livekit import api
            recording_path = f"{settings.recording_output_dir}/{ctx.room.name}-{call_id}.ogg"
            await ctx.api.egress.start_room_composite_egress(
                api.RoomCompositeEgressRequest(
                    room_name=ctx.room.name,
                    audio_only=True,
                    file_outputs=[api.EncodedFileOutput(
                        file_type=api.EncodedFileType.OGG, filepath=recording_path)],
                )
            )
            logger.info("Egress recording started", path=recording_path)
        except Exception as e:
            logger.warning("Egress start failed (needs egress infra / S3)", error=str(e))
            recording_path = ""

    # ── Live-call registry (feeds the dashboard snapshot) + persistence ──
    async def _register_call():
        try:
            await redis_client.sadd(f"nexus:active_calls:{tenant.tenant_id}", call_id)
            await redis_client.hset(f"nexus:call:{call_id}", mapping={
                "call_id": call_id,
                "tenant_id": tenant.tenant_id,
                "caller_number": caller_number,
                "driver_name": "",
                "driver_mc": "",
                "current_state": state_machine.current_state.value,
                "started_at": str(int(state_machine.context.call_start_time)),
                "direction": direction,
            })
            await redis_client.expire(f"nexus:call:{call_id}", 3600)
        except Exception as e:
            logger.warning("registry write failed", error=str(e))

    await _register_call()
    await reporter.register(call_id, caller_number=caller_number,
                            call_mode=state_machine.context.call_mode or "load_booking",
                            direction=direction)

    # ── Shutdown: persist final record + clean up ──
    async def _on_shutdown(reason=None):
        c = state_machine.context
        try:
            report = analytics.build_report()
            latency = report.get("latency_stats", {})
            await reporter.update(
                call_id,
                driver_name=c.driver_name or None,
                driver_mc=c.driver_mc_number or None,
                call_mode=c.call_mode or None,
                duration_seconds=state_machine.get_call_duration(),
                outcome=_derive_outcome(state_machine),
                states_visited=c.states_visited,
                tools_invoked=c.tools_invoked,
                booking_id=c.booking_id or None,
                agreed_rate=c.agreed_rate or None,
                negotiation_rounds=c.negotiation_rounds,
                transferred_to_human=c.transferred_to_human,
                transfer_reason=c.transfer_reason or None,
                recording_path=recording_path or None,
                direction=c.direction,
                transcript=c.transcript,
                sentiment=c.sentiment,
                exception_peak=c.exception_score,
                avg_latency_ms=latency.get("avg_ms"),
                p95_latency_ms=latency.get("p95_ms"),
            )
        except Exception as e:
            logger.warning("final call update failed", error=str(e))
        try:
            await analytics.flush_to_redis()
        except Exception:
            pass
        try:
            await redis_client.srem(f"nexus:active_calls:{tenant.tenant_id}", call_id)
            await redis_client.delete(f"nexus:call:{call_id}")
        except Exception:
            pass
        intervention.stop()
        for closer in (reporter.close(), tms_tools.close(), redis_client.aclose()):
            try:
                await closer
            except Exception:
                pass
        logger.info("Call shutdown complete", call_id=call_id, reason=str(reason))

    ctx.add_shutdown_callback(_on_shutdown)

    # ── Start ──
    greeting_agent = GreetingAgent(tenant_company=tenant.company_name)
    await session.start(agent=greeting_agent, room=ctx.room)
    logger.info("Agent session started", call_id=call_id, tenant_id=tenant.tenant_id, direction=direction)

    # On inbound calls, greet first. (Outbound greeting/disclosure is Phase 1.)
    if direction == "inbound":
        try:
            session.generate_reply(
                instructions="Greet the caller briefly and warmly by the company name, "
                              "and ask how you can help them today."
            )
        except Exception as e:
            logger.debug("initial greeting failed", error=str(e))
