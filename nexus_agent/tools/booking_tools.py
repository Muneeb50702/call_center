"""
Nexus Dispatch — Booking Tools

Tools for confirming bookings and dispatching rate confirmations.
These are used by the BookingAgent during the BOOKING phase.
"""

import httpx
import structlog
from typing import Optional

logger = structlog.get_logger()


class BookingTools:
    """
    Handles booking operations against the TMS backend.
    One instance per call, initialized with the tenant's TMS URL.
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
        )

    async def confirm_booking(
        self,
        load_id: str,
        driver_id: str,
        agreed_rate: float,
    ) -> str:
        """
        Create a booking in the TMS backend.
        Changes the load status from 'available' to 'booked'.
        """
        logger.info(
            "Confirming booking",
            load_id=load_id,
            driver_id=driver_id,
            agreed_rate=agreed_rate,
        )
        try:
            response = await self.client.post(
                "/bookings/",
                json={
                    "load_id": load_id,
                    "driver_id": driver_id,
                    "agreed_rate": agreed_rate,
                },
            )
            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                booking_id = data.get("id", "N/A")
                return (
                    f"Booking confirmed! Booking ID: {booking_id}. "
                    f"Load {load_id} is now booked for driver {driver_id} "
                    f"at ${agreed_rate}/mile. Rate confirmation will be sent shortly."
                )
            else:
                logger.error(
                    "Booking failed",
                    status=response.status_code,
                    body=response.text,
                )
                return f"Booking could not be completed right now. Try again in a moment."
        except httpx.TimeoutException:
            logger.error("Booking request timed out")
            return "The booking system is taking a moment. Hold on, let me try that one more time."
        except Exception as e:
            logger.exception("Booking error", error=str(e))
            return f"There was an issue confirming the booking. Please hold while I connect you with a dispatcher."

    async def send_rate_confirmation(
        self,
        booking_id: str,
        driver_email: Optional[str] = None,
    ) -> str:
        """
        Trigger sending a rate confirmation sheet to the driver.
        In production, this would email/fax the rate con.
        """
        logger.info(
            "Sending rate confirmation",
            booking_id=booking_id,
            driver_email=driver_email,
        )
        # Stub — in production this would integrate with an email/fax service
        if driver_email:
            return f"Rate confirmation for booking {booking_id} has been sent to {driver_email}."
        return f"Rate confirmation for booking {booking_id} will be sent to the driver's email on file."

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
