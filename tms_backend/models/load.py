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
    status: str = Field(..., description="Current status: 'available', 'booked', or 'in_transit'")
    pickup_date: date = Field(..., description="Scheduled pickup date")
    delivery_date: date = Field(..., description="Scheduled delivery date")
