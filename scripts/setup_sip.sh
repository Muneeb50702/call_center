#!/bin/bash
# ==============================================================================
# Nexus Dispatch — SIP Setup Script
# ==============================================================================
# This script configures LiveKit to accept incoming SIP calls from Telnyx
# and dispatch them to the nexus-agent worker.
#
# Prerequisites:
#   1. LiveKit CLI installed: https://docs.livekit.io/cli/
#   2. LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET set in environment
#   3. Telnyx account with a phone number pointing to your LiveKit SIP URI
#
# Usage:
#   chmod +x scripts/setup_sip.sh
#   export LIVEKIT_URL=wss://your-project.livekit.cloud
#   export LIVEKIT_API_KEY=your_key
#   export LIVEKIT_API_SECRET=your_secret
#   ./scripts/setup_sip.sh
# ==============================================================================

set -euo pipefail

echo "🚀 Nexus Dispatch — SIP Configuration"
echo "======================================"

# Check prerequisites
if ! command -v lk &> /dev/null; then
    echo "❌ LiveKit CLI (lk) not found. Install from: https://docs.livekit.io/cli/"
    exit 1
fi

if [ -z "${LIVEKIT_URL:-}" ] || [ -z "${LIVEKIT_API_KEY:-}" ] || [ -z "${LIVEKIT_API_SECRET:-}" ]; then
    echo "❌ Missing environment variables. Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET"
    exit 1
fi

echo "✅ LiveKit CLI found"
echo "✅ LiveKit URL: ${LIVEKIT_URL}"

# ── Step 1: Create Inbound SIP Trunk ──
echo ""
echo "📞 Step 1: Creating SIP Inbound Trunk..."

TRUNK_CONFIG=$(cat <<EOF
{
  "trunk": {
    "name": "telnyx-nexus-inbound"
  }
}
EOF
)

echo "$TRUNK_CONFIG" | lk sip inbound create --request -
echo "✅ Inbound trunk created"

# ── Step 2: Create Dispatch Rule ──
echo ""
echo "🔀 Step 2: Creating SIP Dispatch Rule..."

DISPATCH_CONFIG=$(cat <<EOF
{
  "rule": {
    "dispatchRuleIndividual": {
      "roomPrefix": "dispatch-call"
    },
    "roomConfig": {
      "agents": [
        {
          "agentName": "nexus-agent"
        }
      ]
    }
  }
}
EOF
)

echo "$DISPATCH_CONFIG" | lk sip dispatch create --request -
echo "✅ Dispatch rule created"

# ── Step 3: Verify ──
echo ""
echo "🔍 Step 3: Verifying configuration..."
echo ""
echo "Inbound Trunks:"
lk sip inbound list
echo ""
echo "Dispatch Rules:"
lk sip dispatch list

echo ""
echo "======================================"
echo "✅ SIP Configuration Complete!"
echo ""
echo "Next steps:"
echo "  1. Go to your Telnyx dashboard"
echo "  2. Create a SIP Trunk pointing to: $(echo $LIVEKIT_URL | sed 's/wss:\/\//sip:/' | sed 's/.livekit.cloud/.sip.livekit.cloud/')"
echo "  3. Assign your phone number to the trunk"
echo "  4. Start the agent worker: docker compose up nexus-agent"
echo "  5. Call the phone number — the AI will answer!"
echo "======================================"
