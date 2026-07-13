"""
Nexus Dispatch — Call Reporter

Persists call records to the TMS backend: POST /calls/ at session start, PATCH
/calls/{id} at end (and optionally mid-call). Authenticates with the service key
(via service_http.service_headers). Best-effort: every failure is logged, never
raised, so a persistence hiccup can never break a live call.
"""

import httpx
import structlog

from tools.service_http import service_headers

logger = structlog.get_logger()


class CallReporter:
    def __init__(self, base_url: str, tenant_id: str = ""):
        self.client = httpx.AsyncClient(
            base_url=base_url, timeout=5.0, headers=service_headers(tenant_id)
        )

    async def register(self, call_id: str, caller_number: str = "",
                       call_mode: str = "load_booking", direction: str = "inbound") -> None:
        try:
            await self.client.post("/calls/", json={
                "id": call_id,
                "caller_number": caller_number,
                "call_mode": call_mode,
                "direction": direction,
            })
        except Exception as e:
            logger.warning("call register failed", call_id=call_id, error=str(e))

    async def update(self, call_id: str, **fields) -> None:
        payload = {k: v for k, v in fields.items() if v is not None}
        if not payload:
            return
        try:
            await self.client.patch(f"/calls/{call_id}", json=payload)
        except Exception as e:
            logger.warning("call update failed", call_id=call_id, error=str(e))

    async def close(self) -> None:
        try:
            await self.client.aclose()
        except Exception:
            pass
