"""
Nexus Dispatch — Multi-Tenant Configuration

Each Pakistani BPO/dispatch company that subscribes gets a tenant config.
The system resolves which tenant a call belongs to by matching the dialed
SIP phone number to a tenant's registered numbers.

Storage: Redis (primary) with JSON file fallback for local development.
"""

import json
import os
from typing import Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class TenantConfig(BaseModel):
    """Configuration for a single tenant (dispatch company)."""

    # Identity
    tenant_id: str = Field(..., description="Unique identifier for the tenant")
    company_name: str = Field(..., description="Display name of the dispatch company")
    greeting_script: str = Field(
        default="",
        description="Custom greeting script override. If empty, uses default.",
    )

    # Telephony
    sip_numbers: list[str] = Field(
        default_factory=list,
        description="Phone numbers registered to this tenant (E.164 format)",
    )
    human_transfer_number: str = Field(
        default="",
        description="Phone number for warm-transferring to a human dispatcher",
    )

    # TMS Integration
    tms_api_url: str = Field(
        default="http://tms-backend:8000",
        description="Base URL of the tenant's TMS backend API",
    )
    tms_api_key: str = Field(
        default="",
        description="API key for authenticating with the tenant's TMS",
    )

    # Voice & STT Customization
    voice_model: str = Field(
        default="aura-orion-en",
        description="Deepgram TTS voice model (e.g., 'aura-orion-en', 'aura-asteria-en')",
    )
    custom_keywords: list[str] = Field(
        default_factory=list,
        description="Additional STT keywords specific to this tenant's operations",
    )

    # Business Rules
    negotiation_floor_pct: float = Field(
        default=0.90,
        description="Minimum acceptable rate as a percentage of base rate (0.90 = 90%)",
    )
    max_negotiation_rounds: int = Field(
        default=3,
        description="Maximum negotiation rounds before suggesting human transfer",
    )
    max_concurrent_calls: int = Field(
        default=20,
        description="Max simultaneous calls for this tenant",
    )

    # LLM Configuration
    llm_model: str = Field(
        default="llama-3.1-8b-instant",
        description="Groq model to use for this tenant",
    )
    llm_temperature: float = Field(
        default=0.0,
        description="LLM temperature for this tenant",
    )


class TenantRegistry:
    """
    Manages tenant configurations.
    
    Resolution priority:
    1. Redis (production, shared across workers)
    2. JSON file (local development fallback)
    """

    def __init__(self, config_path: str = "config/tenants.json", redis_client=None):
        self._tenants: dict[str, TenantConfig] = {}
        self._number_to_tenant: dict[str, str] = {}
        self._redis = redis_client
        self._config_path = config_path

        # Load from JSON file on startup
        self._load_from_file()

    def _load_from_file(self):
        """Load tenant configs from JSON file."""
        if not os.path.exists(self._config_path):
            logger.warning("Tenant config file not found", path=self._config_path)
            return

        try:
            with open(self._config_path, "r") as f:
                data = json.load(f)

            tenants = data.get("tenants", [])
            for tenant_data in tenants:
                tenant = TenantConfig(**tenant_data)
                self._tenants[tenant.tenant_id] = tenant

                # Build number → tenant lookup
                for number in tenant.sip_numbers:
                    self._number_to_tenant[number] = tenant.tenant_id

            logger.info(
                "Tenant configs loaded",
                count=len(self._tenants),
                tenants=list(self._tenants.keys()),
            )
        except Exception as e:
            logger.exception("Failed to load tenant configs", error=str(e))

    async def sync_to_redis(self):
        """Push all tenant configs to Redis for cross-worker access."""
        if not self._redis:
            return

        try:
            for tenant_id, tenant in self._tenants.items():
                await self._redis.set(
                    f"nexus:tenant:{tenant_id}",
                    tenant.model_dump_json(),
                )
                # Also store number → tenant mappings
                for number in tenant.sip_numbers:
                    await self._redis.set(
                        f"nexus:number:{number}",
                        tenant_id,
                    )
            logger.info("Tenant configs synced to Redis", count=len(self._tenants))
        except Exception as e:
            logger.exception("Failed to sync tenants to Redis", error=str(e))

    async def resolve_tenant(self, sip_number: str) -> Optional[TenantConfig]:
        """
        Resolve which tenant owns a given SIP phone number.
        Checks Redis first (production), falls back to in-memory (dev).
        """
        # Try Redis first
        if self._redis:
            try:
                tenant_id = await self._redis.get(f"nexus:number:{sip_number}")
                if tenant_id:
                    tenant_id = tenant_id.decode() if isinstance(tenant_id, bytes) else tenant_id
                    tenant_json = await self._redis.get(f"nexus:tenant:{tenant_id}")
                    if tenant_json:
                        tenant_json = tenant_json.decode() if isinstance(tenant_json, bytes) else tenant_json
                        return TenantConfig.model_validate_json(tenant_json)
            except Exception as e:
                logger.warning("Redis lookup failed, using fallback", error=str(e))

        # Fallback to in-memory
        tenant_id = self._number_to_tenant.get(sip_number)
        if tenant_id:
            return self._tenants.get(tenant_id)

        logger.warning("No tenant found for SIP number", sip_number=sip_number)
        return None

    def get_tenant(self, tenant_id: str) -> Optional[TenantConfig]:
        """Get a tenant config by ID."""
        return self._tenants.get(tenant_id)

    def get_default_tenant(self) -> Optional[TenantConfig]:
        """Get the first available tenant (for local development)."""
        if self._tenants:
            return next(iter(self._tenants.values()))
        return None

    def list_tenants(self) -> list[TenantConfig]:
        """List all registered tenants."""
        return list(self._tenants.values())
