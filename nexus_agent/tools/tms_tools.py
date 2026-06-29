import httpx
from livekit.agents import function_tool, RunContext
from config.settings import settings
import structlog

logger = structlog.get_logger()

class TMSTools:
    def __init__(self):
        self.base_url = settings.tms_base_url
        self.client = httpx.AsyncClient(base_url=self.base_url)

    @function_tool(description="Look up a specific freight load by its ID.")
    async def lookup_load(self, context: RunContext, load_id: str) -> str:
        """Look up a specific freight load by its ID."""
        logger.info("Looking up load", load_id=load_id)
        response = await self.client.get(f"/loads/{load_id}")
        if response.status_code == 200:
            return str(response.json())
        return "Load not found."

    @function_tool(description="Search for available freight loads by origin, destination, or equipment type.")
    async def search_loads(self, context: RunContext, origin: str = "", destination: str = "", equipment: str = "") -> str:
        """Search for available freight loads by origin, destination, or equipment type."""
        logger.info("Searching loads", origin=origin, destination=destination, equipment=equipment)
        params = {}
        if origin: params['origin'] = origin
        if destination: params['destination'] = destination
        if equipment: params['equipment'] = equipment
        response = await self.client.get("/loads/search", params=params)
        return str(response.json())

    @function_tool(description="Get the current base rate for a specific lane (e.g., 'IL-TX').")
    async def get_rate(self, context: RunContext, lane_id: str) -> str:
        """Get the current base rate for a specific lane."""
        logger.info("Getting rate", lane_id=lane_id)
        response = await self.client.get(f"/rates/{lane_id}")
        if response.status_code == 200:
            return str(response.json())
        return "Rate not found."

    @function_tool(description="Negotiate a rate for a lane by providing a counter-offer in USD per mile.")
    async def negotiate_rate(self, context: RunContext, lane_id: str, counter_offer: float) -> str:
        """Negotiate a rate for a lane by providing a counter-offer in USD per mile."""
        logger.info("Negotiating rate", lane_id=lane_id, counter_offer=counter_offer)
        response = await self.client.post("/rates/negotiate", json={"lane_id": lane_id, "counter_offer": counter_offer})
        if response.status_code == 200:
            return str(response.json())
        return "Negotiation failed."

    @function_tool(description="Check available drivers, optionally filtered by equipment type.")
    async def check_driver_availability(self, context: RunContext, equipment: str = "") -> str:
        """Check available drivers, optionally filtered by equipment type."""
        logger.info("Checking driver availability", equipment=equipment)
        params = {"equipment": equipment} if equipment else {}
        response = await self.client.get("/drivers/available", params=params)
        return str(response.json())
