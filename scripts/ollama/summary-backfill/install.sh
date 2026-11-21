#!/bin/bash
# Bootstrap the host reconciler on Piglet from a reviewed copy of this directory.
set -euo pipefail
cd "$(dirname "$0")"
systemctl cat photo-enrichment-context.service >/dev/null
install -D -m 0755 context-policy.sh /usr/local/libexec/knowledge-index-context-policy
install -m 0644 context-policy.{service,timer} /etc/systemd/system/
install -D -m 0644 context-backfill.conf /etc/systemd/system/photo-enrichment-context.service.d/90-summary-backfill.conf
systemctl daemon-reload
systemctl enable --now context-policy.timer
systemctl start context-policy.service
