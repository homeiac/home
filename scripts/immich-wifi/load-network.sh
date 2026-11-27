#!/usr/bin/env bash
# Source this helper. Decrypt settings into this process only; never print them.
set -euo pipefail
IMMICH_WIFI_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
settings_file="$IMMICH_WIFI_ROOT/gitops/clusters/homelab/apps/photo-enrichment/immich-wifi/network.sops.yaml"
export SOPS_AGE_KEY_FILE="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
network_env=$(sops --decrypt --output-type json "$settings_file" | python3 -c 'import json,sys; print(json.load(sys.stdin)["stringData"]["network.env"])')
eval "$network_env"
unset network_env
