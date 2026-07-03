"""
Nexus Dispatch — Detention Claims Router

CRUD for detention events. Used by the DetentionAgent to log
when drivers are stuck at facilities beyond free time.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, DetentionClaimDB
from auth import get_current_user, CurrentUser

router = APIRouter(prefix="/detentions", tags=["detentions"])


class DetentionResponse(BaseModel):
    id: str
    load_id: str
    driver_id: str = ""
    facility_name: str = ""
    facility_type: str = "shipper"
    arrival_time: datetime
    departure_time: Optional[datetime] = None
    free_time_hours: float = 2.0
    detention_hours: float = 0.0
    detention_rate_per_hour: float = 75.0
    total_claim_amount: float = 0.0
    status: str = "pending"
    broker_notified: bool = False
    notes: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


class DetentionCreate(BaseModel):
    load_id: str
    driver_id: str = ""
    facility_name: str = ""
    facility_type: str = "shipper"  # shipper or receiver
    arrival_time: datetime
    departure_time: Optional[datetime] = None
    free_time_hours: float = 2.0
    detention_rate_per_hour: float = 75.0
    notes: str = ""


@router.post("/", response_model=DetentionResponse, status_code=201)
async def create_detention_claim(
    req: DetentionCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new detention claim."""
    # Calculate detention hours and amount if departure time provided
    detention_hours = 0.0
    total_amount = 0.0
    if req.departure_time and req.arrival_time:
        total_hours = (req.departure_time - req.arrival_time).total_seconds() / 3600
        detention_hours = max(0, total_hours - req.free_time_hours)
        total_amount = round(detention_hours * req.detention_rate_per_hour, 2)

    claim = DetentionClaimDB(
        id=f"DET-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=user.tenant_id,
        load_id=req.load_id,
        driver_id=req.driver_id,
        facility_name=req.facility_name,
        facility_type=req.facility_type,
        arrival_time=req.arrival_time,
        departure_time=req.departure_time,
        free_time_hours=req.free_time_hours,
        detention_hours=detention_hours,
        detention_rate_per_hour=req.detention_rate_per_hour,
        total_claim_amount=total_amount,
        notes=req.notes,
    )
    db.add(claim)
    await db.flush()
    return DetentionResponse.model_validate(claim, from_attributes=True)


@router.get("/", response_model=List[DetentionResponse])
async def list_detentions(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List detention claims."""
    query = select(DetentionClaimDB).where(
        DetentionClaimDB.tenant_id == user.tenant_id
    )
    if status:
        query = query.where(DetentionClaimDB.status == status)

    query = query.order_by(DetentionClaimDB.created_at.desc()).limit(limit)
    result = await db.execute(query)
    claims = result.scalars().all()
    return [DetentionResponse.model_validate(c, from_attributes=True) for c in claims]


@router.patch("/{claim_id}/close")
async def close_detention(
    claim_id: str,
    departure_time: datetime = Query(...),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close a detention claim (driver has departed the facility)."""
    result = await db.execute(
        select(DetentionClaimDB).where(
            DetentionClaimDB.id == claim_id,
            DetentionClaimDB.tenant_id == user.tenant_id,
        )
    )
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Detention claim not found")

    claim.departure_time = departure_time
    total_hours = (departure_time - claim.arrival_time).total_seconds() / 3600
    claim.detention_hours = max(0, total_hours - claim.free_time_hours)
    claim.total_claim_amount = round(claim.detention_hours * claim.detention_rate_per_hour, 2)
    claim.status = "submitted"
    await db.flush()

    return DetentionResponse.model_validate(claim, from_attributes=True)
