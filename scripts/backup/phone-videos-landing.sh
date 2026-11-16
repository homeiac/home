#!/bin/bash
# Landing folder for phone videos on the SMB share, plus a read-only status/verify report
#
# Usage: ./phone-videos-landing.sh init                 create cloud-backup/phone-videos/ (owner nobody, mode 2770)
#        ./phone-videos-landing.sh status [subdir]      files, GB, newest file, per sub-folder totals, suspicious files
#
# Lands under cloud-backup/ on purpose: the SSK and WD mirrors copy everything under it, so phone videos get the extra copies
# without any new job. Runs inside K3s VM 105 via qm guest exec and only does metadata work (find/stat/du): no bulk I/O there.
# Suspicious = zero-byte files and names ending .tmp/.part/.crdownload/.pending (copy interrupted).
# Phone side: copy with an SMB-capable file manager (see issue/chat), then compare these counts and sizes with the phone's own
# folder properties BEFORE deleting anything on the phone. Needs CB_HOST (e.g. root@<host ip>).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
readonly ROOT=/mnt/samba-storage/cloud-backup/phone-videos
gx() { cb_ssh "qm guest exec $CB_K3S_VMID --timeout 120 -- bash -c $(printf '%q' "$1")" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.stdout.write(d.get("out-data","")+d.get("err-data","")); sys.exit(d.get("exitcode",1))'; }
case "${1:-}" in
  init) gx "mkdir -p $ROOT && chown 65534:65534 $ROOT && chmod 2770 $ROOT && ls -ld $ROOT";;
  status)
    SUB="${2:-}"
    gx "cd $ROOT${SUB:+/$SUB} 2>/dev/null || { echo 'no such folder: $ROOT${SUB:+/$SUB}'; exit 1; }
      echo \"folder: \$(pwd)\"
      echo \"files: \$(find . -type f | wc -l)   size: \$(du -sh --apparent-size . | cut -f1)   free on share: \$(df -h --output=avail /mnt/samba-storage | tail -1 | tr -d ' ')\"
      echo \"newest: \$(find . -type f -printf '%TY-%Tm-%Td %TH:%TM  %p\n' | sort | tail -1)\"
      echo '--- per sub-folder (files, size)'
      for d in */; do [ -d \"\$d\" ] && printf '%6d  %8s  %s\n' \"\$(find \"\$d\" -type f | wc -l)\" \"\$(du -sh --apparent-size \"\$d\" | cut -f1)\" \"\$d\"; done 2>/dev/null
      echo '--- suspicious (zero-byte / partial names)'
      find . -type f \\( -size 0 -o -iname '*.tmp' -o -iname '*.part' -o -iname '*.crdownload' -o -iname '*.pending' \\) | head -20
      echo '(end)'";;
  *) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 1;;
esac
