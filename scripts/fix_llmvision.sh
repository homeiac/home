#!/usr/bin/env bash
# Automated LLM-Vision fix script
# Usage: scripts/fix_llmvision.sh --host HOST [--ssh-port PORT]

set -euo pipefail

# Load HA URL/token from proxmox/homelab .env
ENV_FILE="$(git rev-parse --show-toplevel)/proxmox/homelab/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env not found at $ENV_FILE" >&2
  exit 1
fi
export $(grep '^HOME_ASSISTANT_URL=' "$ENV_FILE")
export $(grep '^HOME_ASSISTANT_TOKEN=' "$ENV_FILE")

SSH_PORT=22222
HOST=""

usage() {
  cat <<EOF
Usage: $0 --host HOST [--ssh-port PORT]
Example: $0 --host homeassistant.maas --ssh-port 22222
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"; shift 2;;
    --ssh-port)
      SSH_PORT="$2"; shift 2;;
    *) usage;;
  esac
done

if [[ -z "$HOST" ]]; then
  usage
fi

echo "[1/5] Backing up blueprint file on $HOST..."
ssh -p "$SSH_PORT" root@"$HOST" \
  'cp /mnt/data/supervisor/homeassistant/blueprints/automation/valentinfrlch/event_summary.yaml \
      /mnt/data/supervisor/homeassistant/blueprints/automation/valentinfrlch/event_summary.yaml.backup.$(date +%s)'

echo "[2/5] Patching blueprint file..."
ssh -p "$SSH_PORT" root@"$HOST" \
  'sed -i "s|camera: .*camera_entities_list\[0\].*|camera: '\''{{ camera_entity.replace(\"camera.\",\"\").replace(\"_\",\" \") | title }}'\''|; \
             s|camera_entity_snapshot:.*camera_entities_list\[0\]|camera_entity_snapshot: '\''{{ camera_entity }}'\''|" \
     /mnt/data/supervisor/homeassistant/blueprints/automation/valentinfrlch/event_summary.yaml'

echo "[3/5] Validating YAML and reloading automation..."
ssh -p "$SSH_PORT" root@"$HOST" \
  'ha core check && ha core reload && ha automation reload'

echo "[4/5] Backing up and patching custom component file..."
ssh -p "$SSH_PORT" root@"$HOST" \
  'cp /mnt/data/supervisor/homeassistant/custom_components/llmvision/__init__.py \
      /mnt/data/supervisor/homeassistant/custom_components/llmvision/__init__.py.backup.$(date +%s)'
ssh -p "$SSH_PORT" root@"$HOST" \
  'sed -i "/^class ServiceCallData/,/^$/ { /self.image_entities =/c\\
      # Ensure a lone image_entity string is wrapped as a list\\
      _img = data_call.data.get(IMAGE_ENTITY)\\
      self.image_entities = [_img] if isinstance(_img, str) else (_img or [])\\
  }" \
     /mnt/data/supervisor/homeassistant/custom_components/llmvision/__init__.py'

echo "[5/5] Restarting Home Assistant core..."
ssh -p "$SSH_PORT" root@"$HOST" 'ha core restart'

echo "✅ Patch complete. Now test via curl to ensure correct camera mapping:" \
"curl -s -X POST \"${HOME_ASSISTANT_URL}/api/services/llmvision/stream_analyzer?return_response=true\" \
  -H \"Authorization: Bearer ${HOME_ASSISTANT_TOKEN}\" \
  -H \"Content-Type: application/json\" \
  -d '{"motion_entity":"binary_sensor.motion_hall","provider":"ollama","image_entities":["camera.hallway"]}' | jq ."
