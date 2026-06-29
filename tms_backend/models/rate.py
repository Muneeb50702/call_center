from pydantic import BaseModel, Field

class Rate(BaseModel):
    lane_id: str = Field(..., description="Identifier for the lane, typically 'OriginState-DestState'")
    per_mile: float = Field(..., description="Base rate per mile in USD")
    flat: float = Field(..., description="Optional flat rate in USD if not using per-mile")
    fuel_surcharge: float = Field(..., description="Fuel surcharge percentage or flat fee")
