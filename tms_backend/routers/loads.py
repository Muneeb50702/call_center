from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import json
import os
from models.load import Load

router = APIRouter(prefix="/loads", tags=["loads"])

# Load data into memory for mock DB
data_path = os.path.join(os.path.dirname(__file__), "..", "data", "loads.json")
with open(data_path, "r") as f:
    loads_db = [Load(**item) for item in json.load(f)]

@router.get("/search", response_model=List[Load])
async def search_loads(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    equipment: Optional[str] = None
):
    results = loads_db
    if origin:
        results = [L for L in results if L.origin.lower() == origin.lower()]
    if destination:
        results = [L for L in results if L.destination.lower() == destination.lower()]
    if equipment:
        results = [L for L in results if L.equipment_type.lower() == equipment.lower()]
    return results

@router.get("/{load_id}", response_model=Load)
async def get_load(load_id: str):
    for L in loads_db:
        if L.id == load_id:
            return L
    raise HTTPException(status_code=404, detail="Load not found")
