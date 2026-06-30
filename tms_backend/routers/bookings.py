from fastapi import APIRouter, HTTPException
from typing import List
import json
import os
import uuid
from datetime import datetime
from models.booking import Booking, BookingCreate

router = APIRouter(prefix="/bookings", tags=["bookings"])

# Load existing bookings
data_path = os.path.join(os.path.dirname(__file__), "..", "data", "bookings.json")
with open(data_path, "r") as f:
    bookings_db: list[dict] = json.load(f)


def _save_bookings():
    """Persist bookings to disk."""
    with open(data_path, "w") as f:
        json.dump(bookings_db, f, indent=2)


@router.post("/", response_model=Booking, status_code=201)
async def create_booking(req: BookingCreate):
    """Create a new booking — dispatched by the AI agent after rate agreement."""
    booking = Booking(
        id=f"BK-{uuid.uuid4().hex[:8].upper()}",
        load_id=req.load_id,
        driver_id=req.driver_id,
        agreed_rate=req.agreed_rate,
        status="confirmed",
        booked_at=datetime.now().isoformat(),
        notes=req.notes,
    )
    bookings_db.append(booking.model_dump())
    _save_bookings()
    return booking


@router.get("/active", response_model=List[Booking])
async def get_active_bookings():
    """List all active (non-cancelled, non-delivered) bookings."""
    active = [
        Booking(**b) for b in bookings_db
        if b.get("status") not in ("cancelled", "delivered")
    ]
    return active


@router.get("/{booking_id}", response_model=Booking)
async def get_booking(booking_id: str):
    """Retrieve a specific booking by ID."""
    for b in bookings_db:
        if b["id"] == booking_id:
            return Booking(**b)
    raise HTTPException(status_code=404, detail="Booking not found")
