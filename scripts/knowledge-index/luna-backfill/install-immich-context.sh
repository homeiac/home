#!/usr/bin/env bash
# Install the committed read-only Immich snapshot exporter on Piglet.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/../../backup/cloud-backup-common.sh"
cb_ssh 'install -d -m 0700 /opt/knowledge-index/luna-backfill'
cb_ssh 'p=$(mktemp /opt/knowledge-index/luna-backfill/.export-immich-context.XXXXXX) && cat > "$p" && python3 -m py_compile "$p" && mv "$p" /opt/knowledge-index/luna-backfill/export-immich-context.py' < "$here/export-immich-context.py"
for suffix in service timer; do
    unit="knowledge-index-immich-context.$suffix"
    cb_ssh "p=\$(mktemp /etc/systemd/system/.$unit.XXXXXX) && cat > \"\$p\" && chmod 0644 \"\$p\" && mv \"\$p\" /etc/systemd/system/$unit" < "$here/$unit"
done
cb_ssh 'systemd-analyze verify knowledge-index-immich-context.service knowledge-index-immich-context.timer && systemctl daemon-reload'
cb_ssh 'systemctl enable --now knowledge-index-immich-context.timer && systemctl start knowledge-index-immich-context.service'
