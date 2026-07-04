"""
Nexus Dispatch — Tenants Router

CRUD API for tenant management. Admin-only endpoints for onboarding
new dispatch companies.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, TenantDB
from auth import (
    get_current_user, require_admin, CurrentUser,
    create_access_token, generate_api_key, hash_api_key,
    LoginRequest, TokenResponse,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


# ── Schemas ──

class TenantResponse(BaseModel):
    id: str
    company_name: str
    greeting_script: str = ""
    sip_numbers: list = []
    human_transfer_number: str = ""
    tms_api_url: str = ""
    voice_model: str = "aura-orion-en"
    custom_keywords: list = []
    negotiation_floor_pct: float = 0.90
    max_negotiation_rounds: int = 3
    max_concurrent_calls: int = 20
    llm_model: str = "gemini-1.5-flash"
    llm_temperature: float = 0.0
    is_active: bool = True

    class Config:
        from_attributes = True


class TenantCreate(BaseModel):
    id: str = Field(..., description="Unique tenant ID (slug format, e.g., 'abc-logistics')")
    company_name: str
    greeting_script: str = ""
    sip_numbers: list = []
    human_transfer_number: str = ""
    voice_model: str = "aura-orion-en"
    custom_keywords: list = []
    negotiation_floor_pct: float = 0.90
    max_negotiation_rounds: int = 3
    max_concurrent_calls: int = 20
    llm_model: str = "gemini-1.5-flash"
    llm_temperature: float = 0.0


class TenantUpdate(BaseModel):
    company_name: Optional[str] = None
    greeting_script: Optional[str] = None
    sip_numbers: Optional[list] = None
    human_transfer_number: Optional[str] = None
    voice_model: Optional[str] = None
    custom_keywords: Optional[list] = None
    negotiation_floor_pct: Optional[float] = None
    max_negotiation_rounds: Optional[int] = None
    max_concurrent_calls: Optional[int] = None
    llm_model: Optional[str] = None
    llm_temperature: Optional[float] = None
    is_active: Optional[bool] = None


class OnboardResponse(BaseModel):
    tenant: TenantResponse
    api_key: str  # Only shown once at creation time
    token: TokenResponse


# ── Auth Endpoint (Public) ──

@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with an API key and receive a JWT token."""
    key_hash = hash_api_key(req.api_key)
    result = await db.execute(
        select(TenantDB).where(
            TenantDB.api_key_hash == key_hash,
            TenantDB.is_active == True,
        )
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return create_access_token(tenant_id=tenant.id, role="dispatcher")


@router.post("/login/admin", response_model=TokenResponse)
async def admin_login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate as admin (uses special admin API key pattern)."""
    # Admin key format: nxd_admin_<secret>
    if not req.api_key.startswith("nxd_admin_"):
        raise HTTPException(status_code=401, detail="Invalid admin key")

    key_hash = hash_api_key(req.api_key)
    result = await db.execute(
        select(TenantDB).where(
            TenantDB.api_key_hash == key_hash,
            TenantDB.is_active == True,
        )
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid admin key")

    return create_access_token(tenant_id=tenant.id, role="admin")


# ── CRUD Endpoints ──

@router.get("/", response_model=List[TenantResponse])
async def list_tenants(
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all tenants (admin only)."""
    result = await db.execute(select(TenantDB))
    tenants = result.scalars().all()
    return [TenantResponse.model_validate(t, from_attributes=True) for t in tenants]


@router.get("/me", response_model=TenantResponse)
async def get_my_tenant(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current tenant's configuration."""
    result = await db.execute(
        select(TenantDB).where(TenantDB.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantResponse.model_validate(tenant, from_attributes=True)


@router.post("/onboard", response_model=OnboardResponse, status_code=201)
async def onboard_tenant(
    req: TenantCreate,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Onboard a new tenant (admin only). Returns API key (shown only once)."""
    # Check for duplicate ID
    existing = await db.execute(
        select(TenantDB).where(TenantDB.id == req.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Tenant '{req.id}' already exists")

    # Generate API key
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)

    tenant = TenantDB(
        id=req.id,
        company_name=req.company_name,
        greeting_script=req.greeting_script,
        sip_numbers=req.sip_numbers,
        human_transfer_number=req.human_transfer_number,
        voice_model=req.voice_model,
        custom_keywords=req.custom_keywords,
        negotiation_floor_pct=req.negotiation_floor_pct,
        max_negotiation_rounds=req.max_negotiation_rounds,
        max_concurrent_calls=req.max_concurrent_calls,
        llm_model=req.llm_model,
        llm_temperature=req.llm_temperature,
        api_key_hash=key_hash,
    )
    db.add(tenant)
    await db.flush()

    token = create_access_token(tenant_id=tenant.id, role="admin")

    return OnboardResponse(
        tenant=TenantResponse.model_validate(tenant, from_attributes=True),
        api_key=api_key,
        token=token,
    )


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    req: TenantUpdate,
    user: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a tenant's configuration (admin only)."""
    result = await db.execute(
        select(TenantDB).where(TenantDB.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)

    await db.flush()
    return TenantResponse.model_validate(tenant, from_attributes=True)
