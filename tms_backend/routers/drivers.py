from fastapi import APIRouter, HTTPException
from typing import List, Optional
import json
import os
from models.driver import Driver

router = APIRouter(prefix="/drivers", tags=["drivers"])

data_path = os.path.join(os.path.dirname(__file__), "..", "data", "drivers.json")
with open(data_path, "r") as f:
    drivers_db = [Driver(**item) for item in json.load(f)]

@router.get("/available", response_model=List[Driver])
async def get_available_drivers(equipment: Optional[str] = None):
    results = [d for d in drivers_db if d.hos_status == "available"]
    if equipment:
        results = [d for d in results if d.equipment.lower() == equipment.lower()]
    return results

@router.get("/by-mc", response_model=Driver)
async def get_driver_by_mc(mc_number: str):
    """Look up a driver by their MC number."""
    for d in drivers_db:
        if d.mc_number.lower() == mc_number.lower():
            return d
    raise HTTPException(status_code=404, detail=f"No driver found with MC number {mc_number}")


@router.get("/{driver_id}", response_model=Driver)
async def get_driver(driver_id: str):
    for d in drivers_db:
        if d.id == driver_id:
            return d
    raise HTTPException(status_code=404, detail="Driver not found")
