"""
Nexus — Agent Session Orchestrator (LiveKit Agents 1.x)

Runs once per call. It:
1. Resolves the tenant (by dialed SIP number, or job metadata for outbound/web).
2. Picks the persona — inbound freight dispatcher, or outbound sales SDR — and
   builds the matching pipeline, agent graph, and tool set.
3. Configures the cascaded pipeline (STT → LLM(+fallback) → TTS) with semantic
   turn detection and preemptive generation for low-latency endpointing.
4. Creates the per-call state machine + tenant-scoped tool clients.
5. Wires observability hooks, per-turn latency telemetry, the human-whisper
   listener, call analytics, the live-call registry, call persistence, and
   (optionally) egress recording.
6. Starts the persona's first agent and prompts the opening line.
7. On shutdown, persists the final call record and releases resources.

Expensive, immutable resources (the VAD model, the embedding model, the per-tenant
knowledge indexes) are loaded once per worker process in `prewarm` and shared
across calls — loading them per call would charge every caller's first turn for
model initialisation.
"""

import asyncio
import json

import structlog
from livekit.agents import AgentSession, AutoSubscribe, JobContext, JobProcess

from config.settings import settings
from config.tenant import TenantRegistry, TenantConfig
from llm.factory import create_llm, warm_prompt_cache
from stt.deepgram_stt import create_stt
from tts.registry import SwitchableTTS, DISPATCH_DEFAULT_VOICE_ID, DEFAULT_VOICE_ID
from vad.silero_vad import create_vad
from state.machine import CallState, CallStateMachine
from state.agents import GreetingAgent
from state.sales_agents import SalesOpeningAgent
from tools.tms_tools import TMSTools
from tools.booking_tools import BookingTools
from tools.check_call_tools import CheckCallTools
from tools.detention_tools import DetentionTools
from tools.document_tools import DocumentTools
from tools.onboarding_tools import OnboardingTools
from tools.kb_tools import KnowledgeTools
from tools.call_reporter import CallReporter
from tools.human_intervention import HumanInterventionService
from pipeline.hooks import setup_hooks
from pipeline.analytics import CallAnalytics
from pipeline.telemetry import TurnTelemetry, TELEMETRY_TOPIC

logger = structlog.get_logger()

# Global tenant registry — loaded once at worker startup, shared across calls.
_tenant_registry: TenantRegistry | None = None

# Control messages the demo page sends over the data channel.
CONTROL_TOPIC = "nexus.control"


def get_tenant_registry() -> TenantRegistry:
    global _tenant_registry
    if _tenant_registry is None:
        _tenant_registry = TenantRegistry(config_path=settings.tenants_config_path)
    return _tenant_registry


# ── Worker prewarm ────────────────────────────────────────────────────────────

def prewarm(proc: JobProcess):
    """Load immutable, expensive resources once per worker process.

    Runs before any job is assigned, so the cost lands on worker startup instead
    of on a caller's first turn. Everything here must be safe to share across
    concurrent calls: the VAD and the knowledge indexes are read-only after load.

    Failures degrade rather than crash — a worker with no knowledge base can still
    take dispatch calls.
    """
    proc.userdata["vad"] = create_vad()
    logger.info("prewarm_vad_loaded")

    # Voice ids are account-scoped on both ElevenLabs and Cartesia, so the
    # catalog is discovered rather than hardcoded. Best-effort: a provider with
    # no key or a failed call just leaves its voices out of the picker.
    try:
        import asyncio

        from tts.registry import discover_cartesia_voices, discover_elevenlabs_voices

        async def _discover():
            for fn in (discover_elevenlabs_voices, discover_cartesia_voices):
                try:
                    await fn()
                except Exception as e:
                    logger.debug("voice discovery failed", fn=fn.__name__, error=str(e))

        asyncio.new_event_loop().run_until_complete(_discover())
    except Exception as e:
        logger.warning("prewarm_voice_discovery_failed", error=str(e))

    registry = get_tenant_registry()
    corpora = {t.knowledge_corpus for t in registry.list_tenants() if t.knowledge_corpus}
    if not corpora:
        logger.info("prewarm_no_knowledge_corpora")
        return

    from pathlib import Path
    from rag.embeddings import warm_encoder
    from rag.index import load_index

    if not warm_encoder():
        logger.warning("prewarm_embeddings_unavailable_retrieval_disabled")
        return

    corpus_root = Path(__file__).parent / "rag" / "corpus"
    # Vectors are read from here rather than recomputed. Built at image build
    # time (see Dockerfile) or by `python -m rag.ingest --build-cache`; a cache
    # miss falls back to embedding, which is correct but slow enough to risk the
    # process-init timeout.
    cache_dir = corpus_root / ".cache"

    for tenant in registry.list_tenants():
        if not tenant.knowledge_corpus:
            continue
        corpus_dir = corpus_root / tenant.knowledge_corpus
        if not corpus_dir.is_dir():
            logger.warning(
                "prewarm_corpus_missing",
                tenant_id=tenant.tenant_id,
                path=str(corpus_dir),
                hint="run: python -m rag.ingest --tenant <id> --dry-run",
            )
            continue
        try:
            index = load_index(tenant.tenant_id, corpus_dir=corpus_dir, cache_dir=cache_dir)
            logger.info("prewarm_index_loaded", tenant_id=tenant.tenant_id, chunks=len(index))
        except Exception as e:
            logger.exception("prewarm_index_failed", tenant_id=tenant.tenant_id, error=str(e))


# ── Tenant resolution ─────────────────────────────────────────────────────────

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
    """Resolve the tenant: explicit metadata (outbound/web) → SIP number → default."""
    registry = get_tenant_registry()

    meta_tenant = meta.get("tenant_id")
    if meta_tenant:
        t = registry.get_tenant(meta_tenant)
        if t:
            return t
        logger.warning("metadata tenant not found", tenant_id=meta_tenant)

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


# ── Pipeline construction ─────────────────────────────────────────────────────

def _build_llm(tenant: TenantConfig):
    """Primary LLM plus a different-vendor fallback. See llm/factory.py — it
    health-checks providers and enforces Gemini's minimum request deadline, both
    of which this function previously got wrong."""
    return create_llm(
        model=tenant.llm_model,
        temperature=tenant.llm_temperature,
        provider=tenant.llm_provider,
    )


def _build_turn_detection():
    """Semantic end-of-turn detection, preferring the hosted detector.

    This is the component that lets the VAD be trigger-happy: it reads the
    transcript and holds the turn open when the sentence is obviously unfinished,
    so a 250ms VAD silence window does not cut callers off mid-thought. If it is
    missing, the VAD tuning is actively harmful — hence the fallback chain, and
    hence the caller adjusting endpointing delays based on what it gets back.

    Order:
    1. `livekit.agents.inference.TurnDetector` — hosted, authenticates with the
       LiveKit credentials we already have, nothing to download, and it
       understands backchannels ("mhm", "right", "go on"), which on a sales call
       are constant and must NOT be treated as the prospect taking their turn.
    2. The local ONNX `EnglishModel` — deprecated in 1.6 and needs its model
       downloaded, but works offline. Kept as a real fallback.
    3. None → VAD endpointing, with the caller widening the delays to compensate.
    """
    try:
        from livekit.agents.inference import TurnDetector
        # Thresholds are left at the server's defaults deliberately. An earlier
        # backchannel_threshold=0.6 override drew an explicit warning from the
        # plugin: "the server provides calibrated defaults and overriding them may
        # be suboptimal". Backchannel handling ("mhm", "right") is already part of
        # the hosted model; it did not need our help.
        detector = TurnDetector()
        logger.info("turn_detection_ready", mode="hosted_semantic")
        return detector
    except Exception as e:
        logger.warning("hosted turn detector unavailable, trying local model", error=str(e))

    try:
        from livekit.plugins.turn_detector.english import EnglishModel
        detector = EnglishModel()
        logger.info("turn_detection_ready", mode="local_semantic")
        return detector
    except Exception as e:
        logger.warning(
            "no semantic turn detector; falling back to VAD endpointing with "
            "widened delays — expect the agent to feel less responsive",
            error=str(e),
        )
        return None


def _derive_outcome(sm: CallStateMachine) -> str:
    c = sm.context
    if c.meeting_booked:
        return "meeting_booked"
    if c.booking_confirmed:
        return "booked"
    if c.transferred_to_human:
        return "transferred"
    if c.call_mode == "outbound_sales":
        return "qualified" if c.lead_qualified else "not_interested"
    return "completed"


async def run_agent(ctx: JobContext):
    """Main per-call handler."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Agent connected to room", room_name=ctx.room.name)

    # ── Job metadata (outbound dispatch and the web demo pass config here) ──
    try:
        meta = json.loads(ctx.job.metadata) if ctx.job.metadata else {}
    except Exception:
        meta = {}
    direction = meta.get("direction", "inbound")

    # ── Tenant + persona ──
    tenant = await _resolve_tenant(ctx, meta)
    profile = meta.get("agent_profile") or tenant.agent_profile
    is_sales = profile == "sales"
    logger.info("persona selected", tenant_id=tenant.tenant_id, profile=profile, direction=direction)

    # ── Pipeline ──
    llm = _build_llm(tenant)
    stt = create_stt(
        extra_keywords=tenant.custom_keywords,
        profile="sales" if is_sales else "dispatch",
    )
    # The demo page may override the tenant's configured voice per session.
    tts = SwitchableTTS(
        meta.get("voice_id") or tenant.voice_model,
        fallback=DEFAULT_VOICE_ID if is_sales else DISPATCH_DEFAULT_VOICE_ID,
    )
    vad = ctx.proc.userdata.get("vad") or create_vad()
    turn_detection = _build_turn_detection()

    # ── Per-call state ──
    initial_state = CallState.SALES_OPENING if is_sales else CallState.GREETING
    state_machine = CallStateMachine(
        tenant_id=tenant.tenant_id,
        company_name=tenant.company_name,
        initial_state=initial_state,
    )
    state_machine.context.direction = direction
    state_machine.context.campaign_id = meta.get("campaign_id", "")
    call_id = state_machine.context.call_id
    caller_number = _extract_caller_number(ctx)

    # ── Shared infra ──
    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    analytics = CallAnalytics(state_machine, redis_client=redis_client)
    telemetry = TurnTelemetry(room=ctx.room, call_id=call_id)
    reporter = CallReporter(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)

    # ── Session ──
    session_kwargs = dict(llm=llm, stt=stt, tts=tts, vad=vad, userdata={})
    if turn_detection is not None:
        session_kwargs["turn_detection"] = turn_detection
        # With a semantic detector deciding when a turn is really over, the VAD
        # silence window can be short and these delays can be tight. The detector
        # extends the wait itself when the transcript looks unfinished.
        session_kwargs["min_endpointing_delay"] = 0.3
        session_kwargs["max_endpointing_delay"] = 3.0
    else:
        # No semantic detector: VAD alone decides the turn is over, and the VAD is
        # deliberately tuned to trigger on 250ms of silence. Pairing that with a
        # 0.3s delay would cut people off every time they paused for breath, so
        # buy the safety back here. Slower, but talking over the prospect is worse
        # than a beat of silence.
        session_kwargs["min_endpointing_delay"] = 0.8
        session_kwargs["max_endpointing_delay"] = 4.0
        logger.warning("endpointing_widened_no_semantic_turn_detector")
    # Start generating on interim transcripts rather than waiting for the turn to
    # be committed. Speculative work is discarded on barge-in, which costs tokens
    # but removes a serial dependency from the hot path.
    session_kwargs["preemptive_generation"] = True
    # The retuned VAD is deliberately sensitive, so a cough or a background voice
    # can trigger a false interruption. Rather than blunt the VAD, let the agent
    # resume where it left off when the "interruption" produced no transcript.
    session_kwargs["resume_false_interruption"] = True
    session_kwargs["false_interruption_timeout"] = 1.0
    session = AgentSession(**session_kwargs)

    # ── Tools ──
    session.userdata["state_machine"] = state_machine
    session.userdata["tenant_config"] = {
        **tenant.model_dump(),
        "agent_profile": profile,
    }
    session.userdata["room"] = ctx.room
    session.userdata["telemetry"] = telemetry

    if is_sales:
        session.userdata["kb_tools"] = KnowledgeTools(tenant_id=tenant.tenant_id)
    else:
        session.userdata["tms_tools"] = TMSTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
        session.userdata["booking_tools"] = BookingTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
        session.userdata["check_call_tools"] = CheckCallTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
        session.userdata["detention_tools"] = DetentionTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
        session.userdata["document_tools"] = DocumentTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)
        session.userdata["onboarding_tools"] = OnboardingTools(base_url=tenant.tms_api_url, tenant_id=tenant.tenant_id)

    # ── Observability + human-in-the-loop ──
    setup_hooks(
        session,
        state_machine,
        analytics=analytics,
        redis_client=redis_client,
        telemetry=telemetry,
    )
    intervention = HumanInterventionService(session, call_id)
    intervention.start()

    # ── Live voice switching (demo control channel) ──
    def _on_voice_switched(profile_switched):
        telemetry.publish({"type": "voice_changed", "voice": profile_switched.to_dict()})

    tts.on_switch(_on_voice_switched)

    @ctx.room.on("data_received")
    def _on_data(packet):
        if getattr(packet, "topic", "") != CONTROL_TOPIC:
            return
        try:
            message = json.loads(packet.data.decode())
        except Exception:
            return
        if message.get("type") == "switch_voice":
            try:
                # Takes effect on the next utterance; the in-flight one finishes
                # in the old voice rather than tearing mid-sentence.
                tts.switch(message.get("voice_id", ""))
            except Exception as e:
                logger.warning("voice switch failed", error=str(e))
                telemetry.publish({"type": "error", "message": f"voice switch failed: {e}"})

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
                "profile": profile,
            })
            await redis_client.expire(f"nexus:call:{call_id}", 3600)
        except Exception as e:
            logger.warning("registry write failed", error=str(e))

    # Bookkeeping only — Redis registry + the backend call record. Neither is
    # needed before the agent speaks, and awaiting them serially put a Redis
    # round-trip AND an HTTP POST between connect and the greeting. Fire them off
    # and let them land while the opener plays.
    _bg_tasks: set = set()

    def _spawn(coro, label: str):
        task = asyncio.create_task(coro)
        _bg_tasks.add(task)  # hold a reference so it is not GC'd mid-flight
        task.add_done_callback(_bg_tasks.discard)

        def _log_failure(t):
            if not t.cancelled() and t.exception():
                logger.warning("background_task_failed", task=label, error=str(t.exception())[:120])

        task.add_done_callback(_log_failure)
        return task

    _spawn(_register_call(), "register_call")
    _spawn(
        reporter.register(
            call_id,
            caller_number=caller_number,
            call_mode=state_machine.context.call_mode or ("outbound_sales" if is_sales else "load_booking"),
            direction=direction,
        ),
        "reporter_register",
    )

    # ── Shutdown: persist final record + clean up ──
    async def _on_shutdown(reason=None):
        c = state_machine.context
        try:
            report = analytics.build_report()
            latency = telemetry.summary() or report.get("latency_stats", {})
            await reporter.update(
                call_id,
                driver_name=c.driver_name or c.lead_name or None,
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

        closers = [reporter.close(), redis_client.aclose()]
        tms_tools = session.userdata.get("tms_tools")
        if tms_tools is not None:
            closers.append(tms_tools.close())
        for closer in closers:
            try:
                await closer
            except Exception:
                pass

        logger.info(
            "Call shutdown complete",
            call_id=call_id,
            reason=str(reason),
            outcome=_derive_outcome(state_machine),
            latency=latency if isinstance(latency, dict) else {},
        )

    ctx.add_shutdown_callback(_on_shutdown)

    # ── Start ──
    if is_sales:
        first_agent = SalesOpeningAgent(
            company_name=tenant.company_name,
            agent_name=tenant.agent_name,
            disclosure_mode=tenant.disclosure_mode,
            campaign_id=tenant.campaign_id,
        )
    else:
        first_agent = GreetingAgent(tenant_company=tenant.company_name)

    # Warm the LLM's prompt-prefix cache — but do NOT block on it. It is a full
    # LLM round trip (~1-2.5s), and awaiting it here sat that entire delay between
    # the caller connecting and hearing a word.
    #
    # Backgrounding is safe because the opener is a FIXED audio/text line, not an
    # LLM generation: the first real LLM call cannot happen until the prospect has
    # listened to ~10s of opener and replied, by which time this has long finished.
    _spawn(warm_prompt_cache(llm, first_agent.instructions), "warm_prompt_cache")

    await session.start(agent=first_agent, room=ctx.room)
    logger.info(
        "Agent session started",
        call_id=call_id,
        tenant_id=tenant.tenant_id,
        profile=profile,
        direction=direction,
        voice=tts.voice_id,
    )

    # Tell the demo page what it's connected to, so the HUD renders before the
    # first turn rather than sitting empty. The voice catalog ships from here
    # rather than from a backend endpoint so that tts/registry.py stays the single
    # source of truth — a copy in the backend would drift on the first new voice.
    from rag.index import get_index
    from tts.registry import list_voices

    kb_index = get_index(tenant.tenant_id)
    telemetry.publish({
        "type": "session_ready",
        "call_id": call_id,
        "tenant_id": tenant.tenant_id,
        "company_name": tenant.company_name,
        "agent_name": tenant.agent_name,
        "profile": profile,
        "voice": tts.profile.to_dict(),
        "voices": [v.to_dict() for v in list_voices()],
        "state": state_machine.current_state.value,
        "kb": {
            "loaded": kb_index is not None and not kb_index.is_empty,
            "chunks": len(kb_index) if kb_index else 0,
            "docs": len({c.doc_name for c in kb_index.chunks}) if kb_index else 0,
        },
        "pipeline": {
            "stt": "deepgram nova-3",
            "llm": tenant.llm_model,
            "tts": tts.profile.provider,
            "vad": "silero",
            "turn_detection": "semantic" if turn_detection is not None else "vad",
            "preemptive_generation": True,
        },
    })

    # The agent speaks first on inbound dispatch calls and on outbound sales
    # calls alike — in both cases the human is waiting for it to say something.
    if is_sales:
        from llm.campaigns import get_campaign, opening_line

        campaign = get_campaign(tenant.campaign_id)
        prospect = meta.get("prospect_name", "")
        greet = f" Greet them by name — they're called {prospect}." if prospect else ""

        # ── Fixed, pre-rendered opener ──
        # The opener is DETERMINISTIC AUDIO, not an LLM-generated turn. This fixes
        # two bugs at once:
        #   1. Consistency — the greeting says the exact same words every call,
        #      instead of the model improvising ("hi how are you") each time.
        #   2. No hedge — model-generated turns pass through the grounding verifier,
        #      and on the very first turn there are no grounded facts yet, so any
        #      factual-looking phrase got replaced with "let me pull that up, one
        #      moment". Supplying the audio to say() bypasses the verifier entirely,
        #      because the verifier only inspects text the model itself produces.
        # It renders on v3 (warm, emotional) and falls back to Flash (clean, fast)
        # — never to LLM improvisation. See tts/expressive_opener.py.
        spoke_fixed_opener = False
        if campaign and campaign.v3_opener and tts.profile.provider == "elevenlabs":
            try:
                from tts.expressive_opener import pcm_to_frames, prerender_opener, strip_tags

                opener_text = campaign.v3_opener.format(
                    agent=tenant.agent_name, company=tenant.company_name
                )
                rendered = await prerender_opener(
                    opener_text, tts.profile.voice, settings.elevenlabs_api_key
                )
                if rendered:
                    pcm, model_used = rendered
                    # The chat context gets the clean words (no [tags]) so the
                    # model's memory of what it "said" reads naturally.
                    await session.say(strip_tags(opener_text), audio=pcm_to_frames(pcm))
                    spoke_fixed_opener = True
                    telemetry.publish({"type": "expressive_opener", "model": model_used})
                    logger.info("fixed_opener_played", call_id=call_id, model=model_used)
            except Exception as e:
                logger.warning("fixed_opener_failed", error=str(e))

        if not spoke_fixed_opener:
            # The normal path for any non-ElevenLabs voice (e.g. the Deepgram
            # Orpheus default), and the safety net if a render failed. Speaks the
            # SAME fixed line deterministically — never an LLM improvisation, so
            # the greeting is identical every call.
            #
            # Its own words are seeded as grounded facts first: this line goes
            # through TTS and therefore through the verifier, and without that
            # seed the verifier would treat the company claim as unsourced and
            # replace the greeting with "let me pull that up, one moment".
            if campaign and campaign.v3_opener:
                from tts.expressive_opener import strip_tags
                fixed = strip_tags(campaign.v3_opener.format(
                    agent=tenant.agent_name, company=tenant.company_name))
                state_machine.add_turn_fact(fixed)
                # Logged BEFORE the await: say() resolves only once playout
                # finishes, so logging after it means the line never appears for
                # a call that is still speaking (or for a headless test with no
                # listener draining the track).
                logger.info("fixed_opener_speaking", call_id=call_id, voice=tts.voice_id)
                await session.say(fixed)
            else:
                session.generate_reply(instructions=(
                    f"Open the call. Say you're {tenant.agent_name} from {tenant.company_name}, "
                    "you're reaching out cold, give ONE reason you called, ask for a slice "
                    f"of time. Under ten seconds.{greet}"
                ))
    elif direction == "inbound":
        try:
            session.generate_reply(
                instructions="Greet the caller briefly and warmly by the company name, "
                             "and ask how you can help them today."
            )
        except Exception as e:
            logger.debug("initial greeting failed", error=str(e))
