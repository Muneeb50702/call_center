"""
Nexus Dispatch — Service-to-service HTTP auth for TMS tool clients.

The agent worker authenticates to the TMS backend with a shared service key
(``NEXUS_SERVICE_KEY``) plus the tenant it is acting for, instead of a user JWT.
The backend's ``get_current_user`` dependency accepts these headers (see
tms_backend/auth.py). Every tool client attaches these headers to its httpx
client so all backend calls — reads and writes — are authenticated and correctly
tenant-scoped.
"""

import os


def service_headers(tenant_id: str = "") -> dict:
    """Build the auth headers for a backend call on behalf of ``tenant_id``."""
    headers: dict[str, str] = {}
    key = os.getenv("NEXUS_SERVICE_KEY", "")
    if key:
        headers["X-Service-Key"] = key
    if tenant_id:
        headers["X-Tenant-Id"] = tenant_id
    return headers
