"""
Nexus Dispatch — Rates Router (Database-Backed)

Lane rate management and negotiation with tenant-specific business rules.
Uses tenant's negotiation_floor_pct instead of hardcoded 10%.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, RateDB, TenantDB
from models.rate import Rate
from auth import get_current_user, CurrentUser

router = APIRouter(prefix="/rates", tags=["rates"])


class NegotiateRequest(BaseModel):
    lane_id: str
    counter_offer: float


class NegotiateResponse(BaseModel):
    accepted: bool
    message: str
    minimum_rate: float = 0.0


@router.get("/", response_model=List[Rate])
async def list_rates(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all rates for the tenant."""
    result = await db.execute(
        select(RateDB).where(RateDB.tenant_id == user.tenant_id)
    )
    rates = result.scalars().all()
    return [Rate.model_validate(r, from_attributes=True) for r in rates]


@router.get("/{lane_id}", response_model=Rate)
async def get_rate(
    lane_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current base rate for a specific lane."""
    result = await db.execute(
        select(RateDB).where(
            RateDB.lane_id == lane_id,
            RateDB.tenant_id == user.tenant_id,
        )
    )
    rate = result.scalar_one_or_none()
    if not rate:
        raise HTTPException(status_code=404, detail="Rate not found for lane")
    return Rate.model_validate(rate, from_attributes=True)


@router.post("/negotiate", response_model=NegotiateResponse)
async def negotiate_rate(
    req: NegotiateRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Negotiate a rate for a lane using the tenant's specific negotiation floor.
    Uses tenant.negotiation_floor_pct instead of hardcoded 10%.
    """
    # Get the rate
    rate_result = await db.execute(
        select(RateDB).where(
            RateDB.lane_id == req.lane_id,
            RateDB.tenant_id == user.tenant_id,
        )
    )
    rate = rate_result.scalar_one_or_none()
    if not rate:
        raise HTTPException(status_code=404, detail="Lane not found")

    # Get tenant's negotiation floor
    tenant_result = await db.execute(
        select(TenantDB).where(TenantDB.id == user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    floor_pct = tenant.negotiation_floor_pct if tenant else 0.90

    min_acceptable_rate = round(rate.per_mile * floor_pct, 2)

    if req.counter_offer >= min_acceptable_rate:
        return NegotiateResponse(
            accepted=True,
            message=f"Counter offer of ${req.counter_offer:.2f}/mile accepted.",
            minimum_rate=min_acceptable_rate,
        )
    else:
        return NegotiateResponse(
            accepted=False,
            message=f"Counter offer too low. Minimum acceptable is ${min_acceptable_rate:.2f}/mile.",
            minimum_rate=min_acceptable_rate,
        )


@router.post("/", response_model=Rate, status_code=201)
async def create_rate(
    lane_id: str,
    per_mile: float,
    flat: float = 0.0,
    fuel_surcharge: float = 0.0,
    miles: int = 0,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a rate for a lane."""
    # Check if rate exists
    result = await db.execute(
        select(RateDB).where(
            RateDB.lane_id == lane_id,
            RateDB.tenant_id == user.tenant_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.per_mile = per_mile
        existing.flat = flat
        existing.fuel_surcharge = fuel_surcharge
        existing.miles = miles
        await db.flush()
        return Rate.model_validate(existing, from_attributes=True)

    rate = RateDB(
        tenant_id=user.tenant_id,
        lane_id=lane_id,
        per_mile=per_mile,
        flat=flat,
        fuel_surcharge=fuel_surcharge,
        miles=miles,
    )
    db.add(rate)
    await db.flush()
    return Rate.model_validate(rate, from_attributes=True)
