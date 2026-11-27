#!/usr/bin/env bash
# Read only: verify Google Wi-Fi from the dual-connected host even when the
# operator's laptop is on another SSID. Inventory stays SOPS-encrypted.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/load-network.sh"
echo 'Laptop Wi-Fi address'
ipconfig getifaddr "${WIFI_INTERFACE:-en0}" || true
ssh -o Hostname="$PVE_ADDRESS" -o BatchMode=yes -o ConnectTimeout=8 \
  "root@$PVE_HOSTNAME" "bash -s -- $GOOGLE_GATEWAY_ADDRESS $IMMICH_HOSTNAME $RELAY_ADDRESS ${SECONDARY_DNS:-1.1.1.1}" <<'REMOTE'
set -euo pipefail
gateway=$1
hostname=$2
relay=$3
secondary=$4
echo 'Checking primary and independent public secondary'
[[ $(dig +time=3 +tries=1 +short @"$relay" "$hostname" A) == "$relay" ]]
public_answer=$(dig +time=3 +tries=1 +short @"$secondary" "$hostname" A)
[[ -n $public_answer ]]
[[ -n $(dig +time=3 +tries=1 +short @"$secondary" example.com A) ]]
echo 'Google Wi-Fi effective DNS answer (the status API need not be available)'
answer=$(dig +time=3 +tries=1 +short @"$gateway" "$hostname" A)
tcp_answer=$(dig +time=3 +tries=1 +tcp +short @"$gateway" "$hostname" A)
for response in "$answer" "$tcp_answer"; do
  [[ $response == "$relay" || $response == "$public_answer" ]] || { echo 'FAIL: unexpected Google Wi-Fi answer'; exit 1; }
done
[[ -n $(dig +time=3 +tries=1 +short @"$gateway" example.com A) ]]
if [[ $answer == "$relay" && $tcp_answer == "$relay" ]]; then
  echo 'Google Wi-Fi currently returns the local relay address over UDP and TCP.'
else
  echo 'Google Wi-Fi used a public Immich answer: ordinary DNS works; photos may be unavailable.'
fi
echo 'PASS: ordinary DNS works through Google Wi-Fi and the independent public secondary.'
echo 'Secondary configuration is owner-confirmed; this is not a forced outage test.'
echo 'Checking the relay locally with normal certificate validation'
curl --fail --connect-timeout 3 --max-time 15 -sS \
  --resolve "$hostname:443:$relay" "https://$hostname/api/server/ping"
echo
echo 'PASS: the HTTPS relay is healthy.'
echo 'The relay health check is local; a real album still needs browser confirmation.'
REMOTE
