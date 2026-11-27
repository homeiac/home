#!/usr/bin/env bash
# Scope access to the observed Google Wi-Fi WAN IP and PVE's own health checks.
# Only the new listeners are affected; never flush global firewall rules.
set -euo pipefail
set -a
. "$(dirname "${BASH_SOURCE[0]}")/network.env"
set +a
chain=IMMICH_WIFI
remove_jumps() {
  for protocol in tcp udp; do
    ports=53
    [[ $protocol == tcp ]] && ports=53,443
    while iptables -w -C INPUT -d ${RELAY_ADDRESS} -p "$protocol" -m multiport --dports "$ports" -j "$chain" 2>/dev/null; do
      iptables -w -D INPUT -d ${RELAY_ADDRESS} -p "$protocol" -m multiport --dports "$ports" -j "$chain"
    done
  done
}
case "${1:-apply}" in
  apply)
    # Populate a new chain before attaching it. Existing chains are verified,
    # then replaced under an explicit reject rule so updates never fail open.
    iptables -w -N "$chain" 2>/dev/null || true
    iptables -w -I "$chain" 1 -j REJECT
    while [[ $(iptables -w -S "$chain" | wc -l) -gt 2 ]]; do
      iptables -w -D "$chain" 2
    done
    iptables -w -A "$chain" -s ${GOOGLE_WAN_ADDRESS}/32 -j ACCEPT
    iptables -w -A "$chain" -s ${RELAY_ADDRESS}/32 -j ACCEPT
    iptables -w -A "$chain" -j REJECT
    iptables -w -D "$chain" 1
    for protocol in tcp udp; do
      ports=53
      [[ $protocol == tcp ]] && ports=53,443
      iptables -w -C INPUT -d ${RELAY_ADDRESS} -p "$protocol" -m multiport --dports "$ports" -j "$chain" 2>/dev/null ||
        iptables -w -I INPUT 1 -d ${RELAY_ADDRESS} -p "$protocol" -m multiport --dports "$ports" -j "$chain"
    done
    ;;
  remove)
    remove_jumps
    if iptables -w -S "$chain" >/dev/null 2>&1; then
      iptables -w -F "$chain"
      iptables -w -X "$chain"
    fi
    ;;
  *) echo 'Expected apply or remove' >&2; exit 2 ;;
esac
