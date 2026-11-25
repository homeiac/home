#!/usr/bin/env python3
"""Back up and requeue only settled story format failures, preserving all audio.

Defaults to read-only inspection. After deploying the guarded worker, --requeue
allows one new recovery attempt under its changed policy (not the old prompt).
"""
import argparse,json,sqlite3,subprocess,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--host');p.add_argument('--requeue',action='store_true');a=p.parse_args()
if a.host:
    target='/opt/knowledge-index/audio-story/recover-format-errors.py'
    subprocess.run(['ssh','-o','BatchMode=yes',a.host,'cat > '+target],input=Path(__file__).read_bytes(),check=True)
    subprocess.run(['ssh','-o','BatchMode=yes',a.host,'/opt/knowledge-index/venv/bin/python '+target+(' --requeue' if a.requeue else '')],check=True)
    raise SystemExit
import worker
root=worker.ROOT
with sqlite3.connect('file:'+str(root/'ledger.sqlite3')+'?mode=ro',uri=True) as d:
    d.row_factory=sqlite3.Row
    rows=d.execute("SELECT * FROM jobs WHERE active=1 AND story_state IN ('error','skipped') AND error IN ('JSONDecodeError','StoryFormatError')").fetchall()
    withheld=sum(bool(r['transcript']) and not worker.reliable_story_segments(json.loads(r['transcript'])) for r in rows)
    if a.requeue and rows:
        if 'story_note' not in rows[0].keys():raise RuntimeError('Deploy the guarded worker first')
        directory=root/'recovery-backups';directory.mkdir(exist_ok=True)
        backup=sqlite3.connect(directory/('before-format-recovery-'+str(time.time_ns())+'.sqlite3'))
        d.backup(backup);backup.close()
changed=0
if a.requeue and rows:
    with worker.connect() as d:
        for r in rows:
            changed+=d.execute("UPDATE jobs SET story_state='pending',story_attempts=0,retry_at=0,story_note='format_recovery_pending',updated=? WHERE id=? AND active=1 AND story_state IN ('error','skipped') AND error IN ('JSONDecodeError','StoryFormatError') AND visual_hash=? AND updated=?",[time.time(),r['id'],r['visual_hash'],r['updated']]).rowcount
print(json.dumps({'format_failures':len(rows),'repetitive_speech_to_withhold':withheld,'usable_speech_for_codex':len(rows)-withheld,'requeued':changed,'audio_modified':False,'models_called':0}))
