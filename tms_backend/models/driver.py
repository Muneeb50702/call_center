from pydantic import BaseModel, Field

class Driver(BaseModel):
    id: str = Field(..., description="Unique identifier for the driver")
    name: str = Field(..., description="Driver's full name")
    mc_number: str = Field(..., description="Motor Carrier number associated with the driver/carrier")
    equipment: str = Field(..., description="Type of equipment the driver operates (e.g., 'Dry Van', 'Reefer', 'Flatbed')")
    hos_status: str = Field(..., description="Hours of Service status, e.g., 'available', 'on_duty', 'driving', 'off_duty'")
