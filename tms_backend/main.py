"""
Nexus Dispatch — TMS Backend

Transportation Management System API for freight dispatch operations.
Production-grade with PostgreSQL, JWT auth, and tenant-scoped data isolation.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, close_db, async_session, TenantDB, LoadDB, DriverDB, RateDB, UserDB
from routers import (
    loads, rates, drivers, bookings, tenants, analytics_router, calls,
    detentions, documents, demo,
)
from routers.auth_router import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # Startup: Initialize database tables and seed data
    await init_db()
    await _seed_default_data()
    yield
    # Shutdown: Close database connections
    await close_db()


app = FastAPI(
    title="Nexus TMS Backend",
    description="Transportation Management System API for freight dispatch operations",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — restrict in production, permissive for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",     # Dashboard (Next.js dev)
        "http://localhost:8001",     # Self-reference
        "http://tms-backend:8000",   # Docker internal
        "*",                         # Allow all in dev — restrict in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(loads.router)
app.include_router(rates.router)
app.include_router(drivers.router)
app.include_router(auth_router)
app.include_router(bookings.router)
app.include_router(tenants.router)
app.include_router(analytics_router.router)
app.include_router(calls.router)
app.include_router(detentions.router)
app.include_router(documents.router)
# Public — the client-facing voice demo. Unauthenticated by design; see
# routers/demo.py for the rate limiting that keeps that safe.
app.include_router(demo.router)
from routers import websocket
app.include_router(websocket.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "nexus-tms-backend", "version": "1.0.0"}


async def _seed_default_data():
    """Seed the database with default tenant + sample data for development."""
    from auth import hash_api_key
    from datetime import date
    import passlib.hash
    from sqlalchemy import select, func

    async with async_session() as session:
        # ── Seed Only Super Admin User ──
        # Check if users exist to prevent duplicate key errors
        result = await session.execute(select(func.count(UserDB.id)))
        count = result.scalar()
        if count == 0:
            admin_password = passlib.hash.bcrypt.hash("admin")
            users = [
                UserDB(email="admin@nexusdispatch.ai", password_hash=admin_password, role="super_admin", tenant_id=None),
            ]
            session.add_all(users)
            await session.commit()
            print("✅ Database seeded with default super admin only")
