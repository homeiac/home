#!/usr/bin/env bash
# Install the caption tag reconciler from the checked-out Git revision.
# The private user rule is provisioned separately and never read or printed here.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/../backup/cloud-backup-common.sh"
cb_ssh 'test -s /etc/knowledge-index-caption-tags.json'
cb_ssh 'p=$(mktemp /opt/knowledge-index/.caption-tags.XXXXXX) && cat > "$p" && /opt/knowledge-index/venv/bin/python -m py_compile "$p" && chmod 0644 "$p" && mv "$p" /opt/knowledge-index/reconcile-caption-tags.py' < "$here/reconcile-caption-tags.py"
for suffix in service timer; do
    unit="knowledge-index-caption-tags.$suffix"
    cb_ssh "p=\$(mktemp /etc/systemd/system/.$unit.XXXXXX) && cat > \"\$p\" && chmod 0644 \"\$p\" && mv \"\$p\" /etc/systemd/system/$unit" < "$here/host/$unit"
done
cb_ssh 'systemd-analyze verify knowledge-index-caption-tags.service knowledge-index-caption-tags.timer && systemctl daemon-reload'
cb_ssh '/opt/knowledge-index/venv/bin/python /opt/knowledge-index/reconcile-caption-tags.py --config /etc/knowledge-index-caption-tags.json'
cb_ssh 'systemctl enable --now knowledge-index-caption-tags.timer && systemctl start knowledge-index-caption-tags.service'
