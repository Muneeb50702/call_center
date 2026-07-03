"""
Nexus Dispatch — Bookings Router (Database-Backed)

Booking creation, status tracking, and listing with tenant isolation.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, BookingDB, LoadDB
from models.booking import Booking, BookingCreate
from auth import get_current_user, CurrentUser

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=Booking, status_code=201)
async def create_booking(
    req: BookingCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new booking — dispatched by the AI agent after rate agreement."""
    # Verify load belongs to tenant and is available
    load_result = await db.execute(
        select(LoadDB).where(
            LoadDB.id == req.load_id,
            LoadDB.tenant_id == user.tenant_id,
        )
    )
    load = load_result.scalar_one_or_none()
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    if load.status != "available":
        raise HTTPException(status_code=409, detail=f"Load is not available (current status: {load.status})")

    booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
    booking = BookingDB(
        id=booking_id,
        tenant_id=user.tenant_id,
        load_id=req.load_id,
        driver_id=req.driver_id,
        agreed_rate=req.agreed_rate,
        status="confirmed",
        booked_at=datetime.utcnow(),
        notes=req.notes,
    )
    db.add(booking)

    # Update load status to 'booked'
    load.status = "booked"
    await db.flush()

    return Booking.model_validate(booking, from_attributes=True)


@router.get("/active", response_model=List[Booking])
async def get_active_bookings(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active (non-cancelled, non-delivered) bookings."""
    result = await db.execute(
        select(BookingDB).where(
            BookingDB.tenant_id == user.tenant_id,
            BookingDB.status.notin_(["cancelled", "delivered"]),
        )
    )
    bookings = result.scalars().all()
    return [Booking.model_validate(b, from_attributes=True) for b in bookings]


@router.get("/{booking_id}", response_model=Booking)
async def get_booking(
    booking_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a specific booking by ID."""
    result = await db.execute(
        select(BookingDB).where(
            BookingDB.id == booking_id,
            BookingDB.tenant_id == user.tenant_id,
        )
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return Booking.model_validate(booking, from_attributes=True)


@router.patch("/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    new_status: str = Query(..., description="New status: dispatched, in_transit, delivered, cancelled"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update booking status (e.g., dispatched → in_transit → delivered)."""
    result = await db.execute(
        select(BookingDB).where(
            BookingDB.id == booking_id,
            BookingDB.tenant_id == user.tenant_id,
        )
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    valid = ["confirmed", "dispatched", "in_transit", "delivered", "cancelled"]
    if new_status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")

    booking.status = new_status

    # Also update load status if booking transitions
    if new_status in ("in_transit", "delivered"):
        load_result = await db.execute(
            select(LoadDB).where(LoadDB.id == booking.load_id)
        )
        load = load_result.scalar_one_or_none()
        if load:
            load.status = new_status

    await db.flush()
    return {"id": booking_id, "status": new_status}
