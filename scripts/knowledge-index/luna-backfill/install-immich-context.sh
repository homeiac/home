#!/usr/bin/env bash
# Install the committed Immich context exporter and Photos reconciliation on Piglet.
set -euo pipefail
if [[ $# -gt 1 || (${1:-} != "" && ${1:-} != "--install-only") ]]; then
    echo "Usage: $0 [--install-only]" >&2
    exit 2
fi
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/../../backup/cloud-backup-common.sh"
cb_ssh 'install -d -m 0700 /opt/knowledge-index/luna-backfill'
for script in export-immich-context.py reconcile-immich-faces.py; do
    cb_ssh "p=\$(mktemp /opt/knowledge-index/luna-backfill/.$script.XXXXXX) && cat > \"\$p\" && python3 -m py_compile \"\$p\" && mv \"\$p\" /opt/knowledge-index/luna-backfill/$script" < "$here/$script"
done
for suffix in service timer; do
    unit="knowledge-index-immich-context.$suffix"
    cb_ssh "p=\$(mktemp /etc/systemd/system/.$unit.XXXXXX) && cat > \"\$p\" && chmod 0644 \"\$p\" && mv \"\$p\" /etc/systemd/system/$unit" < "$here/$unit"
done
cb_ssh 'systemd-analyze verify knowledge-index-immich-context.service knowledge-index-immich-context.timer && systemctl daemon-reload'
cb_ssh 'systemctl enable --now knowledge-index-immich-context.timer'
if [[ ${1:-} != "--install-only" ]]; then
    cb_ssh 'systemctl start knowledge-index-immich-context.service'
fi
