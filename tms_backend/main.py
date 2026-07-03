"""
Nexus Dispatch — TMS Backend

Transportation Management System API for freight dispatch operations.
Production-grade with PostgreSQL, JWT auth, and tenant-scoped data isolation.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, close_db, async_session, TenantDB, LoadDB, DriverDB, RateDB, UserDB
from routers import loads, rates, drivers, bookings, tenants, analytics_router, calls, detentions, documents
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

    async with async_session() as session:
        # Check if data already exists
        from sqlalchemy import select, func
        result = await session.execute(select(func.count(TenantDB.id)))
        count = result.scalar()
        if count and count > 0:
            return  # Already seeded

        # ── Seed Tenants ──
        # Default admin key: nxd_admin_default_dev_key (for local development only)
        admin_key_hash = hash_api_key("nxd_admin_default_dev_key")
        # Dispatcher key: nxd_abc_logistics_dev_key
        abc_key_hash = hash_api_key("nxd_abc_logistics_dev_key")
        pak_key_hash = hash_api_key("nxd_paktruck_dev_key")

        abc_tenant = TenantDB(
            id="abc-logistics",
            company_name="ABC Logistics",
            sip_numbers=["+15550100", "+15550101"],
            human_transfer_number="+15559999",
            tms_api_url="http://tms-backend:8000",
            voice_model="aura-orion-en",
            custom_keywords=["ABC Logistics"],
            negotiation_floor_pct=0.90,
            max_negotiation_rounds=3,
            max_concurrent_calls=20,
            llm_model="llama-3.1-8b-instant",
            llm_temperature=0.0,
            api_key_hash=admin_key_hash,  # Admin key for ABC (first tenant = admin)
        )
        session.add(abc_tenant)

        pak_tenant = TenantDB(
            id="paktruck-dispatch",
            company_name="PakTruck Dispatch",
            sip_numbers=["+15550200", "+15550201"],
            human_transfer_number="+15558888",
            tms_api_url="http://tms-backend:8000",
            voice_model="aura-asteria-en",
            custom_keywords=["PakTruck", "PakTruck Dispatch"],
            negotiation_floor_pct=0.85,
            max_negotiation_rounds=4,
            max_concurrent_calls=50,
            llm_model="llama-3.3-70b-versatile",
            llm_temperature=0.0,
            api_key_hash=pak_key_hash,
        )
        session.add(pak_tenant)

        # ── Seed Loads ──
        loads = [
            LoadDB(id="1001", tenant_id="abc-logistics", origin="Chicago, IL", destination="Dallas, TX",
                   weight_lbs=42000, commodity="Auto Parts", equipment_type="Dry Van",
                   rate_per_mile=2.50, status="available",
                   pickup_date=date(2026, 7, 5), delivery_date=date(2026, 7, 7)),
            LoadDB(id="1002", tenant_id="abc-logistics", origin="Los Angeles, CA", destination="Phoenix, AZ",
                   weight_lbs=35000, commodity="Produce", equipment_type="Reefer",
                   rate_per_mile=3.10, status="available",
                   pickup_date=date(2026, 7, 6), delivery_date=date(2026, 7, 7)),
            LoadDB(id="1003", tenant_id="abc-logistics", origin="Atlanta, GA", destination="Miami, FL",
                   weight_lbs=45000, commodity="Building Materials", equipment_type="Flatbed",
                   rate_per_mile=2.80, status="available",
                   pickup_date=date(2026, 7, 4), delivery_date=date(2026, 7, 5)),
            LoadDB(id="2001", tenant_id="paktruck-dispatch", origin="Houston, TX", destination="Memphis, TN",
                   weight_lbs=38000, commodity="Electronics", equipment_type="Dry Van",
                   rate_per_mile=2.65, status="available",
                   pickup_date=date(2026, 7, 5), delivery_date=date(2026, 7, 7)),
            LoadDB(id="2002", tenant_id="paktruck-dispatch", origin="Seattle, WA", destination="Portland, OR",
                   weight_lbs=28000, commodity="Frozen Foods", equipment_type="Reefer",
                   rate_per_mile=3.30, status="available",
                   pickup_date=date(2026, 7, 6), delivery_date=date(2026, 7, 6)),
        ]
        session.add_all(loads)

        # ── Seed Drivers ──
        drivers = [
            DriverDB(id="D-001", tenant_id="abc-logistics", name="John Smith",
                     mc_number="MC123456", equipment="Dry Van", hos_status="available",
                     phone="+15551234", email="john@example.com"),
            DriverDB(id="D-002", tenant_id="abc-logistics", name="Sarah Connor",
                     mc_number="MC654321", equipment="Reefer", hos_status="driving",
                     phone="+15555678", email="sarah@example.com"),
            DriverDB(id="D-003", tenant_id="abc-logistics", name="Mike Ehrmantraut",
                     mc_number="MC111222", equipment="Flatbed", hos_status="available",
                     phone="+15559012", email="mike@example.com"),
            DriverDB(id="D-004", tenant_id="paktruck-dispatch", name="Ali Khan",
                     mc_number="MC777888", equipment="Dry Van", hos_status="available",
                     phone="+15553456", email="ali@example.com"),
            DriverDB(id="D-005", tenant_id="paktruck-dispatch", name="Ahmed Raza",
                     mc_number="MC999000", equipment="Reefer", hos_status="available",
                     phone="+15557890", email="ahmed@example.com"),
        ]
        session.add_all(drivers)

        # ── Seed Rates ──
        rates = [
            RateDB(tenant_id="abc-logistics", lane_id="IL-TX", per_mile=2.45, fuel_surcharge=0.35, miles=920),
            RateDB(tenant_id="abc-logistics", lane_id="CA-AZ", per_mile=3.00, fuel_surcharge=0.40, miles=370),
            RateDB(tenant_id="abc-logistics", lane_id="GA-FL", per_mile=2.70, fuel_surcharge=0.30, miles=660),
            RateDB(tenant_id="paktruck-dispatch", lane_id="TX-TN", per_mile=2.55, fuel_surcharge=0.35, miles=780),
            RateDB(tenant_id="paktruck-dispatch", lane_id="WA-OR", per_mile=3.15, fuel_surcharge=0.30, miles=175),
        ]
        session.add_all(rates)

        # ── Seed Users ──
        admin_password = passlib.hash.bcrypt.hash("admin")
        users = [
            UserDB(email="admin@nexusdispatch.ai", password_hash=admin_password, role="super_admin", tenant_id=None),
            UserDB(email="client@abclogistics.com", password_hash=admin_password, role="tenant_admin", tenant_id="abc-logistics")
        ]
        session.add_all(users)

        await session.commit()
        print("✅ Database seeded with default tenants, loads, drivers, rates, and users")
