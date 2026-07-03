from pydantic import BaseModel, Field


class Rate(BaseModel):
    lane_id: str = Field(..., description="Identifier for the lane, typically 'OriginState-DestState'")
    per_mile: float = Field(..., description="Base rate per mile in USD")
    flat: float = Field(default=0.0, description="Optional flat rate in USD if not using per-mile")
    fuel_surcharge: float = Field(default=0.0, description="Fuel surcharge percentage or flat fee")
    miles: int = Field(default=0, description="Lane distance in miles")

    class Config:
        from_attributes = True
