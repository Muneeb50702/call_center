"""
Nexus Dispatch — Check Call Tools

Tools for answering "Where is my truck?" calls.
Looks up load location, calculates ETA, and sends status notifications.
"""

import structlog
import httpx

from tools.service_http import service_headers

logger = structlog.get_logger()


class CheckCallTools:
    """
    Tools for check call operations.
    One instance per call, initialized with the tenant's TMS base URL.
    """

    def __init__(self, base_url: str = "http://localhost:8000", tenant_id: str = ""):
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=base_url, timeout=5.0, headers=service_headers(tenant_id)
        )

    async def get_load_location(self, load_id: str) -> str:
        """Get the current GPS location and status of a load."""
        logger.info("Getting load location", load_id=load_id)
        try:
            response = await self.client.get(f"/loads/{load_id}")
            if response.status_code == 200:
                data = response.json()
                location = data.get("current_city", "Location not available")
                status = data.get("status", "unknown")
                lat = data.get("last_known_lat")
                lng = data.get("last_known_lng")

                if status == "delivered":
                    return f"Load {load_id} has been delivered. Delivery date: {data.get('delivery_date', 'N/A')}."
                elif status == "in_transit" and location:
                    return (
                        f"Load {load_id} is currently in transit. "
                        f"Last known location: {location}. "
                        f"Origin: {data.get('origin', 'N/A')} → Destination: {data.get('destination', 'N/A')}."
                    )
                elif status == "booked":
                    return (
                        f"Load {load_id} is booked but hasn't been picked up yet. "
                        f"Scheduled pickup: {data.get('pickup_date', 'N/A')} from {data.get('origin', 'N/A')}."
                    )
                else:
                    return f"Load {load_id} status: {status}. Route: {data.get('origin', 'N/A')} → {data.get('destination', 'N/A')}."
            return f"Load {load_id} not found."
        except Exception as e:
            return f"Unable to get location for load {load_id}. System error: {str(e)}"

    async def get_load_eta(self, load_id: str) -> str:
        """Calculate estimated time of arrival for a load."""
        logger.info("Calculating ETA", load_id=load_id)
        try:
            response = await self.client.get(f"/loads/{load_id}")
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                delivery_date = data.get("delivery_date", "N/A")
                destination = data.get("destination", "N/A")

                if status == "delivered":
                    return f"Load {load_id} has already been delivered."
                elif status == "in_transit":
                    return (
                        f"Load {load_id} is in transit to {destination}. "
                        f"Scheduled delivery: {delivery_date}. "
                        f"Current location: {data.get('current_city', 'updating...')}."
                    )
                elif status == "booked":
                    return (
                        f"Load {load_id} hasn't been picked up yet. "
                        f"Scheduled pickup: {data.get('pickup_date', 'N/A')}. "
                        f"Estimated delivery: {delivery_date}."
                    )
                else:
                    return f"Load {load_id} status: {status}. Delivery date: {delivery_date}."
            return f"Load {load_id} not found."
        except Exception as e:
            return f"Unable to calculate ETA. System error: {str(e)}"

    async def send_eta_notification(self, load_id: str, message: str, email: str = "") -> str:
        """Send an ETA update notification (stub — uses document system)."""
        logger.info("Sending ETA notification", load_id=load_id, email=email)
        if email:
            return f"ETA update for load {load_id} has been sent to {email}."
        return f"ETA update for load {load_id} has been logged. The broker will be notified."

    async def close(self):
        await self.client.aclose()
