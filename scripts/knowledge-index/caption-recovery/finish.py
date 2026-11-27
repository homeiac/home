"""Finish a submitted recovery batch with one corrected pass and verify Immich readback."""
import argparse
import datetime as dt
import fcntl
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import process


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger',type=Path)
    parser.add_argument('--journal',type=Path,required=True)
    parser.add_argument('--rtx',required=True)
    args=parser.parse_args()
    if not args.ledger.is_file():
        parser.error('recovery ledger does not exist')
    # The original batch holds this advisory lock until its work and local checkpoints finish.
    with args.ledger.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
    db=sqlite3.connect(args.ledger)
    db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS recovery_retry(id TEXT PRIMARY KEY, previous_reason TEXT, at TEXT)')
    retried_count=0
    for phase in range(2):
        stamp=dt.datetime.now(dt.timezone.utc).isoformat()
        retryable=db.execute("""SELECT id,reason FROM work WHERE state='error' AND answer IS NULL
          AND (reason LIKE 'EROFS:%' OR reason LIKE '%timed out%' OR reason='no JSON in model reply'
          OR reason='empty video frame') AND id NOT IN (SELECT id FROM recovery_retry)""").fetchall()
        with db:
            db.executemany('INSERT INTO recovery_retry VALUES(?,?,?)',[(r['id'],r['reason'],stamp) for r in retryable])
            db.executemany("UPDATE work SET state='pending',reason=NULL WHERE id=? AND state='error'",[(r['id'],) for r in retryable])
        retried_count+=len(retryable)
        if not db.execute("SELECT count(*) FROM work WHERE state IN ('pending','generated')").fetchone()[0]:
            break
        subprocess.run([sys.executable,str(process.HERE/'process.py'),str(args.ledger),'--limit','2192',
                        '--workers','6' if phase==0 else '4','--rtx',args.rtx,'--journal',str(args.journal),
                        '--final-pass'],check=True)
    deadline=time.monotonic()+3600
    while True:
        process.verify(db)
        if not db.execute("SELECT count(*) FROM work WHERE state='queued'").fetchone()[0] or time.monotonic()>=deadline:
            break
        time.sleep(30)
    counts=dict(db.execute('SELECT state,count(*) FROM work GROUP BY state').fetchall())
    stamp=dt.datetime.now().astimezone().isoformat(timespec='minutes')
    with args.journal.open('a') as journal:
        journal.write(f"\n#### End-of-batch readback · {stamp}\n\n")
        journal.write('| Status | Assets |\n|---|---:|\n')
        for state,count in sorted(counts.items()):
            journal.write(f'| {state} | {count:,} |\n')
        journal.write(f"\n{retried_count} records qualified for a bounded retry after a change to decoding or inference. The private ledger retains per-asset reasons for any unresolved records.\n")
    print(counts,flush=True)


if __name__=='__main__':
    main()
