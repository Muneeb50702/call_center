from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class Load(BaseModel):
    id: str = Field(..., description="Unique identifier for the load")
    origin: str = Field(..., description="City and State of pickup (e.g., 'Chicago, IL')")
    destination: str = Field(..., description="City and State of delivery (e.g., 'Dallas, TX')")
    weight_lbs: int = Field(..., description="Weight of the load in pounds")
    commodity: str = Field(..., description="Type of goods being transported")
    equipment_type: str = Field(..., description="Required equipment (e.g., 'Dry Van', 'Reefer', 'Flatbed')")
    rate_per_mile: float = Field(..., description="Base rate per mile in USD")
    status: str = Field(..., description="Current status: 'available', 'booked', 'in_transit', 'delivered'")
    pickup_date: date = Field(..., description="Scheduled pickup date")
    delivery_date: date = Field(..., description="Scheduled delivery date")

    # GPS tracking (for check calls)
    last_known_lat: Optional[float] = None
    last_known_lng: Optional[float] = None
    current_city: Optional[str] = None

    class Config:
        from_attributes = True


class LoadCreate(BaseModel):
    id: str
    origin: str
    destination: str
    weight_lbs: int
    commodity: str
    equipment_type: str
    rate_per_mile: float
    status: str = "available"
    pickup_date: date
    delivery_date: date
