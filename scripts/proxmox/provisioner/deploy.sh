#!/bin/bash
set -e

TARGET_HOST="${TARGET_HOST:?TARGET_HOST required}"
SSH_KEY="${SSH_KEY_PATH:-/ssh/id_rsa}"
VMID="${VMID:-108}"

SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $SSH_KEY"
SCP="scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $SSH_KEY"

log() { echo "[$(date '+%H:%M:%S')] $1"; }

log "Deploying to $TARGET_HOST"

# Test SSH
$SSH root@$TARGET_HOST hostname || { log "SSH failed"; exit 1; }

# Deploy hookscripts
if ls /scripts/hookscripts/*.sh 2>/dev/null; then
    $SSH root@$TARGET_HOST "mkdir -p /var/lib/vz/snippets"
    for f in /scripts/hookscripts/*.sh; do
        $SCP "$f" "root@$TARGET_HOST:/var/lib/vz/snippets/"
        log "Deployed $(basename $f)"
    done

    # Attach GPU hookscript to VM
    if [[ -f /scripts/hookscripts/gpu-reset-vm108.sh ]]; then
        HOOK=$($SSH root@$TARGET_HOST "grep hookscript /etc/pve/qemu-server/${VMID}.conf 2>/dev/null || true")
        if [[ ! "$HOOK" =~ "gpu-reset" ]]; then
            $SSH root@$TARGET_HOST "qm set $VMID --hookscript local:snippets/gpu-reset-vm108.sh"
            log "Attached hookscript to VM $VMID"
        fi
    fi
fi

log "Done"
