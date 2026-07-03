from pydantic_settings import BaseSettings, SettingsConfigDict


class NexusSettings(BaseSettings):
    # LiveKit connection
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    # API keys
    deepgram_api_key: str
    groq_api_key: str
    gemini_api_key: str = ""

    # LLM tiers
    tier1_model: str = "llama-3.1-8b-instant"
    tier2_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.0

    # TMS backend (default, overridden per tenant)
    tms_base_url: str = "http://tms-backend:8000"

    # Multi-tenant configuration
    tenants_config_path: str = "config/tenants.json"
    default_tenant_id: str = "abc-logistics"

    # Redis for shared state across workers
    redis_url: str = "redis://redis:6379/0"

    # SIP / Telephony (Telnyx)
    telnyx_api_key: str = ""
    telnyx_sip_uri: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = NexusSettings()
