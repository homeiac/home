#!/bin/bash
# fix-pbs-network.sh - Recover PBS (LXC 103 on pumped-piglet) from a lost IPv4
# DHCP lease and install a watchdog so it self-heals next time.
#
# Symptom (vzdump task log on any node):
#   TASK ERROR: could not activate storage 'homelab-backup': homelab-backup:
#   error fetching datastores - 500 Can't connect to 192.168.4.211:8007
#   (No route to host)
#
# Root cause: after a power cut, PBS boots before the MAAS DHCP server
# (VM 102 on pve, 192.168.4.53) is serving. ifupdown's dhclient tries for
# ~60s, gives up, and never retries -> container is IPv6-only forever.
# See docs/blog/2026-11-15-pbs-no-route-to-host-after-power-cut.md
#
# Usage (run from your workstation):
#   scripts/backup/fix-pbs-network.sh            # repair + install watchdog
#   scripts/backup/fix-pbs-network.sh --check    # read-only status
#
# Idempotent: safe to run any time.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_DIR="$SCRIPT_DIR/pbs-dhcp-watchdog"

PBS_HOST="root@pumped-piglet.maas"
PBS_CTID=103
PBS_IP="192.168.4.211"
PBS_PORT=8007
STORAGE="homelab-backup"
SSH="ssh -o ConnectTimeout=10 -o BatchMode=yes"

MODE="fix"
[[ "${1:-}" == "--check" ]] && MODE="check"

log() { echo "[$(date +%H:%M:%S)] $*"; }

ct() { $SSH "$PBS_HOST" "pct exec $PBS_CTID -- $*"; }

ct_ipv4() { ct "ip -4 -o addr show dev eth0" | awk '{print $4}' | head -1; }

status() {
    log "Container status: $($SSH "$PBS_HOST" "pct status $PBS_CTID")"
    local ip; ip="$(ct_ipv4 || true)"
    log "Container IPv4 on eth0: ${ip:-<none>}"
    log "Watchdog timer: $(ct "systemctl is-active dhcp-ipv4-watchdog.timer" 2>/dev/null || true)"
    if $SSH "$PBS_HOST" "timeout 5 bash -c '</dev/tcp/$PBS_IP/$PBS_PORT'" 2>/dev/null; then
        log "PBS API $PBS_IP:$PBS_PORT reachable from pumped-piglet: yes"
    else
        log "PBS API $PBS_IP:$PBS_PORT reachable from pumped-piglet: NO"
    fi
    log "Storage '$STORAGE' on pumped-piglet:"
    $SSH "$PBS_HOST" "pvesm status --storage $STORAGE 2>&1" | sed 's/^/    /'
}

repair_lease() {
    if [[ -n "$(ct_ipv4 || true)" ]]; then
        log "IPv4 already present - no lease repair needed"
        return
    fi
    log "No IPv4 - checking MAAS DHCP server is up first"
    if ! ping -c1 -W2 192.168.4.53 >/dev/null 2>&1; then
        log "WARNING: MAAS (192.168.4.53) not answering ping; DHCP may still fail"
    fi
    log "Requesting DHCP lease inside CT $PBS_CTID"
    ct "/sbin/dhclient -1 -v -pf /run/dhclient.eth0.pid -lf /var/lib/dhcp/dhclient.eth0.leases eth0" 2>&1 | grep -E 'DHCP|bound' | sed 's/^/    /' || true
    local ip; ip="$(ct_ipv4 || true)"
    [[ -z "$ip" ]] && { log "ERROR: still no IPv4 after dhclient"; exit 1; }
    log "Got IPv4: $ip"
    if [[ "${ip%/*}" != "$PBS_IP" ]]; then
        log "WARNING: got ${ip%/*}, storage.cfg expects $PBS_IP - check MAAS reservation"
    fi
}

install_watchdog() {
    log "Installing dhcp-ipv4-watchdog (systemd timer) into CT $PBS_CTID"
    local tmp=/tmp/pbs-dhcp-watchdog.$$
    $SSH "$PBS_HOST" "mkdir -p $tmp"
    scp -q -o ConnectTimeout=10 "$WATCHDOG_DIR"/* "$PBS_HOST:$tmp/"
    $SSH "$PBS_HOST" "set -e
        pct push $PBS_CTID $tmp/dhcp-ipv4-watchdog.sh /usr/local/sbin/dhcp-ipv4-watchdog.sh --perms 0755
        pct push $PBS_CTID $tmp/dhcp-ipv4-watchdog.service /etc/systemd/system/dhcp-ipv4-watchdog.service --perms 0644
        pct push $PBS_CTID $tmp/dhcp-ipv4-watchdog.timer /etc/systemd/system/dhcp-ipv4-watchdog.timer --perms 0644
        rm -rf $tmp
        pct exec $PBS_CTID -- systemctl daemon-reload
        pct exec $PBS_CTID -- systemctl enable --now dhcp-ipv4-watchdog.timer"
    log "Watchdog timer: $(ct "systemctl is-active dhcp-ipv4-watchdog.timer")"
}

if [[ "$MODE" == "check" ]]; then
    status
    exit 0
fi

repair_lease
install_watchdog
log "Final status:"
status
