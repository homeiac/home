#!/bin/bash
# Drop an apt.conf.d snippet on each Proxmox host that disables
# Unattended-Upgrade's auto-reboot. Background: 2026-05-29, chief-horse
# was silently rebooted at 05:40 by unattended-upgrades; a latent
# ceph-mon ordering cycle then deleted pve-cluster's start job, which
# took the host out of cluster-managed state for ~10h until manual
# intervention. We've separately fixed the ceph cycle, but disabling
# unscheduled-and-unsupervised reboots is the additional safety net.
#
# This script only disables Automatic-Reboot. It does NOT touch
# Unattended-Upgrade::Allowed-Origins — security updates still apply,
# we just don't reboot for them without being there.
#
# Idempotent. Run as: scripts/setup/disable-unattended-reboot.sh [host ...]

set -u

PROXMOX_HOSTS=(
    pve.maas
    still-fawn.maas
    pumped-piglet.maas
    chief-horse.maas
    fun-bedbug.maas
)

HOSTS=("${@:-${PROXMOX_HOSTS[@]}}")

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

DROPIN_PATH='/etc/apt/apt.conf.d/52-no-auto-reboot'
DROPIN_BODY='// Managed by scripts/setup/disable-unattended-reboot.sh
// Keep auto-upgrades, but never auto-reboot. See 2026-05-29 RCA.
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Automatic-Reboot-WithUsers "false";
'

apply() {
    local host="$1"
    if ! ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
           "root@$host" true 2>/dev/null; then
        echo -e "${RED}[FAIL]${NC} $host unreachable / no key trust"
        return 1
    fi
    if ssh -o BatchMode=yes "root@$host" "test -f $DROPIN_PATH && grep -q 'Automatic-Reboot \"false\"' $DROPIN_PATH" 2>/dev/null; then
        echo -e "${GREEN}[SKIP]${NC} $host already configured"
        return 0
    fi
    ssh -o BatchMode=yes "root@$host" "cat > $DROPIN_PATH" <<< "$DROPIN_BODY"
    if ssh -o BatchMode=yes "root@$host" "test -f $DROPIN_PATH && grep -q 'Automatic-Reboot \"false\"' $DROPIN_PATH" 2>/dev/null; then
        echo -e "${GREEN}[ OK ]${NC} $host: wrote $DROPIN_PATH"
    else
        echo -e "${RED}[FAIL]${NC} $host: write verification failed"
        return 1
    fi
}

echo "Disabling Unattended-Upgrade auto-reboot on ${#HOSTS[@]} host(s)..."
fail=0
for h in "${HOSTS[@]}"; do apply "$h" || fail=$((fail+1)); done
echo
if [[ $fail -eq 0 ]]; then
    echo -e "${GREEN}All done.${NC}"
else
    echo -e "${YELLOW}$fail host(s) failed.${NC} Re-run after the host is reachable / has key trust."
fi
exit $fail
