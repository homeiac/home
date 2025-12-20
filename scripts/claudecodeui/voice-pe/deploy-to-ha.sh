#!/bin/bash
# Deploy voice approval to HA
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HA_CONFIG="/mnt/data/supervisor/homeassistant"
PROXMOX_HOST="root@chief-horse.maas"
VMID=116
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

ha_exec() {
    ssh "$PROXMOX_HOST" "qm guest exec $VMID -- $*" 2>/dev/null | jq -r '.["out-data"] // .exitcode'
}

ha_write() {
    local dest="$1"
    ssh "$PROXMOX_HOST" "qm guest exec $VMID -- tee $dest" 2>/dev/null | jq -r '.exitcode'
}

echo "=== Deploying Voice Approval to HA ==="
echo ""

# Step 1: Backup
echo "1. Backing up HA config..."
ha_exec "cp $HA_CONFIG/configuration.yaml $HA_CONFIG/configuration.yaml.backup-$TIMESTAMP"
ha_exec "cp $HA_CONFIG/automations.yaml $HA_CONFIG/automations.yaml.backup-$TIMESTAMP"
echo "   Backed up to *.backup-$TIMESTAMP"

# Step 2: Create custom_sentences dir
echo "2. Creating custom_sentences directory..."
ha_exec "mkdir -p $HA_CONFIG/custom_sentences/en"

# Step 3: Deploy custom_sentences
echo "3. Deploying voice_approval.yaml..."
cat "$SCRIPT_DIR/custom_sentences/en/voice_approval.yaml" | ha_write "$HA_CONFIG/custom_sentences/en/voice_approval.yaml"

# Step 4: Deploy intent_script
echo "4. Deploying intent_script.yaml..."
cat "$SCRIPT_DIR/intent_scripts/voice_approval.yaml" | ha_write "$HA_CONFIG/intent_script.yaml"

# Step 5: Check if intent_script already in configuration.yaml
echo "5. Checking configuration.yaml..."
if ha_exec "grep -q 'intent_script:' $HA_CONFIG/configuration.yaml"; then
    echo "   intent_script already configured"
else
    echo "   Adding intent_script include..."
    ha_exec "echo 'intent_script: !include intent_script.yaml' >> $HA_CONFIG/configuration.yaml"
fi

# Step 6: Verify
echo "6. Verifying deployment..."
echo "   custom_sentences/en/voice_approval.yaml:"
ha_exec "head -5 $HA_CONFIG/custom_sentences/en/voice_approval.yaml"
echo ""
echo "   intent_script.yaml:"
ha_exec "head -5 $HA_CONFIG/intent_script.yaml"

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Next: Update approval-request automation to use assist_satellite.start_conversation"
echo "Then: Restart HA to apply changes"
