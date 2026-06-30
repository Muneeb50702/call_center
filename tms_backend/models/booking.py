from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Booking(BaseModel):
    id: str = Field(..., description="Unique booking identifier")
    load_id: str = Field(..., description="ID of the booked load")
    driver_id: str = Field(..., description="ID or MC number of the assigned driver")
    agreed_rate: float = Field(..., description="Agreed rate per mile in USD")
    status: str = Field(
        default="confirmed",
        description="Booking status: 'confirmed', 'dispatched', 'in_transit', 'delivered', 'cancelled'",
    )
    booked_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp of when the booking was created",
    )
    notes: str = Field(default="", description="Optional notes from the AI dispatcher")


class BookingCreate(BaseModel):
    """Request body for creating a new booking."""
    load_id: str
    driver_id: str
    agreed_rate: float
    notes: str = ""
