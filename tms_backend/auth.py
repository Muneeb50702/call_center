"""
Nexus Dispatch — JWT Authentication & Authorization

Provides:
- JWT token generation and validation
- API key → tenant resolution
- Role-based access control (admin, dispatcher, viewer)
- FastAPI dependency for protecting endpoints
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Using PyJWT (lighter than python-jose)
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "nexus_jwt_dev_secret_change_in_production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Shared secret for service-to-service auth (the agent worker → this backend).
# The agent sends `X-Service-Key: <this>` plus `X-Tenant-Id: <tenant>` instead of
# a user JWT. Set the same value in the agent and backend environments.
SERVICE_KEY = os.getenv("NEXUS_SERVICE_KEY", "")

# Role tiers (the real roles come from UserDB: super_admin / tenant_admin /
# dispatcher; "admin" is a legacy alias minted by routers/tenants.py).
SUPER_ADMIN_ROLES = frozenset({"super_admin"})
ADMIN_ROLES = frozenset({"super_admin", "tenant_admin", "admin"})
STAFF_ROLES = ADMIN_ROLES | frozenset({"dispatcher"})

# auto_error=False so we can fall back to service-key auth when no bearer is sent.
security_scheme = HTTPBearer(auto_error=False)


# ── Models ──

class TokenPayload(BaseModel):
    tenant_id: str
    role: str  # admin, dispatcher, viewer
    exp: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    tenant_id: str
    role: str


class LoginRequest(BaseModel):
    api_key: str


class CurrentUser(BaseModel):
    tenant_id: str
    role: str


# ── Token Utilities ──

def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage. Uses SHA-256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return f"nxd_{secrets.token_urlsafe(32)}"


def create_access_token(tenant_id: str, role: str = "dispatcher") -> TokenResponse:
    """Create a JWT access token for a tenant."""
    expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "tenant_id": tenant_id,
        "role": role,
        "exp": expires,
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return TokenResponse(
        access_token=token,
        expires_in=JWT_EXPIRATION_HOURS * 3600,
        tenant_id=tenant_id,
        role=role,
    )


def decode_access_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def decode_token(token: str) -> dict:
    """Decode a JWT and return the raw payload dict (no HTTPException).

    Used by the WebSocket handshake, where raising HTTP errors is awkward — the
    caller wraps this in try/except and closes the socket on failure. Raises the
    underlying ``jwt`` exceptions on an invalid/expired/empty token.
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ── FastAPI Dependencies ──

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    x_service_key: Optional[str] = Header(default=None, alias="X-Service-Key"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
) -> CurrentUser:
    """Resolve the caller: a dashboard user (JWT) or the agent worker (service key).

    Service auth: the agent sends ``X-Service-Key`` (matched against
    ``NEXUS_SERVICE_KEY``) and ``X-Tenant-Id`` so it can read/write its tenant's
    data without a user login. Everyone else must present a valid bearer JWT.
    """
    if SERVICE_KEY and x_service_key and secrets.compare_digest(x_service_key, SERVICE_KEY):
        return CurrentUser(tenant_id=x_tenant_id or "", role="service")

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_access_token(credentials.credentials)
    return CurrentUser(tenant_id=payload.tenant_id, role=payload.role)


async def require_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require an admin-tier role (super_admin, tenant_admin, or legacy admin)."""
    if user.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_super_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require the super_admin role (cross-tenant / provisioning operations)."""
    if user.role not in SUPER_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return user


async def require_dispatcher_or_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require any staff role (dispatcher or an admin-tier role)."""
    if user.role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dispatcher or admin access required",
        )
    return user
