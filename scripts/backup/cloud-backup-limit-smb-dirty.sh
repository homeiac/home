#!/bin/bash
# Cap how much of the K3s VM's dirty-page budget the SMB disk may use (live + persistent)
#
# Usage: ./cloud-backup-limit-smb-dirty.sh [percent]     (default 20)
#        ./cloud-backup-limit-smb-dirty.sh --check
#
# Why (2026-11-15): VM 105 allows ~1.5 GB of dirty page cache in total (vm.dirty_ratio=5 of 31 GB)
# and the slow USB-HDD SMB disk could take all of it (bdi max_ratio=100). Eight fast Takeout downloads
# filled it with data that disk could not drain, and Linux throttled EVERY writer in the VM -
# including etcd on the fast NVMe root disk - so the K3s node went NotReady. Capping the SMB disk's
# share keeps headroom for etcd/K3s writes on the root disk.
#
# The disk is found inside the VM by mountpoint (/mnt/samba-storage) + ext4 label (smb_data).
# Applies /sys/block/<dev>/bdi/max_ratio now, and installs /etc/udev/rules.d/90-smb-data-bdi.rules
# (matched by filesystem label) so it is re-applied at every boot. Idempotent.
# Revert: rm the rule; echo 100 > /sys/block/<dev>/bdi/max_ratio

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"

ARG="${1:-20}"
CHECK=0
[[ "$ARG" == --check ]] && CHECK=1 && ARG=20
[[ "$ARG" =~ ^[0-9]+$ && "$ARG" -ge 1 && "$ARG" -le 100 ]] || { echo "ERROR: percent must be 1-100"; exit 1; }

cb_ssh "VMID='$CB_K3S_VMID' PCT='$ARG' CHECK='$CHECK' bash -s" <<'EOS'
set -euo pipefail
gx() { qm guest exec "$VMID" --timeout 60 "$@" | python3 -c 'import json,sys
d=json.load(sys.stdin); sys.stdout.write(d.get("out-data","")); sys.stderr.write(d.get("err-data","")); sys.exit(d.get("exitcode",1))'; }
RULE=/etc/udev/rules.d/90-smb-data-bdi.rules
gx -- bash -c "
  set -e
  dev=\$(basename \$(findmnt -no SOURCE /mnt/samba-storage))
  [ \"\$(lsblk -no LABEL /dev/\$dev)\" = smb_data ] || { echo \"ERROR: /mnt/samba-storage is /dev/\$dev, not label smb_data\"; exit 1; }
  echo \"SMB disk: /dev/\$dev  max_ratio now: \$(cat /sys/block/\$dev/bdi/max_ratio)  vm.dirty_ratio: \$(sysctl -n vm.dirty_ratio)\"
  [ $CHECK = 1 ] && { [ -f $RULE ] && echo \"rule: \$(grep -v '^#' $RULE)\" || echo 'rule: (none)'; exit 0; }
  echo $PCT > /sys/block/\$dev/bdi/max_ratio
  want='SUBSYSTEM==\"block\", ACTION==\"add|change\", ENV{ID_FS_LABEL}==\"smb_data\", RUN+=\"/bin/sh -c '\"'\"'echo $PCT > /sys/block/%k/bdi/max_ratio'\"'\"'\"'
  if [ \"\$(grep -v '^#' $RULE 2>/dev/null)\" != \"\$want\" ]; then
    printf '%s\n%s\n' '# Cap the SMB backup disk at $PCT% of the dirty-page budget (scripts/backup/cloud-backup-limit-smb-dirty.sh)' \"\$want\" > $RULE
    udevadm control --reload
    echo \"installed $RULE\"
  else
    echo \"$RULE already up to date\"
  fi
  echo \"SMB disk: /dev/\$dev  max_ratio now: \$(cat /sys/block/\$dev/bdi/max_ratio)\"
"
EOS
