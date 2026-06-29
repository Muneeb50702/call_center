from pydantic_settings import BaseSettings, SettingsConfigDict

class NexusSettings(BaseSettings):
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    deepgram_api_key: str
    groq_api_key: str
    tier1_model: str = "llama-3.1-8b-instant"
    tier2_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.0

    tms_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = NexusSettings()
