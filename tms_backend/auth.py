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

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Using PyJWT (lighter than python-jose)
import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "nexus_jwt_dev_secret_change_in_production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

security_scheme = HTTPBearer()


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


# ── FastAPI Dependencies ──

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme),
) -> CurrentUser:
    """Extract and validate the current user from the JWT token."""
    payload = decode_access_token(credentials.credentials)
    return CurrentUser(tenant_id=payload.tenant_id, role=payload.role)


async def require_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require admin role."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_dispatcher_or_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require dispatcher or admin role."""
    if user.role not in ("admin", "dispatcher"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dispatcher or admin access required",
        )
    return user
