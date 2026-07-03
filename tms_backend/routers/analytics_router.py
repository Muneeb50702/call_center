"""
Nexus Dispatch — Analytics Router

Aggregated analytics for the admin dashboard.
Metrics: call volume, booking rate, revenue, transfer rate, latency.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, CallDB, BookingDB
from auth import get_current_user, CurrentUser

router = APIRouter(prefix="/analytics", tags=["analytics"])


class DashboardKPIs(BaseModel):
    total_calls: int = 0
    total_bookings: int = 0
    booking_rate_pct: float = 0.0
    transfer_rate_pct: float = 0.0
    avg_call_duration_s: float = 0.0
    total_revenue: float = 0.0
    avg_latency_ms: float = 0.0
    calls_today: int = 0
    bookings_today: int = 0


class CallModeBreakdown(BaseModel):
    mode: str
    count: int
    pct: float = 0.0


class DailyMetric(BaseModel):
    date: str
    calls: int = 0
    bookings: int = 0
    revenue: float = 0.0


@router.get("/kpis", response_model=DashboardKPIs)
async def get_kpis(
    days: int = Query(30, ge=1, le=365, description="Number of days to aggregate"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get key performance indicators for the dashboard."""
    since = datetime.utcnow() - timedelta(days=days)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Total calls in period
    calls_result = await db.execute(
        select(
            func.count(CallDB.id).label("total"),
            func.avg(CallDB.duration_seconds).label("avg_duration"),
            func.avg(CallDB.avg_latency_ms).label("avg_latency"),
            func.sum(case((CallDB.transferred_to_human == True, 1), else_=0)).label("transfers"),
        ).where(
            CallDB.tenant_id == user.tenant_id,
            CallDB.started_at >= since,
        )
    )
    call_stats = calls_result.one()

    # Total bookings in period
    bookings_result = await db.execute(
        select(
            func.count(BookingDB.id).label("total"),
            func.sum(BookingDB.agreed_rate).label("total_revenue"),
        ).where(
            BookingDB.tenant_id == user.tenant_id,
            BookingDB.booked_at >= since,
        )
    )
    booking_stats = bookings_result.one()

    # Today's counts
    today_calls = await db.execute(
        select(func.count(CallDB.id)).where(
            CallDB.tenant_id == user.tenant_id,
            CallDB.started_at >= today_start,
        )
    )
    today_bookings = await db.execute(
        select(func.count(BookingDB.id)).where(
            BookingDB.tenant_id == user.tenant_id,
            BookingDB.booked_at >= today_start,
        )
    )

    total_calls = call_stats.total or 0
    total_bookings = booking_stats.total or 0
    transfers = int(call_stats.transfers or 0)

    return DashboardKPIs(
        total_calls=total_calls,
        total_bookings=total_bookings,
        booking_rate_pct=round((total_bookings / total_calls * 100) if total_calls > 0 else 0, 1),
        transfer_rate_pct=round((transfers / total_calls * 100) if total_calls > 0 else 0, 1),
        avg_call_duration_s=round(float(call_stats.avg_duration or 0), 1),
        total_revenue=round(float(booking_stats.total_revenue or 0), 2),
        avg_latency_ms=round(float(call_stats.avg_latency or 0), 0),
        calls_today=today_calls.scalar() or 0,
        bookings_today=today_bookings.scalar() or 0,
    )


@router.get("/call-modes", response_model=list[CallModeBreakdown])
async def get_call_mode_breakdown(
    days: int = Query(30, ge=1, le=365),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get breakdown of calls by mode (load_booking, check_call, etc.)."""
    since = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            CallDB.call_mode,
            func.count(CallDB.id).label("count"),
        ).where(
            CallDB.tenant_id == user.tenant_id,
            CallDB.started_at >= since,
        ).group_by(CallDB.call_mode)
    )
    rows = result.all()
    total = sum(r.count for r in rows) or 1

    return [
        CallModeBreakdown(mode=r.call_mode, count=r.count, pct=round(r.count / total * 100, 1))
        for r in rows
    ]


@router.get("/daily", response_model=list[DailyMetric])
async def get_daily_metrics(
    days: int = Query(30, ge=1, le=90),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily call and booking metrics for charts."""
    since = datetime.utcnow() - timedelta(days=days)

    calls_result = await db.execute(
        select(
            func.date(CallDB.started_at).label("day"),
            func.count(CallDB.id).label("calls"),
        ).where(
            CallDB.tenant_id == user.tenant_id,
            CallDB.started_at >= since,
        ).group_by(func.date(CallDB.started_at))
        .order_by(func.date(CallDB.started_at))
    )

    bookings_result = await db.execute(
        select(
            func.date(BookingDB.booked_at).label("day"),
            func.count(BookingDB.id).label("bookings"),
            func.sum(BookingDB.agreed_rate).label("revenue"),
        ).where(
            BookingDB.tenant_id == user.tenant_id,
            BookingDB.booked_at >= since,
        ).group_by(func.date(BookingDB.booked_at))
        .order_by(func.date(BookingDB.booked_at))
    )

    calls_map = {str(r.day): r.calls for r in calls_result.all()}
    bookings_map = {}
    revenue_map = {}
    for r in bookings_result.all():
        bookings_map[str(r.day)] = r.bookings
        revenue_map[str(r.day)] = float(r.revenue or 0)

    # Build daily series
    all_dates = sorted(set(list(calls_map.keys()) + list(bookings_map.keys())))
    return [
        DailyMetric(
            date=d,
            calls=calls_map.get(d, 0),
            bookings=bookings_map.get(d, 0),
            revenue=round(revenue_map.get(d, 0), 2),
        )
        for d in all_dates
    ]
