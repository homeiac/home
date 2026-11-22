#!/usr/bin/env bash
# Read-only Luna ledger, data availability and runner/timer health. No submissions.
# Set CB_HOST and LUNA_RUNNER_HOST from proxmox/inventory.txt.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../backup/cloud-backup-common.sh"
: "${LUNA_RUNNER_HOST:?set LUNA_RUNNER_HOST from inventory}"
cb_ssh 'python3 -' <<'PY'
import datetime, json, sqlite3, time
from pathlib import Path
root = Path('/local-3TB-backup/photo-enrichment/luna-backfill')
db = sqlite3.connect(f'file:{root}/luna-ledger.sqlite3?mode=ro', uri=True)
print('Checked UTC:', datetime.datetime.now(datetime.timezone.utc).isoformat())
print('Library present:', Path('/local-3TB-backup/gphotos/library').is_dir())
print('Luna states:', json.dumps(dict(db.execute('SELECT state,count(*) FROM jobs GROUP BY state'))))
print('Published successful jobs:', db.execute("SELECT count(*) FROM jobs WHERE state='ok' AND published=1").fetchone()[0])
print('Latest successful finish UTC:', db.execute("SELECT max(finished) FROM jobs WHERE state='ok'").fetchone()[0])
print('Successes last 10 minutes:', db.execute("SELECT count(*) FROM jobs WHERE state='ok' AND finished>=datetime('now','-10 minutes')").fetchone()[0])
print('Eligible pending jobs:', db.execute("SELECT count(*) FROM jobs WHERE state='pending' AND available_after<=unixepoch()").fetchone()[0])
print('Blocked flag:', db.execute("SELECT value FROM config WHERE key='blocked'").fetchone())
metrics = Path('/var/lib/prometheus/node-exporter/knowledge_index_luna.prom')
if metrics.exists():
    print('Metrics age seconds:', round(time.time() - metrics.stat().st_mtime, 1))
    print(metrics.read_text())
PY
ssh -o BatchMode=yes -o ConnectTimeout=10 "$LUNA_RUNNER_HOST" 'python3 -' <<'PY'
import datetime, json, subprocess
for unit in ['knowledge-index-luna.service','knowledge-index-luna.timer']:
    print(unit, flush=True)
    subprocess.run(['systemctl','show',unit,'-p','ActiveState','-p','SubState','-p','UnitFileState',
                    '-p','ExecMainStatus','-p','ExecMainStartTimestamp','-p','ExecMainExitTimestamp',
                    '-p','NextElapseUSecRealtime','-p','LastTriggerUSec'], check=True)
for name, window in [('reboot window',['--since','2026-11-22 04:10:00 UTC','--until','2026-11-22 04:40:00 UTC']),
                     ('recent',['--since','20 minutes ago'])]:
    raw=subprocess.check_output(['journalctl','-u','knowledge-index-luna.service','-o','json','--all','--no-pager',*window],text=True)
    batches=[]; events=[]
    for line in raw.splitlines():
        entry=json.loads(line); message=entry.get('MESSAGE') or ''
        if not isinstance(message, str):
            continue
        at=datetime.datetime.fromtimestamp(int(entry['__REALTIME_TIMESTAMP'])/1e6,datetime.timezone.utc).isoformat()
        if message.startswith('LUNA_BATCH '):
            batch=json.loads(message[len('LUNA_BATCH '):])
            batches.append({'at':at,'saved':sum(r['state']=='ok' for r in batch['results'])})
        elif any(s in message for s in ['Piglet operation failed', 'Idle, exhausted or blocked',
                                      'Failed with result', 'Starting knowledge-index-luna',
                                      'Finished knowledge-index-luna', 'ExecCondition=']):
            events.append({'at':at,'message':message[:240]})
    print(name, json.dumps({'batch_count':len(batches),'saved':sum(b['saved'] for b in batches),
                           'first_batch':batches[:1],'last_batch':batches[-1:],'events':events[-18:]}))
PY
