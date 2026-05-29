#!/bin/bash
# Install ~/.ssh/id_ed25519.pub on every Proxmox host's root account so this
# Mac can SSH key-only afterwards. Uses /usr/bin/expect to feed the password
# from .env -- never echoes the password and never writes it to disk
# elsewhere. Idempotent: ssh-copy-id won't add a duplicate key.
#
# Per CLAUDE.md: NEVER hardcode credentials. Password is sourced from
# proxmox/homelab/.env (gitignored).
#
# Usage: scripts/setup/copy-ssh-keys-to-proxmox.sh [host ...]
#   With no args, copies to the full Proxmox inventory below.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../proxmox/homelab/.env"
PUBKEY="$HOME/.ssh/id_ed25519.pub"

PROXMOX_HOSTS=(
    pve.maas
    still-fawn.maas
    pumped-piglet.maas
    chief-horse.maas
    fun-bedbug.maas
    rapid-civet.maas
)

[[ -f "$PUBKEY" ]] || { echo "ERROR: $PUBKEY not found. Run: ssh-keygen -t ed25519"; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "ERROR: $ENV_FILE not found"; exit 1; }

PROXMOX_ROOT_PASSWORD=$(grep "^PROXMOX_ROOT_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '"')
[[ -n "$PROXMOX_ROOT_PASSWORD" ]] || { echo "ERROR: PROXMOX_ROOT_PASSWORD empty in $ENV_FILE"; exit 1; }
command -v expect >/dev/null || { echo "ERROR: /usr/bin/expect missing"; exit 1; }

HOSTS=("${@:-${PROXMOX_HOSTS[@]}}")
[[ "$#" -gt 0 ]] && HOSTS=("$@")

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

copy_to_host() {
    local host="$1"
    if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new \
           "root@$host" true 2>/dev/null; then
        echo -e "${GREEN}[SKIP]${NC} $host already accepts our key"
        return 0
    fi
    if ! ping -c 1 -W 2 "$host" >/dev/null 2>&1; then
        echo -e "${RED}[FAIL]${NC} $host unreachable on ping"
        return 1
    fi
    expect <<EOF
log_user 0
set timeout 20
spawn ssh-copy-id -i "$PUBKEY" -o StrictHostKeyChecking=accept-new "root@$host"
expect {
    -re "(?i)password:" { send "$PROXMOX_ROOT_PASSWORD\r"; exp_continue }
    -re "already exist|added"  { }
    timeout { exit 2 }
    eof { }
}
catch wait result
exit [lindex \$result 3]
EOF
    local rc=$?
    if [[ $rc -eq 0 ]] && ssh -o BatchMode=yes -o ConnectTimeout=5 \
            "root@$host" true 2>/dev/null; then
        echo -e "${GREEN}[ OK ]${NC} $host key installed"
    else
        echo -e "${RED}[FAIL]${NC} $host (expect rc=$rc) -- check password or host"
        return 1
    fi
}

echo "Installing $PUBKEY on ${#HOSTS[@]} host(s)..."
fail=0
for h in "${HOSTS[@]}"; do copy_to_host "$h" || fail=$((fail+1)); done
echo
if [[ $fail -eq 0 ]]; then
    echo -e "${GREEN}All done.${NC} You can now clear PROXMOX_ROOT_PASSWORD from .env."
else
    echo -e "${YELLOW}$fail host(s) failed.${NC} Pumped-piglet was offline earlier --"
    echo "re-run for just that host once it's back: $0 pumped-piglet.maas"
fi
exit $fail
