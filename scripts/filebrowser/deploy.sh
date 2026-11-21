#!/usr/bin/env bash
# Upload reviewed scripts to piglet and provision FileBrowser. Uses SSH agent auth.
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
host=${1:-pumped-piglet.maas}
remote_dir=$(ssh -o BatchMode=yes "root@$host" 'mktemp -d /root/filebrowser-deploy.XXXXXX')
COPYFILE_DISABLE=1 tar -C "$SCRIPT_DIR" -cf - setup-host.sh configure-mounts-host.sh unlock-bitlocker-host.sh proxy-container.sh config.yaml filebrowser.service filebrowser-proxy.socket filebrowser-proxy.service |
    ssh -o BatchMode=yes "root@$host" "tar -xf - -C '$remote_dir'"
ssh -o BatchMode=yes "root@$host" "bash '$remote_dir/setup-host.sh'"
