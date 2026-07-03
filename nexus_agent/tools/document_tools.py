"""
Nexus Dispatch — Document Tools

Tools for sending rate confirmations, PODs, and BOLs via email.
"""

import structlog
import httpx

logger = structlog.get_logger()


class DocumentTools:
    """Tools for document management and delivery."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    async def send_rate_confirmation(self, booking_id: str, email: str) -> str:
        """Send a rate confirmation document to the specified email."""
        logger.info("Sending rate confirmation", booking_id=booking_id, email=email)
        try:
            # Create document record
            response = await self.client.post("/documents/", json={
                "doc_type": "rate_confirmation",
                "reference_id": booking_id,
                "sent_to_email": email,
            })
            if response.status_code in (200, 201):
                data = response.json()
                doc_id = data.get("id", "N/A")
                # Trigger send
                await self.client.post(f"/documents/{doc_id}/send?email={email}")
                return f"Rate confirmation for booking {booking_id} has been sent to {email}."
            return f"Could not generate rate confirmation. Please try again."
        except Exception as e:
            return f"Unable to send rate confirmation. System error: {str(e)}"

    async def send_pod(self, load_id: str, email: str) -> str:
        """Send a Proof of Delivery document."""
        logger.info("Sending POD", load_id=load_id, email=email)
        try:
            response = await self.client.post("/documents/", json={
                "doc_type": "pod",
                "reference_id": load_id,
                "sent_to_email": email,
            })
            if response.status_code in (200, 201):
                data = response.json()
                doc_id = data.get("id", "N/A")
                await self.client.post(f"/documents/{doc_id}/send?email={email}")
                return f"Proof of Delivery for load {load_id} has been sent to {email}."
            return f"Could not generate POD. The document may not be available yet."
        except Exception as e:
            return f"Unable to send POD. System error: {str(e)}"

    async def send_bol(self, load_id: str, email: str) -> str:
        """Send a Bill of Lading document."""
        logger.info("Sending BOL", load_id=load_id, email=email)
        try:
            response = await self.client.post("/documents/", json={
                "doc_type": "bol",
                "reference_id": load_id,
                "sent_to_email": email,
            })
            if response.status_code in (200, 201):
                data = response.json()
                doc_id = data.get("id", "N/A")
                await self.client.post(f"/documents/{doc_id}/send?email={email}")
                return f"Bill of Lading for load {load_id} has been sent to {email}."
            return f"Could not generate BOL. The document may not be available yet."
        except Exception as e:
            return f"Unable to send BOL. System error: {str(e)}"

    async def close(self):
        await self.client.aclose()
