"""
Nexus Dispatch — Onboarding Tools

Tools for registering new drivers/carriers into the system.
"""

import re
import structlog
import httpx

logger = structlog.get_logger()


class OnboardingTools:
    """Tools for driver onboarding operations."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=5.0)

    async def validate_mc_number(self, mc_number: str) -> str:
        """Validate MC number format (e.g., MC123456)."""
        # MC numbers: MC followed by 4-8 digits
        pattern = r'^MC\d{4,8}$'
        clean = mc_number.strip().upper().replace(" ", "").replace("-", "")

        if re.match(pattern, clean):
            return f"MC number {clean} format is valid."
        else:
            return (
                f"'{mc_number}' doesn't look like a valid MC number. "
                f"MC numbers start with 'MC' followed by 4-8 digits (e.g., MC123456). "
                f"Please ask the caller to confirm."
            )

    async def check_duplicate_driver(self, mc_number: str) -> str:
        """Check if a driver with this MC number is already registered."""
        logger.info("Checking for duplicate driver", mc_number=mc_number)
        try:
            response = await self.client.get(
                "/drivers/by-mc",
                params={"mc_number": mc_number},
            )
            if response.status_code == 200:
                data = response.json()
                return (
                    f"A driver with MC number {mc_number} is already registered: "
                    f"{data.get('name', 'N/A')} (Driver ID: {data.get('id', 'N/A')}). "
                    f"They don't need to register again."
                )
            return f"No existing driver found with MC number {mc_number}. Proceed with registration."
        except Exception as e:
            return f"Unable to check for duplicates. Proceed with registration and we'll verify later."

    async def register_driver(
        self,
        mc_number: str,
        name: str,
        equipment: str,
        phone: str = "",
        email: str = "",
        dot_number: str = "",
    ) -> str:
        """Register a new driver in the system."""
        logger.info("Registering new driver", mc_number=mc_number, name=name, equipment=equipment)
        try:
            response = await self.client.post("/drivers/", json={
                "mc_number": mc_number.strip().upper(),
                "name": name,
                "equipment": equipment,
                "hos_status": "available",
                "phone": phone,
                "email": email,
                "dot_number": dot_number,
            })
            if response.status_code in (200, 201):
                data = response.json()
                driver_id = data.get("id", "N/A")
                return (
                    f"Welcome aboard! Driver registered successfully. "
                    f"Driver ID: {driver_id}. "
                    f"Name: {name}. MC: {mc_number}. Equipment: {equipment}. "
                    f"You can now search for available loads."
                )
            elif response.status_code == 409:
                return f"A driver with MC number {mc_number} is already registered. No need to register again."
            return f"Registration failed. Status: {response.status_code}. Please try again."
        except Exception as e:
            return f"Unable to register driver. System error: {str(e)}"

    async def close(self):
        await self.client.aclose()
