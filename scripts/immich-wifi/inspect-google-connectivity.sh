#!/usr/bin/env bash
# Read-only targeted diagnostics when the configured Google Wi-Fi gateway is
# unreachable. No scanning or router configuration changes.
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/load-network.sh"
ssh -o Hostname="$PVE_ADDRESS" -o BatchMode=yes -o ConnectTimeout=8 \
  "root@$PVE_HOSTNAME" "bash -s -- $GOOGLE_GATEWAY_ADDRESS $GOOGLE_WAN_ADDRESS $IMMICH_HOSTNAME $RELAY_ADDRESS" <<'REMOTE'
set -u
ip -br -4 addr
ip -4 route
ip neigh show to "$1"
ip neigh show to "$2"
ip route get "$1"
ping -c 2 -W 2 "$1"
ping -c 2 -W 2 "$2"
systemctl is-active immich-wifi-firewall.service immich-wifi-proxy.service immich-wifi-dns.service
command -v dig
dig +time=2 +tries=1 @"$4" "$3" A
dig +time=2 +tries=1 @"$1" "$3" A
curl --connect-timeout 3 --max-time 10 -sS --resolve "$3:443:$4" "https://$3/api/server/ping"
echo
REMOTE
