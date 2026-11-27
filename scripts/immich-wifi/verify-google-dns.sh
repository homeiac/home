#!/usr/bin/env bash
# Read only: verify Google Wi-Fi from the dual-connected host even when the
# operator's laptop is on another SSID. Inventory stays SOPS-encrypted.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/load-network.sh"
echo 'Laptop Wi-Fi address'
ipconfig getifaddr "${WIFI_INTERFACE:-en0}" || true
ssh -o Hostname="$PVE_ADDRESS" -o BatchMode=yes -o ConnectTimeout=8 \
  "root@$PVE_HOSTNAME" "bash -s -- $GOOGLE_GATEWAY_ADDRESS $IMMICH_HOSTNAME $RELAY_ADDRESS $GOOGLE_WAN_ADDRESS $WAN_INTERFACE" <<'REMOTE'
set -euo pipefail
gateway=$1
hostname=$2
relay=$3
echo 'Google Wi-Fi effective DNS answer (the status API need not be available)'
answer=$(dig +time=3 +tries=1 +short @"$gateway" "$hostname" A)
[[ $answer == "$relay" ]] || { echo 'FAIL: Google Wi-Fi does not return the relay address'; exit 1; }
[[ $(dig +time=3 +tries=1 +tcp +short @"$gateway" "$hostname" A) == "$relay" ]]
[[ -n $(dig +time=3 +tries=1 +short @"$gateway" example.com A) ]]
echo 'PASS: Google Wi-Fi returns the relay address.'
echo 'Checking the relay locally with normal certificate validation'
curl --fail --connect-timeout 3 --max-time 15 -sS \
  --resolve "$hostname:443:$answer" "https://$hostname/api/server/ping"
echo
echo 'PASS: Google Wi-Fi DNS adopted the override and the HTTPS relay is healthy.'
echo 'The relay health check is local; a real album still needs browser confirmation.'
REMOTE
