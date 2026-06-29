from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import os
from models.rate import Rate

router = APIRouter(prefix="/rates", tags=["rates"])

data_path = os.path.join(os.path.dirname(__file__), "..", "data", "rates.json")
with open(data_path, "r") as f:
    rates_db = [Rate(**item) for item in json.load(f)]

class NegotiateRequest(BaseModel):
    lane_id: str
    counter_offer: float

class NegotiateResponse(BaseModel):
    accepted: bool
    message: str

@router.get("/{lane_id}", response_model=Rate)
async def get_rate(lane_id: str):
    for r in rates_db:
        if r.lane_id == lane_id:
            return r
    raise HTTPException(status_code=404, detail="Rate not found for lane")

@router.post("/negotiate", response_model=NegotiateResponse)
async def negotiate_rate(req: NegotiateRequest):
    rate = None
    for r in rates_db:
        if r.lane_id == req.lane_id:
            rate = r
            break
    
    if not rate:
        raise HTTPException(status_code=404, detail="Lane not found")
    
    # Simple negotiation logic: Accept if counter offer is within 10% of base rate
    min_acceptable_rate = rate.per_mile * 0.90
    if req.counter_offer >= min_acceptable_rate:
        return NegotiateResponse(accepted=True, message=f"Counter offer of ${req.counter_offer}/mile accepted.")
    else:
        return NegotiateResponse(accepted=False, message=f"Counter offer too low. Minimum acceptable is ${min_acceptable_rate:.2f}/mile.")
