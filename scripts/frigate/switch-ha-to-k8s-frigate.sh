#!/bin/bash
#
# switch-ha-to-k8s-frigate.sh
#
# Switch Home Assistant Frigate integration from LXC to Kubernetes instance
# This script provides manual instructions and optional API-based switching
#

set -euo pipefail

# Load environment variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Cannot find .env file at $ENV_FILE"
    exit 1
fi

# Load HA credentials (extract specific variables to avoid syntax errors)
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2-)
HA_URL=$(grep "^HA_URL=" "$ENV_FILE" | cut -d'=' -f2-)

if [[ -z "$HA_TOKEN" ]] || [[ -z "$HA_URL" ]]; then
    echo "ERROR: HA_TOKEN or HA_URL not set in .env file"
    exit 1
fi

# Configuration
OLD_FRIGATE_URL="http://still-fawn.maas:5000"
NEW_FRIGATE_URL="http://frigate.app.homelab"
MQTT_CLIENT_ID="frigate-k8s"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================="
echo "Switch Home Assistant to K8s Frigate"
echo "========================================="
echo ""
echo -e "${YELLOW}IMPORTANT: This will switch your Frigate integration${NC}"
echo -e "${YELLOW}from the LXC instance to the Kubernetes instance${NC}"
echo ""
echo -e "Old Frigate: ${RED}$OLD_FRIGATE_URL${NC}"
echo -e "New Frigate: ${GREEN}$NEW_FRIGATE_URL${NC}"
echo ""

# Step 1: Verify new Frigate is healthy
echo "Step 1: Verifying new Frigate K8s instance..."
echo ""

if [[ -x "$SCRIPT_DIR/verify-frigate-k8s.sh" ]]; then
    if "$SCRIPT_DIR/verify-frigate-k8s.sh"; then
        echo ""
        echo -e "${GREEN}✓ Frigate K8s instance is healthy${NC}"
        echo ""
    else
        echo ""
        echo -e "${RED}✗ Frigate K8s instance verification failed${NC}"
        echo -e "${RED}Please resolve issues before proceeding${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠ verify-frigate-k8s.sh not found or not executable${NC}"
    echo "Skipping automatic verification - please verify manually"
    echo ""
fi

# Step 2: Manual instructions
echo "========================================="
echo "MANUAL SWITCH INSTRUCTIONS"
echo "========================================="
echo ""
echo "The Frigate integration URL must be changed manually in the Home Assistant UI."
echo "The Home Assistant API does not provide a way to update integration URLs."
echo ""
echo "Follow these steps:"
echo ""
echo -e "${BLUE}1. Remove old Frigate integration:${NC}"
echo "   - Open Home Assistant: $HA_URL"
echo "   - Go to: Settings → Devices & Services → Integrations"
echo "   - Find 'Frigate' integration"
echo "   - Click the three dots (⋮) → Delete"
echo "   - Confirm deletion"
echo ""
echo -e "${BLUE}2. Add new Frigate K8s integration:${NC}"
echo "   - Still in Settings → Devices & Services → Integrations"
echo "   - Click '+ ADD INTEGRATION'"
echo "   - Search for 'Frigate'"
echo "   - Enter the new URL: ${GREEN}$NEW_FRIGATE_URL${NC}"
echo "   - Complete the setup wizard"
echo ""
echo -e "${BLUE}3. Verify integration:${NC}"
echo "   - Check that Frigate cameras appear in Home Assistant"
echo "   - Verify camera entities (camera.old_ip_camera, etc.)"
echo "   - Check Frigate events are being received"
echo "   - Test face recognition notifications (if configured)"
echo ""
echo -e "${BLUE}4. Update automations (if needed):${NC}"
echo "   - Check automations using Frigate entities"
echo "   - Update any hardcoded entity IDs if they changed"
echo "   - Test automations to ensure they work"
echo ""
echo "========================================="
echo "POST-SWITCH VERIFICATION"
echo "========================================="
echo ""
echo "After switching, verify the following:"
echo ""
echo "1. Camera entities exist and show live feeds"
echo "2. Motion detection events are working"
echo "3. Face recognition is working (check notifications)"
echo "4. MQTT messages are being received (check with MQTT explorer)"
echo "5. Recordings are being stored properly"
echo ""
echo "You can check the integration status with:"
echo "  $SCRIPT_DIR/check-ha-frigate-integration.sh"
echo ""

# Optional: Offer to open HA in browser
echo "========================================="
echo "READY TO PROCEED?"
echo "========================================="
echo ""
read -p "Do you want to open Home Assistant in your browser now? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Opening Home Assistant..."
    open "$HA_URL/config/integrations" || {
        echo "Could not open browser automatically. Please navigate to:"
        echo "$HA_URL/config/integrations"
    }
    echo ""
fi

echo "========================================="
echo "ADDITIONAL NOTES"
echo "========================================="
echo ""
echo "After successful switch:"
echo "  - Monitor Frigate logs for any errors"
echo "  - Check Home Assistant logs for integration issues"
echo "  - Verify MQTT messages with correct client_id: $MQTT_CLIENT_ID"
echo ""
echo "To monitor Frigate K8s logs:"
echo "  kubectl --kubeconfig=~/kubeconfig logs -n frigate -l app=frigate -f"
echo ""
echo "If you need to rollback to LXC Frigate:"
echo "  1. Delete the K8s integration in HA"
echo "  2. Re-add the LXC integration with URL: $OLD_FRIGATE_URL"
echo "  3. Restart the LXC container if needed"
echo ""
