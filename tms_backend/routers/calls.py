"""
Nexus Dispatch — Calls Router

Call history, live calls, and call details for the admin dashboard.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, CallDB
from auth import get_current_user, CurrentUser

router = APIRouter(prefix="/calls", tags=["calls"])


class CallResponse(BaseModel):
    id: str
    caller_number: str = ""
    driver_name: str = ""
    driver_mc: str = ""
    call_mode: str = "load_booking"
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    outcome: str = "in_progress"
    states_visited: list = []
    tools_invoked: list = []
    booking_id: Optional[str] = None
    agreed_rate: Optional[float] = None
    negotiation_rounds: int = 0
    transferred_to_human: bool = False
    transfer_reason: str = ""
    recording_path: str = ""
    avg_latency_ms: Optional[int] = None

    class Config:
        from_attributes = True


class CallCreate(BaseModel):
    """Used by the agent to register a call when it starts."""
    id: str
    caller_number: str = ""
    call_mode: str = "load_booking"


class CallUpdate(BaseModel):
    """Used by the agent to update call state when it ends."""
    driver_name: Optional[str] = None
    driver_mc: Optional[str] = None
    call_mode: Optional[str] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    outcome: Optional[str] = None
    states_visited: Optional[list] = None
    tools_invoked: Optional[list] = None
    booking_id: Optional[str] = None
    agreed_rate: Optional[float] = None
    negotiation_rounds: Optional[int] = None
    transferred_to_human: Optional[bool] = None
    transfer_reason: Optional[str] = None
    recording_path: Optional[str] = None
    avg_latency_ms: Optional[int] = None
    p95_latency_ms: Optional[int] = None


@router.get("/history", response_model=List[CallResponse])
async def get_call_history(
    days: int = Query(7, ge=1, le=90),
    mode: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get call history with filters."""
    since = datetime.utcnow() - timedelta(days=days)
    query = select(CallDB).where(
        CallDB.tenant_id == user.tenant_id,
        CallDB.started_at >= since,
    )

    if mode:
        query = query.where(CallDB.call_mode == mode)
    if outcome:
        query = query.where(CallDB.outcome == outcome)

    query = query.order_by(desc(CallDB.started_at)).offset(offset).limit(limit)
    result = await db.execute(query)
    calls = result.scalars().all()
    return [CallResponse.model_validate(c, from_attributes=True) for c in calls]


@router.get("/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific call."""
    result = await db.execute(
        select(CallDB).where(
            CallDB.id == call_id,
            CallDB.tenant_id == user.tenant_id,
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return CallResponse.model_validate(call, from_attributes=True)


@router.post("/", response_model=CallResponse, status_code=201)
async def register_call(
    req: CallCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new call (called by the agent at session start)."""
    call = CallDB(
        id=req.id,
        tenant_id=user.tenant_id,
        caller_number=req.caller_number,
        call_mode=req.call_mode,
        started_at=datetime.utcnow(),
    )
    db.add(call)
    await db.flush()
    return CallResponse.model_validate(call, from_attributes=True)


@router.patch("/{call_id}", response_model=CallResponse)
async def update_call(
    call_id: str,
    req: CallUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update call data (called by the agent at session end or transitions)."""
    result = await db.execute(
        select(CallDB).where(
            CallDB.id == call_id,
            CallDB.tenant_id == user.tenant_id,
        )
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(call, field, value)

    await db.flush()
    return CallResponse.model_validate(call, from_attributes=True)
