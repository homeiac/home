#!/bin/bash
# Change the Ollama model used by HA conversation agent
# Usage: set-ha-model.sh <model_name>
#
# Examples:
#   set-ha-model.sh qwen2.5:3b    # switch to smaller/faster model
#   set-ha-model.sh qwen2.5:7b    # switch to larger model
#   set-ha-model.sh gemma3:4b     # switch to gemma
#
# Safety: Creates timestamped backup before any modification.
# The edit runs atomically inside the HA container via python3.
#
# IMPORTANT: The HA subentry reconfigure API is not available via REST,
# so this script edits the storage file via docker exec on HAOS.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${1:?Usage: $0 <model_name> (e.g., qwen2.5:3b)}"

PROXMOX_HOST="chief-horse.maas"
VMID=116
STORAGE_PATH="/config/.storage/core.config_entries"
DOCKER="docker exec homeassistant"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)

echo "Changing HA Ollama conversation model to: $MODEL"

# 1. Backup FIRST — atomic inside container, no piping
echo "Creating backup: ${STORAGE_PATH}.backup.${TIMESTAMP}"
ssh root@$PROXMOX_HOST "qm guest exec $VMID -- $DOCKER cp $STORAGE_PATH ${STORAGE_PATH}.backup.${TIMESTAMP}" 2>/dev/null
echo "Backup created."

# 2. Edit atomically inside the container using python3
# This avoids piping data through qm guest exec (which truncates files)
echo "Updating model inside container..."
RESULT=$(ssh root@$PROXMOX_HOST "qm guest exec $VMID -- $DOCKER python3 -c '
import json

path = \"$STORAGE_PATH\"
model = \"$MODEL\"

with open(path) as f:
    data = json.load(f)

changed = False
for entry in data.get(\"data\", {}).get(\"entries\", []):
    if entry.get(\"domain\") == \"ollama\":
        for sub in entry.get(\"subentries\", []):
            if sub.get(\"subentry_type\") == \"conversation\":
                old = sub[\"data\"].get(\"model\", \"unknown\")
                sub[\"data\"][\"model\"] = model
                changed = True
                print(f\"Changed: {old} -> {model}\")

if not changed:
    print(\"ERROR: Ollama conversation subentry not found\")
    exit(1)

with open(path, \"w\") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(\"File written successfully\")
'" 2>/dev/null)

echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('out-data','').strip()); exit(d.get('exitcode',1))" 2>/dev/null

if [[ $? -ne 0 ]]; then
    echo "ERROR: Edit failed. Restoring backup..."
    ssh root@$PROXMOX_HOST "qm guest exec $VMID -- $DOCKER cp ${STORAGE_PATH}.backup.${TIMESTAMP} $STORAGE_PATH" 2>/dev/null
    echo "Backup restored."
    exit 1
fi

# 3. Verify file is valid JSON
echo "Verifying file integrity..."
VERIFY=$(ssh root@$PROXMOX_HOST "qm guest exec $VMID -- $DOCKER python3 -c '
import json
with open(\"$STORAGE_PATH\") as f:
    data = json.load(f)
for e in data.get(\"data\",{}).get(\"entries\",[]):
    if e.get(\"domain\")==\"ollama\":
        for s in e.get(\"subentries\",[]):
            if s.get(\"subentry_type\")==\"conversation\":
                print(s[\"data\"][\"model\"])
'" 2>/dev/null)

VERIFIED_MODEL=$(echo "$VERIFY" | python3 -c "import json,sys; print(json.load(sys.stdin).get('out-data','').strip())" 2>/dev/null)

if [[ "$VERIFIED_MODEL" != "$MODEL" ]]; then
    echo "ERROR: Verification failed (got '$VERIFIED_MODEL'). Restoring backup..."
    ssh root@$PROXMOX_HOST "qm guest exec $VMID -- $DOCKER cp ${STORAGE_PATH}.backup.${TIMESTAMP} $STORAGE_PATH" 2>/dev/null
    echo "Backup restored."
    exit 1
fi

echo "Verified: model = $VERIFIED_MODEL"

# 4. Reload the integration via HA API
echo "Reloading Ollama integration..."
source "$SCRIPT_DIR/../lib-sh/ha-api.sh"

ENTRY_ID=$(ha_api_get "config/config_entries/entry" | \
    jq -r '.[] | select(.domain == "ollama") | .entry_id' | head -1)

ha_api_post "config/config_entries/entry/$ENTRY_ID/reload" '{}' >/dev/null 2>&1

sleep 2
STATE=$(ha_api_get "config/config_entries/entry" | \
    jq -r ".[] | select(.entry_id == \"$ENTRY_ID\") | .state")
echo "Integration state: $STATE"
echo "Done."
