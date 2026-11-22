#!/usr/bin/env bash
# Inspect permanent service and heartbeat; optionally test a service-only restart.
# No Proxmox host reboot. Run audit-host.sh before and after --restart.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../backup/cloud-backup-common.sh"
case "${1:-}" in
  --restart)
    cb_ssh 'test -f /opt/knowledge-index/caption-gitops/applied.json && systemctl is-enabled --quiet knowledge-index-enrich.service && systemctl restart knowledge-index-enrich.service'
    ;;
  '') ;;
  *) echo 'Usage: check-host.sh [--restart]' >&2; exit 2;;
esac
cb_ssh 'python3 -' <<'PY'
import json
from pathlib import Path
import subprocess
import time

subprocess.run(['systemctl', 'show', 'knowledge-index-enrich.service', '-p', 'ActiveState',
                '-p', 'SubState', '-p', 'MainPID', '-p', 'FragmentPath', '-p', 'UnitFileState',
                '-p', 'NRestarts', '-p', 'ExecMainStartTimestamp'], check=True)
state = Path('/opt/knowledge-index/caption-gitops/applied.json')
print('Applied deployment:', state.read_text() if state.exists() else 'not installed')
metrics = Path('/var/lib/prometheus/node-exporter/knowledge_index_pipeline.prom')
if metrics.exists():
    print('Heartbeat file age seconds:', round(time.time() - metrics.stat().st_mtime, 1))
    for line in metrics.read_text().splitlines():
        if line.startswith(('media_pipeline_running{', 'media_pipeline_items_total{',
                            'media_pipeline_heartbeat_timestamp_seconds{')):
            print(line)
workers = []
for proc in Path('/proc').glob('[0-9]*'):
    try:
        argv = (proc / 'cmdline').read_bytes().split(b'\0')
        if b'/opt/knowledge-index/enrichers/media_summary.py' in argv:
            workers.append(int(proc.name))
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
print('Caption worker process IDs:', json.dumps(workers))
keys = Path('/root/.ssh/authorized_keys').read_text().splitlines()
print('Restricted deployment key entries:', sum('caption-worker-gitops' in line for line in keys))
PY
