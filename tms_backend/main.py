from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import loads, rates, drivers, bookings

app = FastAPI(
    title="Nexus TMS Backend",
    description="Transportation Management System API for freight dispatch operations",
    version="0.2.0",
)

# CORS — restrict in production, permissive for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",     # Admin dashboard (Next.js dev)
        "http://localhost:8001",     # Self-reference
        "http://tms-backend:8000",  # Docker internal
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(loads.router)
app.include_router(rates.router)
app.include_router(drivers.router)
app.include_router(bookings.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "nexus-tms-backend"}
