#!/usr/bin/env bash
# Install the metadata-only verifier and validate access before the private prompt.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
host=${1:-pumped-piglet.maas}
ssh -o BatchMode=yes "root@$host" 'if test -f /usr/local/sbin/filebrowser-verify-efs-certificate.py; then install -d -m 700 /root/filebrowser-backups; cp /usr/local/sbin/filebrowser-verify-efs-certificate.py /root/filebrowser-backups/efs-verifier-$(date +%Y%m%dT%H%M%S).py; fi; install -m 700 /dev/stdin /usr/local/sbin/filebrowser-verify-efs-certificate.py' < "$SCRIPT_DIR/verify-efs-certificate.py"
ssh -o BatchMode=yes "root@$host" 'python3 /usr/local/sbin/filebrowser-verify-efs-certificate.py --metadata-only'
