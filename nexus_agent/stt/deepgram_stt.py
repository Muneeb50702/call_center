"""
Nexus Dispatch — Deepgram STT (Speech-to-Text)

Optimized for freight dispatch conversations in noisy truck cab environments.
Nova-3 with custom logistics vocabulary boosting ensures high accuracy
for industry jargon over diesel engine noise.
"""

from livekit.plugins import deepgram


# Core logistics vocabulary — boosted for recognition priority
# Weight scale: 1 (slight boost) to 5 (maximum priority)
LOGISTICS_KEYWORDS = [
    # Equipment types
    "reefer:5",
    "flatbed:5",
    "dry van:5",
    "bobtail:4",
    "step deck:4",
    "lowboy:4",
    "tanker:4",
    "box truck:4",
    "hot shot:4",
    "conestoga:3",
    "curtain side:3",
    # Documents & paperwork
    "BOL:5",          # Bill of Lading
    "POD:5",          # Proof of Delivery
    "rate con:5",     # Rate Confirmation
    "rate confirmation:5",
    "lumper receipt:4",
    "freight bill:4",
    # Operations & logistics terms
    "deadhead:5",
    "detention:5",
    "TONU:5",         # Truck Ordered Not Used
    "drayage:4",
    "drop and hook:4",
    "live load:4",
    "live unload:4",
    "backhaul:4",
    "relay:3",
    "team driver:3",
    "solo driver:3",
    # Shipping modes
    "LTL:5",          # Less Than Truckload
    "FTL:5",          # Full Truckload
    "partial:4",
    # Identifiers
    "MC number:5",
    "DOT number:5",
    "PRO number:4",
    "SCAC code:3",
    # Weight & dimensions
    "gross weight:3",
    "payload:3",
    "cube out:3",
    "weight out:3",
    # Industry organizations
    "FMCSA:4",
    "broker:4",
    "shipper:4",
    "consignee:4",
    "dispatcher:5",
    # Common route references
    "per mile:5",
    "all in:4",
    "line haul:4",
    "fuel surcharge:4",
    "accessorial:3",
    # Hours of Service
    "HOS:5",
    "ELD:4",          # Electronic Logging Device
    "drive time:4",
    "on duty:4",
    "off duty:4",
    "sleeper berth:3",
]


def create_stt(
    extra_keywords: list[str] | None = None,
) -> deepgram.STT:
    """
    Creates a Deepgram STT instance optimized for freight dispatch voice AI.
    
    Args:
        extra_keywords: Additional tenant-specific keywords to boost.
    
    Returns:
        Configured Deepgram STT instance.
    """
    all_keywords = LOGISTICS_KEYWORDS.copy()
    if extra_keywords:
        # Add tenant-specific keywords with default boost
        for kw in extra_keywords:
            if ":" not in kw:
                kw = f"{kw}:4"
            all_keywords.append(kw)

    return deepgram.STT(
        model="nova-3",
        language="en-US",
        smart_format=True,
        filler_words=False,
        keywords=all_keywords,
    )
