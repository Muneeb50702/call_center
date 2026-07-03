from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class Driver(BaseModel):
    id: str = Field(..., description="Unique identifier for the driver")
    name: str = Field(..., description="Driver's full name")
    mc_number: str = Field(..., description="Motor Carrier number associated with the driver/carrier")
    equipment: str = Field(..., description="Type of equipment the driver operates (e.g., 'Dry Van', 'Reefer', 'Flatbed')")
    hos_status: str = Field(..., description="Hours of Service status, e.g., 'available', 'on_duty', 'driving', 'off_duty'")
    phone: str = Field(default="", description="Driver's phone number")
    email: str = Field(default="", description="Driver's email address")
    insurance_expiry: Optional[date] = Field(default=None, description="Insurance expiration date")
    dot_number: str = Field(default="", description="DOT number")
    is_active: bool = Field(default=True, description="Whether the driver is active")

    class Config:
        from_attributes = True


class DriverCreate(BaseModel):
    id: str = ""
    name: str
    mc_number: str
    equipment: str
    hos_status: str = "available"
    phone: str = ""
    email: str = ""
    insurance_expiry: Optional[date] = None
    dot_number: str = ""
