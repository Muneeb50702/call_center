import os
import structlog
import httpx
from typing import Optional

logger = structlog.get_logger()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send transactional emails using Resend."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set. Email not sent.", to=to_email, subject=subject)
        return False
        
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": "Nexus Dispatch <noreply@nexusdispatch.ai>",
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body
                }
            )
            response.raise_for_status()
            logger.info("Email sent successfully", to=to_email, subject=subject)
            return True
    except Exception as e:
        logger.error("Failed to send email", to=to_email, error=str(e))
        return False

async def send_detention_alert(tenant_email: str, driver_name: str, facility: str, duration: str):
    """Send an alert to a tenant about a new detention claim."""
    subject = f"Action Required: New Detention Claim at {facility}"
    html = f"""
    <h2>Detention Claim Alert</h2>
    <p>Driver <strong>{driver_name}</strong> has reported being detained at <strong>{facility}</strong> for {duration}.</p>
    <p>The AI dispatcher has gathered the preliminary information and instructed the driver to secure a signed BOL.</p>
    <p><a href="https://app.nexusdispatch.ai/history">View Call Details in Dashboard</a></p>
    """
    await send_email(tenant_email, subject, html)
