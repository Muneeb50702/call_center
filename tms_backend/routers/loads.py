"""
Nexus Dispatch — Loads Router (Database-Backed)

CRUD and search for freight loads with tenant-scoped data isolation.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, LoadDB
from models.load import Load, LoadCreate
from auth import get_current_user, CurrentUser

router = APIRouter(prefix="/loads", tags=["loads"])


@router.get("/search", response_model=List[Load])
async def search_loads(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    equipment: Optional[str] = None,
    status: Optional[str] = Query(None, description="Filter by status: available, booked, in_transit, delivered"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for available freight loads with filters."""
    query = select(LoadDB).where(LoadDB.tenant_id == user.tenant_id)

    if origin:
        query = query.where(LoadDB.origin.ilike(f"%{origin}%"))
    if destination:
        query = query.where(LoadDB.destination.ilike(f"%{destination}%"))
    if equipment:
        query = query.where(LoadDB.equipment_type.ilike(f"%{equipment}%"))
    if status:
        query = query.where(LoadDB.status == status)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    loads = result.scalars().all()
    return [Load.model_validate(l, from_attributes=True) for l in loads]


@router.get("/{load_id}", response_model=Load)
async def get_load(
    load_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific load by ID."""
    result = await db.execute(
        select(LoadDB).where(LoadDB.id == load_id, LoadDB.tenant_id == user.tenant_id)
    )
    load = result.scalar_one_or_none()
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")
    return Load.model_validate(load, from_attributes=True)


@router.post("/", response_model=Load, status_code=201)
async def create_load(
    req: LoadCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new freight load."""
    load = LoadDB(
        id=req.id,
        tenant_id=user.tenant_id,
        origin=req.origin,
        destination=req.destination,
        weight_lbs=req.weight_lbs,
        commodity=req.commodity,
        equipment_type=req.equipment_type,
        rate_per_mile=req.rate_per_mile,
        status=req.status,
        pickup_date=req.pickup_date,
        delivery_date=req.delivery_date,
    )
    db.add(load)
    await db.flush()
    return Load.model_validate(load, from_attributes=True)


@router.patch("/{load_id}/status")
async def update_load_status(
    load_id: str,
    new_status: str = Query(..., description="New status: available, booked, in_transit, delivered"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a load's status."""
    result = await db.execute(
        select(LoadDB).where(LoadDB.id == load_id, LoadDB.tenant_id == user.tenant_id)
    )
    load = result.scalar_one_or_none()
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")

    valid_statuses = ["available", "booked", "in_transit", "delivered"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    load.status = new_status
    await db.flush()
    return {"id": load_id, "status": new_status}


@router.patch("/{load_id}/location")
async def update_load_location(
    load_id: str,
    lat: float = Query(...),
    lng: float = Query(...),
    city: str = Query(""),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a load's GPS location (for check calls)."""
    from datetime import datetime
    result = await db.execute(
        select(LoadDB).where(LoadDB.id == load_id, LoadDB.tenant_id == user.tenant_id)
    )
    load = result.scalar_one_or_none()
    if not load:
        raise HTTPException(status_code=404, detail="Load not found")

    load.last_known_lat = lat
    load.last_known_lng = lng
    load.current_city = city
    load.last_location_update = datetime.utcnow()
    await db.flush()
    return {"id": load_id, "lat": lat, "lng": lng, "city": city}
