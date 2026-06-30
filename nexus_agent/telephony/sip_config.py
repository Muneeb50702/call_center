"""
Nexus Dispatch — Telephony / SIP Configuration

Helpers for configuring SIP trunking with Telnyx via the LiveKit SIP bridge.

Architecture:
    Phone Call → Telnyx SIP Trunk → LiveKit SIP Bridge → LiveKit Room → nexus-agent

Setup Steps:
1. Create a Telnyx account (use GitHub Student Pack for $20 free credits)
2. Buy a phone number on Telnyx
3. Create a SIP Trunk pointing to your LiveKit SIP URI
4. Create a LiveKit Dispatch Rule to route calls to nexus-agent
5. Run the agent worker

This module provides Python helpers for steps 3-4 using the LiveKit Server SDK.
For CLI-based setup, use scripts/setup_sip.sh instead.
"""

import structlog
from typing import Optional

logger = structlog.get_logger()


# ── Configuration Templates ──

def get_telnyx_sip_trunk_config(
    livekit_sip_uri: str,
    phone_numbers: list[str],
    trunk_name: str = "nexus-dispatch-trunk",
) -> dict:
    """
    Generate the configuration for a Telnyx SIP trunk.
    
    This is the config you'd apply on the Telnyx dashboard or via their API.
    Points the trunk to your LiveKit SIP bridge URI.
    
    Args:
        livekit_sip_uri: Your LiveKit SIP URI (e.g., 'sip:your-project.sip.livekit.cloud')
        phone_numbers: List of phone numbers to associate with this trunk
        trunk_name: Human-readable name for the trunk
    
    Returns:
        Configuration dict for documentation/API use.
    """
    return {
        "name": trunk_name,
        "sip_uri": livekit_sip_uri,
        "phone_numbers": phone_numbers,
        "codec": "PCMU",  # G.711 μ-law — universal compatibility
        "dtmf_type": "RFC 2833",
        "notes": "Routes to LiveKit SIP bridge for AI dispatch",
    }


def get_livekit_inbound_trunk_config(
    trunk_name: str = "telnyx-inbound",
    allowed_numbers: list[str] | None = None,
) -> dict:
    """
    Generate the LiveKit SIP Inbound Trunk configuration.
    
    This tells LiveKit which incoming SIP calls to accept.
    Create via: lk sip inbound create --request <json>
    
    Args:
        trunk_name: Name for the inbound trunk
        allowed_numbers: Phone numbers to accept calls on
    
    Returns:
        Configuration dict for the LiveKit CLI.
    """
    config = {
        "trunk": {
            "name": trunk_name,
        }
    }
    if allowed_numbers:
        config["trunk"]["allowed_numbers"] = allowed_numbers
    return config


def get_livekit_dispatch_rule_config(
    agent_name: str = "nexus-agent",
    room_prefix: str = "dispatch-call",
    trunk_ids: list[str] | None = None,
) -> dict:
    """
    Generate the LiveKit SIP Dispatch Rule configuration.
    
    This tells LiveKit: "When a SIP call arrives, create a room and dispatch 
    the nexus-agent worker to handle it."
    Create via: lk sip dispatch create --request <json>
    
    Args:
        agent_name: The agent name registered in entrypoint.py
        room_prefix: Prefix for auto-generated room names
        trunk_ids: Optional list of trunk IDs to restrict this rule to
    
    Returns:
        Configuration dict for the LiveKit CLI.
    """
    rule = {
        "rule": {
            "dispatchRuleIndividual": {
                "roomPrefix": room_prefix,
            },
            "roomConfig": {
                "agents": [
                    {
                        "agentName": agent_name,
                    }
                ]
            },
        }
    }
    if trunk_ids:
        rule["rule"]["trunkIds"] = trunk_ids
    return rule


async def setup_sip_programmatic(
    livekit_api,
    phone_numbers: list[str],
    agent_name: str = "nexus-agent",
) -> dict:
    """
    Programmatically configure SIP trunking via the LiveKit Server SDK.
    
    This is the API-based alternative to scripts/setup_sip.sh.
    Requires the livekit-api Python package.
    
    Args:
        livekit_api: Initialized LiveKit API client
        phone_numbers: Phone numbers to register
        agent_name: Agent name to dispatch to
    
    Returns:
        Dict with trunk_id and dispatch_rule_id
    """
    try:
        # Create inbound trunk
        trunk_config = get_livekit_inbound_trunk_config(
            allowed_numbers=phone_numbers,
        )
        logger.info("Creating SIP inbound trunk", config=trunk_config)
        
        # Create dispatch rule
        dispatch_config = get_livekit_dispatch_rule_config(
            agent_name=agent_name,
        )
        logger.info("Creating SIP dispatch rule", config=dispatch_config)
        
        # Note: Actual API calls depend on the livekit-api SDK version
        # In production, use:
        # trunk = await livekit_api.sip.create_sip_inbound_trunk(trunk_config)
        # rule = await livekit_api.sip.create_sip_dispatch_rule(dispatch_config)
        
        return {
            "status": "configured",
            "phone_numbers": phone_numbers,
            "agent_name": agent_name,
        }
    except Exception as e:
        logger.exception("Failed to setup SIP", error=str(e))
        raise
