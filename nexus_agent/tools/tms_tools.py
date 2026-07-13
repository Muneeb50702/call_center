"""
Nexus Dispatch — TMS Tools (Transportation Management System)

Async HTTP client for interacting with the TMS backend.
Includes retry logic with exponential backoff and request timeouts
to prevent blocking the voice pipeline.

These tools are now called directly by the Agent subclasses in state/agents.py
rather than through @function_tool decorators (the agents wrap them).
"""

import asyncio
import httpx
import structlog

from tools.service_http import service_headers

logger = structlog.get_logger()

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 0.3  # seconds
REQUEST_TIMEOUT = 5.0  # seconds — never block the voice pipeline longer than this


class TMSTools:
    """
    HTTP client for the TMS backend API.
    One instance per call, initialized with the tenant's TMS base URL.
    """

    def __init__(self, base_url: str = "http://localhost:8000", tenant_id: str = ""):
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=REQUEST_TIMEOUT,
            headers=service_headers(tenant_id),
        )

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_data: dict | None = None,
    ) -> httpx.Response:
        """
        Execute an HTTP request with exponential backoff retry.
        Retries on network errors and 5xx server errors.
        """
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                if method == "GET":
                    response = await self.client.get(path, params=params)
                elif method == "POST":
                    response = await self.client.post(path, json=json_data)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                # Retry on server errors (5xx)
                if response.status_code >= 500:
                    logger.warning(
                        "TMS server error, retrying",
                        path=path,
                        status=response.status_code,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                    continue

                return response

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                last_error = e
                logger.warning(
                    "TMS request failed, retrying",
                    path=path,
                    error=str(e),
                    attempt=attempt + 1,
                    max_retries=MAX_RETRIES,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

        # All retries exhausted
        logger.error(
            "TMS request failed after all retries",
            path=path,
            error=str(last_error),
        )
        raise last_error

    async def lookup_load(self, load_id: str) -> str:
        """Look up a specific freight load by its ID."""
        logger.info("Looking up load", load_id=load_id)
        try:
            response = await self._request_with_retry("GET", f"/loads/{load_id}")
            if response.status_code == 200:
                return str(response.json())
            return f"No load found with ID {load_id}. Ask the caller to verify the load number."
        except Exception as e:
            return f"Load lookup is temporarily slow. Try again in a moment. (Internal: {str(e)})"

    async def search_loads(
        self,
        origin: str = "",
        destination: str = "",
        equipment: str = "",
    ) -> str:
        """Search for available freight loads by origin, destination, or equipment type."""
        logger.info("Searching loads", origin=origin, destination=destination, equipment=equipment)
        params = {}
        if origin:
            params["origin"] = origin
        if destination:
            params["destination"] = destination
        if equipment:
            params["equipment"] = equipment
        try:
            response = await self._request_with_retry("GET", "/loads/search", params=params)
            data = response.json()
            if not data:
                return "No loads found matching those criteria right now. Ask the caller if they'd be open to nearby cities or a different equipment type."
            return str(data)
        except Exception as e:
            return f"Load search is temporarily slow. Try the search again. (Internal: {str(e)})"

    async def get_rate(self, lane_id: str) -> str:
        """Get the current base rate for a specific lane."""
        logger.info("Getting rate", lane_id=lane_id)
        try:
            response = await self._request_with_retry("GET", f"/rates/{lane_id}")
            if response.status_code == 200:
                return str(response.json())
            return f"Rate not available for lane {lane_id} at the moment. Try again."
        except Exception as e:
            return f"Rate lookup is temporarily slow. Try again in a moment. (Internal: {str(e)})"

    async def negotiate_rate(self, lane_id: str, counter_offer: float) -> str:
        """Negotiate a rate for a lane by providing a counter-offer in USD per mile."""
        logger.info("Negotiating rate", lane_id=lane_id, counter_offer=counter_offer)
        try:
            response = await self._request_with_retry(
                "POST",
                "/rates/negotiate",
                json_data={"lane_id": lane_id, "counter_offer": counter_offer},
            )
            if response.status_code == 200:
                return str(response.json())
            return "The system couldn't process that offer right now. Try submitting the offer again."
        except Exception as e:
            return f"Negotiation system is temporarily slow. Try again. (Internal: {str(e)})"

    async def check_driver_availability(self, equipment: str = "") -> str:
        """Check available drivers, optionally filtered by equipment type."""
        logger.info("Checking driver availability", equipment=equipment)
        params = {"equipment": equipment} if equipment else {}
        try:
            response = await self._request_with_retry("GET", "/drivers/available", params=params)
            data = response.json()
            if not data:
                return "No available drivers found for that equipment type right now."
            return str(data)
        except Exception as e:
            return f"Driver availability check is temporarily slow. Try again. (Internal: {str(e)})"

    async def lookup_driver_by_mc(self, mc_number: str) -> str:
        """Look up a driver's details using their MC number."""
        logger.info("Looking up driver by MC", mc_number=mc_number)
        try:
            response = await self._request_with_retry(
                "GET",
                "/drivers/by-mc",
                params={"mc_number": mc_number},
            )
            if response.status_code == 200:
                return str(response.json())
            return f"MC number {mc_number} not found in our system. Ask the caller to spell it out or provide their name instead."
        except Exception as e:
            return f"Driver lookup is temporarily slow. Try again. (Internal: {str(e)})"

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
