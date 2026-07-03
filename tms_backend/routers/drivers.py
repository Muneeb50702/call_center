"""
Nexus Dispatch — Drivers Router (Database-Backed)

Driver management with MC number lookup, HOS status, and onboarding support.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, DriverDB
from models.driver import Driver, DriverCreate
from auth import get_current_user, CurrentUser

router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.get("/", response_model=List[Driver])
async def get_all_drivers(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all drivers for the tenant."""
    result = await db.execute(
        select(DriverDB).where(DriverDB.tenant_id == user.tenant_id)
    )
    drivers = result.scalars().all()
    return [Driver.model_validate(d, from_attributes=True) for d in drivers]


@router.get("/available", response_model=List[Driver])
async def get_available_drivers(
    equipment: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all available drivers, optionally filtered by equipment type."""
    query = select(DriverDB).where(
        DriverDB.tenant_id == user.tenant_id,
        DriverDB.hos_status == "available",
        DriverDB.is_active == True,
    )
    if equipment:
        query = query.where(DriverDB.equipment.ilike(f"%{equipment}%"))

    result = await db.execute(query)
    drivers = result.scalars().all()
    return [Driver.model_validate(d, from_attributes=True) for d in drivers]


@router.get("/by-mc", response_model=Driver)
async def get_driver_by_mc(
    mc_number: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Look up a driver by their MC number."""
    result = await db.execute(
        select(DriverDB).where(
            DriverDB.mc_number.ilike(mc_number),
            DriverDB.tenant_id == user.tenant_id,
        )
    )
    driver = result.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail=f"No driver found with MC number {mc_number}")
    return Driver.model_validate(driver, from_attributes=True)


@router.get("/{driver_id}", response_model=Driver)
async def get_driver(
    driver_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific driver by ID."""
    result = await db.execute(
        select(DriverDB).where(
            DriverDB.id == driver_id,
            DriverDB.tenant_id == user.tenant_id,
        )
    )
    driver = result.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    return Driver.model_validate(driver, from_attributes=True)


@router.post("/", response_model=Driver, status_code=201)
async def create_driver(
    req: DriverCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new driver (onboarding)."""
    # Check for duplicate MC number
    existing = await db.execute(
        select(DriverDB).where(
            DriverDB.mc_number.ilike(req.mc_number),
            DriverDB.tenant_id == user.tenant_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Driver with MC number {req.mc_number} already registered",
        )

    import uuid
    driver = DriverDB(
        id=req.id or f"D-{uuid.uuid4().hex[:6].upper()}",
        tenant_id=user.tenant_id,
        name=req.name,
        mc_number=req.mc_number,
        equipment=req.equipment,
        hos_status=req.hos_status,
        phone=req.phone,
        email=req.email,
        insurance_expiry=req.insurance_expiry,
        dot_number=req.dot_number,
    )
    db.add(driver)
    await db.flush()
    return Driver.model_validate(driver, from_attributes=True)


@router.patch("/{driver_id}/status")
async def update_driver_status(
    driver_id: str,
    hos_status: str = Query(..., description="New HOS status: available, on_duty, driving, off_duty, sleeper_berth"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a driver's HOS status."""
    result = await db.execute(
        select(DriverDB).where(
            DriverDB.id == driver_id,
            DriverDB.tenant_id == user.tenant_id,
        )
    )
    driver = result.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    valid_statuses = ["available", "on_duty", "driving", "off_duty", "sleeper_berth"]
    if hos_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    driver.hos_status = hos_status
    await db.flush()
    return {"id": driver_id, "hos_status": hos_status}
