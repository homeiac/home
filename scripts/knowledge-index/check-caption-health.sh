#!/usr/bin/env bash
# Read-only caption-worker and heartbeat diagnosis. No restarts or config changes.
# Usage: CB_HOST=root@<inventory-host> scripts/knowledge-index/check-caption-health.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../backup/cloud-backup-common.sh"
cb_ssh 'bash -s' <<'REMOTE'
date -u
uptime
journalctl --list-boots --no-pager | tail -3
journalctl -b -1 -n 8 --no-pager -o short-iso
systemctl show knowledge-index-enrich.service -p LoadState -p ActiveState -p SubState -p Result -p ExecMainStatus -p ExecMainStartTimestamp -p ExecMainExitTimestamp -p NRestarts -p MemoryCurrent -p MemoryPeak
journalctl -u knowledge-index-enrich.service --no-pager -n 24 -o short-iso
journalctl -k --since '24 hours ago' --no-pager | grep -Ei 'out of memory|oom-kill|killed process|I/O error' | tail -12 || true
free -m
cat /proc/pressure/{cpu,memory,io}
find /var/lib/prometheus/node-exporter -maxdepth 1 -type f -iname '*pipeline*' -printf '%f %TY-%Tm-%Td %TH:%TM:%TS\n'
curl -fsS --max-time 15 http://127.0.0.1:9100/metrics | grep -E '^media_pipeline_(heartbeat_timestamp_seconds|running|worker_stage|stage_started_timestamp_seconds)|^node_textfile_scrape_error|^knowledge_index_luna_(heartbeat_timestamp_seconds|running)' || true
REMOTE
