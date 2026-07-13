"""
Nexus Dispatch — Detention Tools

Tools for handling detention claims when drivers are stuck at facilities.
"""

import structlog
import httpx
from datetime import datetime

from tools.service_http import service_headers

logger = structlog.get_logger()


class DetentionTools:
    """Tools for detention claim operations."""

    def __init__(self, base_url: str = "http://localhost:8000", tenant_id: str = ""):
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=base_url, timeout=5.0, headers=service_headers(tenant_id)
        )

    async def create_detention_claim(
        self,
        load_id: str,
        facility_name: str = "",
        facility_type: str = "shipper",
        arrival_time: str = "",
        departure_time: str = "",
        driver_id: str = "",
        notes: str = "",
    ) -> str:
        """Create a detention claim for a driver stuck at a facility."""
        logger.info(
            "Creating detention claim",
            load_id=load_id,
            facility=facility_name,
            facility_type=facility_type,
        )
        try:
            payload = {
                "load_id": load_id,
                "driver_id": driver_id,
                "facility_name": facility_name,
                "facility_type": facility_type,
                "arrival_time": arrival_time or datetime.utcnow().isoformat(),
                "notes": notes,
            }
            if departure_time:
                payload["departure_time"] = departure_time

            response = await self.client.post("/detentions/", json=payload)
            if response.status_code in (200, 201):
                data = response.json()
                claim_id = data.get("id", "N/A")
                hours = data.get("detention_hours", 0)
                amount = data.get("total_claim_amount", 0)

                if departure_time:
                    return (
                        f"Detention claim {claim_id} has been filed. "
                        f"Detention time: {hours:.1f} hours. "
                        f"Estimated claim amount: ${amount:.2f}. "
                        f"We'll follow up with the broker."
                    )
                else:
                    return (
                        f"Detention claim {claim_id} has been started. "
                        f"Arrival logged at {facility_name}. "
                        f"We'll calculate the final detention time when you depart."
                    )
            return f"Could not create detention claim. Status: {response.status_code}"
        except Exception as e:
            return f"Unable to file detention claim. System error: {str(e)}"

    async def get_detention_rate(self, tenant_id: str = "") -> str:
        """Get the detention rate configuration."""
        return "Standard detention rate: $75/hour after 2 hours of free time."

    async def close(self):
        await self.client.aclose()
