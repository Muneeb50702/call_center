"""
Nexus Dispatch — Database Configuration

Async SQLAlchemy engine with PostgreSQL for production-grade persistence.
Connection pool tuned for 50 concurrent calls (pool_size=20, max_overflow=30).

Tables:
- tenants: Multi-tenant configuration
- loads: Freight loads
- drivers: Driver profiles with MC numbers
- rates: Lane-based rate cards
- bookings: Confirmed dispatch bookings
- calls: Call history and analytics
- detention_claims: Detention events
- documents: Rate confirmations, PODs, BOLs metadata
"""

import os
import uuid
from datetime import datetime, date
from typing import Optional, AsyncGenerator

from sqlalchemy import (
    String, Float, Integer, Boolean, Text, DateTime, Date,
    ForeignKey, Index, JSON, Enum as SAEnum,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Engine Configuration ──

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://nexus:nexus_dev_password@localhost:5432/nexus_dispatch",
)

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,       # Base connections in pool
    max_overflow=30,    # Extra connections under load (up to 50 total)
    pool_pre_ping=True, # Verify connections before use
    pool_recycle=3600,  # Recycle connections every hour
    echo=False,         # Set True for SQL debugging
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables. Called on application startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Dispose engine. Called on application shutdown."""
    await engine.dispose()


# ── Base Model ──

class Base(DeclarativeBase):
    pass


# ── Helper ──

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


# =============================================================================
# TENANT TABLE
# =============================================================================

class TenantDB(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    greeting_script: Mapped[str] = mapped_column(Text, default="")
    sip_numbers: Mapped[Optional[str]] = mapped_column(JSON, default=list)
    human_transfer_number: Mapped[str] = mapped_column(String(32), default="")

    # TMS Integration
    tms_api_url: Mapped[str] = mapped_column(String(512), default="http://tms-backend:8000")
    tms_api_key: Mapped[str] = mapped_column(String(255), default="")

    # Voice & STT
    voice_model: Mapped[str] = mapped_column(String(64), default="aura-orion-en")
    custom_keywords: Mapped[Optional[str]] = mapped_column(JSON, default=list)

    # Business Rules
    negotiation_floor_pct: Mapped[float] = mapped_column(Float, default=0.90)
    max_negotiation_rounds: Mapped[int] = mapped_column(Integer, default=3)
    max_concurrent_calls: Mapped[int] = mapped_column(Integer, default=20)

    # LLM
    llm_model: Mapped[str] = mapped_column(String(64), default="llama-3.1-8b-instant")
    llm_temperature: Mapped[float] = mapped_column(Float, default=0.0)

    # Auth
    api_key_hash: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # Relationships
    users: Mapped[list["UserDB"]] = relationship(back_populates="tenant", lazy="selectin")
    loads: Mapped[list["LoadDB"]] = relationship(back_populates="tenant", lazy="selectin")
    drivers: Mapped[list["DriverDB"]] = relationship(back_populates="tenant", lazy="selectin")
    rates: Mapped[list["RateDB"]] = relationship(back_populates="tenant", lazy="selectin")
    bookings: Mapped[list["BookingDB"]] = relationship(back_populates="tenant", lazy="selectin")
    calls: Mapped[list["CallDB"]] = relationship(back_populates="tenant", lazy="selectin")

    __table_args__ = (
        Index("ix_tenants_active", "is_active"),
    )


# =============================================================================
# USER TABLE (Dashboard Authentication)
# =============================================================================

class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"USR-{uuid.uuid4().hex[:8].upper()}")
    tenant_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=True) # Null for super_admin

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="dispatcher")  # super_admin, tenant_admin, dispatcher
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # Relationships
    tenant: Mapped[Optional["TenantDB"]] = relationship(back_populates="users")

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_tenant", "tenant_id"),
    )


# =============================================================================
# LOAD TABLE
# =============================================================================

class LoadDB(Base):
    __tablename__ = "loads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)

    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    weight_lbs: Mapped[int] = mapped_column(Integer, nullable=False)
    commodity: Mapped[str] = mapped_column(String(255), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rate_per_mile: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="available")  # available, booked, in_transit, delivered
    pickup_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)

    # GPS tracking (for check calls)
    last_known_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_known_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_location_update: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    current_city: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Relationships
    tenant: Mapped["TenantDB"] = relationship(back_populates="loads")

    __table_args__ = (
        Index("ix_loads_tenant", "tenant_id"),
        Index("ix_loads_status", "status"),
        Index("ix_loads_equipment", "equipment_type"),
        Index("ix_loads_origin", "origin"),
        Index("ix_loads_destination", "destination"),
    )


# =============================================================================
# DRIVER TABLE
# =============================================================================

class DriverDB(Base):
    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mc_number: Mapped[str] = mapped_column(String(32), nullable=False)
    equipment: Mapped[str] = mapped_column(String(64), nullable=False)
    hos_status: Mapped[str] = mapped_column(String(32), default="available")  # available, on_duty, driving, off_duty, sleeper_berth
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(255), default="")

    # Onboarding fields
    insurance_expiry: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    dot_number: Mapped[str] = mapped_column(String(32), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Relationships
    tenant: Mapped["TenantDB"] = relationship(back_populates="drivers")

    __table_args__ = (
        Index("ix_drivers_tenant", "tenant_id"),
        Index("ix_drivers_mc", "mc_number"),
        Index("ix_drivers_equipment", "equipment"),
        Index("ix_drivers_hos", "hos_status"),
    )


# =============================================================================
# RATE TABLE
# =============================================================================

class RateDB(Base):
    __tablename__ = "rates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)

    lane_id: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g., 'IL-TX'
    per_mile: Mapped[float] = mapped_column(Float, nullable=False)
    flat: Mapped[float] = mapped_column(Float, default=0.0)
    fuel_surcharge: Mapped[float] = mapped_column(Float, default=0.0)
    miles: Mapped[int] = mapped_column(Integer, default=0)  # Lane distance for revenue calc

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # Relationships
    tenant: Mapped["TenantDB"] = relationship(back_populates="rates")

    __table_args__ = (
        Index("ix_rates_tenant_lane", "tenant_id", "lane_id", unique=True),
    )


# =============================================================================
# BOOKING TABLE
# =============================================================================

class BookingDB(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)

    load_id: Mapped[str] = mapped_column(String(32), ForeignKey("loads.id"), nullable=False)
    driver_id: Mapped[str] = mapped_column(String(32), nullable=False)
    agreed_rate: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="confirmed")  # confirmed, dispatched, in_transit, delivered, cancelled
    booked_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    notes: Mapped[str] = mapped_column(Text, default="")

    # Rate confirmation tracking
    rate_con_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_con_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    tenant: Mapped["TenantDB"] = relationship(back_populates="bookings")
    load: Mapped["LoadDB"] = relationship()

    __table_args__ = (
        Index("ix_bookings_tenant", "tenant_id"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_load", "load_id"),
    )


# =============================================================================
# CALL HISTORY TABLE
# =============================================================================

class CallDB(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)

    # Caller info
    caller_number: Mapped[str] = mapped_column(String(32), default="")
    driver_name: Mapped[str] = mapped_column(String(255), default="")
    driver_mc: Mapped[str] = mapped_column(String(32), default="")

    # Call metadata
    call_mode: Mapped[str] = mapped_column(String(32), default="load_booking")  # load_booking, check_call, eta_update, etc.
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # Outcome
    outcome: Mapped[str] = mapped_column(String(32), default="in_progress")  # booked, no_match, transferred, completed
    states_visited: Mapped[Optional[str]] = mapped_column(JSON, default=list)
    tools_invoked: Mapped[Optional[str]] = mapped_column(JSON, default=list)

    # Rate info
    booking_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    agreed_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    negotiation_rounds: Mapped[int] = mapped_column(Integer, default=0)

    # Transfer
    transferred_to_human: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_reason: Mapped[str] = mapped_column(Text, default="")

    # Recording
    recording_path: Mapped[str] = mapped_column(String(512), default="")

    # Latency
    avg_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    p95_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    tenant: Mapped["TenantDB"] = relationship(back_populates="calls")

    __table_args__ = (
        Index("ix_calls_tenant", "tenant_id"),
        Index("ix_calls_started", "started_at"),
        Index("ix_calls_mode", "call_mode"),
        Index("ix_calls_outcome", "outcome"),
    )


# =============================================================================
# DETENTION CLAIMS TABLE
# =============================================================================

class DetentionClaimDB(Base):
    __tablename__ = "detention_claims"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"DET-{uuid.uuid4().hex[:8].upper()}")
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)

    load_id: Mapped[str] = mapped_column(String(32), ForeignKey("loads.id"), nullable=False)
    driver_id: Mapped[str] = mapped_column(String(32), default="")
    facility_name: Mapped[str] = mapped_column(String(255), default="")
    facility_type: Mapped[str] = mapped_column(String(32), default="shipper")  # shipper, receiver

    arrival_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    departure_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    free_time_hours: Mapped[float] = mapped_column(Float, default=2.0)  # Standard 2-hour free time
    detention_hours: Mapped[float] = mapped_column(Float, default=0.0)
    detention_rate_per_hour: Mapped[float] = mapped_column(Float, default=75.0)
    total_claim_amount: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, submitted, approved, denied
    broker_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_detention_tenant", "tenant_id"),
        Index("ix_detention_status", "status"),
    )


# =============================================================================
# DOCUMENT TABLE
# =============================================================================

class DocumentDB(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"DOC-{uuid.uuid4().hex[:8].upper()}")
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)

    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)  # rate_confirmation, pod, bol
    reference_id: Mapped[str] = mapped_column(String(64), default="")  # booking_id or load_id
    file_path: Mapped[str] = mapped_column(String(512), default="")
    sent_to_email: Mapped[str] = mapped_column(String(255), default="")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="generated")  # generated, sent, failed

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_documents_tenant", "tenant_id"),
        Index("ix_documents_type", "doc_type"),
    )
