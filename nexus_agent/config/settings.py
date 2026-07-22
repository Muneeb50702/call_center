from pydantic_settings import BaseSettings, SettingsConfigDict


class NexusSettings(BaseSettings):
    # LiveKit connection
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    # API keys
    deepgram_api_key: str
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    cartesia_api_key: str = ""
    elevenlabs_api_key: str = ""

    # ── LLM provider ──
    # Which provider serves the primary LLM: "openai" | "gemini" | "groq".
    #
    # Default is openai (gpt-4o-mini), and the reason is rate limits, not model
    # quality. Measured against this agent's ~3,000-token-per-turn prompt:
    #
    #   Gemini free tier   5 turns/min   (hard 5 RPM cap, verified via a live 429)
    #   Groq free tier    ~4 turns/min   (12,000 TPM ÷ ~3k tokens per turn)
    #   OpenAI 4o-mini    ~67 turns/min  (500 RPM / 200k TPM)
    #
    # A real sales conversation is 15-30 turns over a few minutes, so both free
    # tiers run dry mid-call — which is exactly the "transcribes but stops
    # answering" failure this system already hit once.
    #
    # Gemini 2.5 Flash is the better model for persona nuance and gets implicit
    # prompt caching; make it primary if the key is on a PAID tier. On free, it
    # cannot survive a demo.
    #
    # Every other reachable vendor is chained as a fallback automatically (see
    # llm/factory.py). The wrapper costs nothing on the happy path — measured at
    # 225.1ms bare vs 214.8ms wrapped, i.e. within noise.
    llm_provider: str = "openai"

    # ── Per-provider models ──
    # One setting per provider, because a model name is only valid for the vendor
    # it belongs to. The legacy TIER1_MODEL / TIER2_MODEL names are
    # provider-agnostic but their VALUES are not, and real .env files in this
    # project carry TIER1_MODEL=llama-3.1-8b-instant — a Groq model. Wiring that
    # into the Gemini client (as "tier 1 = primary = Gemini" invites) sends Google
    # a Llama model name and fails the call. Never resolve a provider's model
    # through a tier alias.
    gemini_model: str = "gemini-2.5-flash"
    openai_model: str = "gpt-4o-mini"
    groq_model: str = "llama-3.3-70b-versatile"

    # Legacy aliases, still read from existing .env files. tier1 is NOT a synonym
    # for "the Gemini model" — it predates this being multi-provider and holds a
    # Groq model in practice. Kept only so old configs keep booting.
    tier1_model: str = "llama-3.1-8b-instant"
    tier2_model: str = "llama-3.3-70b-versatile"

    groq_temperature: float = 0.0

    # Per-attempt LLM timeout used by the fallback adapter. MUST stay >= 10.0:
    # Gemini rejects any deadline under 10s with a non-retryable 400, and
    # LiveKit's FallbackAdapter defaults to 5.0 — which silently broke every
    # Gemini call until we caught it. This is a ceiling, not a wait: a healthy
    # LLM answering in 300ms is unaffected.
    llm_attempt_timeout: float = 12.0

    # TMS backend (default, overridden per tenant)
    tms_base_url: str = "http://tms-backend:8000"

    # Multi-tenant configuration
    tenants_config_path: str = "config/tenants.json"
    default_tenant_id: str = "abc-logistics"

    # Redis for shared state across workers
    redis_url: str = "redis://redis:6379/0"

    # Service-to-service auth: the agent authenticates to the TMS backend with
    # this shared key (sent as X-Service-Key). Must match the backend's value.
    nexus_service_key: str = ""

    # SIP / Telephony (Telnyx)
    telnyx_api_key: str = ""
    telnyx_sip_uri: str = ""

    # Outbound SIP trunk id on LiveKit (Phase 1 outbound dialing). Optional.
    livekit_sip_outbound_trunk_id: str = ""

    # Call recording (LiveKit Egress). When enabled, each call is recorded and
    # the resulting path is stored on the call record.
    recording_enabled: bool = False
    recording_output_dir: str = "recordings"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = NexusSettings()
