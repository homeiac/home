"""Recover the frozen historical caption cohort using the existing Bonsai prompts and publisher."""
import argparse
import base64
import concurrent.futures
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'enrichers'))
from media_summary import ask_model, build_prompt, parse_answer, story_prompt

KUBE = ['kubectl', '--kubeconfig', str(Path.home() / 'kubeconfig'), '-n', 'immich-pilot', 'exec', '-i']
LOCAL = 'http://127.0.0.1:19476'
MODEL = 'bonsai-27b-metal'
PRIVATE = Path.home() / 'Library/Application Support'
ASSET_MODULE = HERE / 'asset.mjs'


def pod(mode, items):
    """Exchange only allowlisted per-asset records with the existing sync container."""
    prefix = 'const mode=' + json.dumps(mode) + ', items=' + json.dumps(items) + ';\n'
    out = subprocess.run(KUBE + ['deploy/immich-sync', '--', 'node', '--input-type=module', '-'],
                         input=prefix + ASSET_MODULE.read_text(), text=True, capture_output=True, check=True, timeout=300)
    rows = [json.loads(line) for line in out.stdout.splitlines()]
    if [r['id'] for r in rows] != [r['id'] for r in items]:
        raise RuntimeError('incomplete asset response')
    return rows


def infer(row, backend, key, final_pass=False):
    """Generate a description using the same scene and four-frame video prompts as the pipeline."""
    frames = [base64.b64decode(s, validate=True) for s in row['frames']]
    context = dict(album=None, taken_ts=None, people=[], has_geo=False)
    duration = row['duration']
    prompt = (story_prompt(context, duration, row['positions'])
              if duration else build_prompt(context, False, 1, ''))
    schema={'type':'object','required':['summary','tags'],'properties':{
        'summary':{'type':'string'},'tags':{'type':'array','items':{'type':'string'}}}}
    if final_pass:
        prompt+=' Return one JSON object containing a short factual scene description and a list of tags.'
    model = MODEL if backend == LOCAL else 'bonsai-27b'
    if backend == LOCAL:
        reply = ask_model(backend, model, prompt, frames, timeout=300,
                          headers={'Authorization': 'Bearer ' + key},
                          extra={'max_tokens': 256, 'chat_template_kwargs': {'enable_thinking': False},
                                 'response_format': ({'type':'json_schema','json_schema':{'name':'caption','schema':schema}} if final_pass else {'type':'json_object'})})
    else:
        reply = ask_model(backend, model, prompt, frames, timeout=300, api='ollama',
                          extra={'think': False, 'format':schema if final_pass else 'json',
                                 'options': {'temperature': 0.2, 'num_ctx':4096, 'num_predict':256}})
    summary, tags = parse_answer(reply)
    if summary.lower() in {'null','none','unclear'} or len(summary.split()) < 4:
        raise ValueError('no usable scene description')
    return dict(summary=summary, tags=tags, model=model,
                created=dt.datetime.now(dt.timezone.utc).isoformat(), mtime=row['mtime'], frameCount=len(frames))



def verify(db):
    """Recheck queued writes in Immich by exact ID and saved text before marking them verified."""
    rows=db.execute("SELECT id,answer FROM work WHERE state='queued'").fetchall()
    for offset in range(0,len(rows),500):
        records=rows[offset:offset+500]
        from uuid import UUID
        ids=','.join("'"+str(UUID(r['id']))+"'" for r in records)
        query="""BEGIN READ ONLY;
          SELECT json_build_array("assetId", value->>'summary')
          FROM asset_metadata WHERE key='home.knowledge-index.v1'
          AND "assetId" IN ("""+ids+"""); ROLLBACK;"""
        command=KUBE+['deploy/immich-postgres','--','psql','-XqAt','-v','ON_ERROR_STOP=1','-U','immich','-d','immich']
        out=subprocess.check_output(command,input=query,text=True,timeout=60)
        found=dict(json.loads(line) for line in out.splitlines())
        for r in records:
            if found.get(r['id'])==json.loads(r['answer'])['summary']:
                db.execute("UPDATE work SET state='verified' WHERE id=?", (r['id'],))
    db.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger', type=Path)
    parser.add_argument('--limit', type=int, required=True)
    parser.add_argument('--final-pass', action='store_true', help='Use a constrained response schema for previously failed items')
    parser.add_argument('--retry-errors', action='store_true', help='Retry only after correcting a previously observed failure')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--journal', type=Path, help='Append aggregate progress every ten batches')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--rtx', help='Additional verified local Bonsai endpoint')
    args = parser.parse_args()
    os.umask(0o077)
    if not args.ledger.is_file() or args.limit < 1 or not 1 <= args.workers <= 8:
        parser.error('supply an existing frozen ledger, positive limit and 1–8 workers')
    lock = args.ledger.with_suffix('.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    db = sqlite3.connect(args.ledger)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS work(id TEXT PRIMARY KEY,state TEXT NOT NULL,reason TEXT,answer TEXT,frame_hash TEXT)')
    db.execute("INSERT OR IGNORE INTO work(id,state) SELECT id,'pending' FROM cohort WHERE cohort='caption'")
    db.commit()
    verify(db)
    if args.verify_only:
        print(dict(db.execute('SELECT state,count(*) FROM work GROUP BY state').fetchall()))
        return
    if args.retry_errors:
        db.execute("UPDATE work SET state='pending',reason=NULL WHERE state='error' AND answer IS NULL")
        db.commit()
    key = (PRIVATE / 'knowledge-index-bonsai/server.key').read_text().strip()
    def publish(items):
        for result in pod('publish', items):
            db.execute('UPDATE work SET state=?,reason=? WHERE id=?',
                       (result['state'],result.get('reason'),result['id']))
        db.commit()
    # If the process stopped after inference, replay the saved answer without invoking the model.
    for row in db.execute("SELECT c.*,w.answer FROM work w JOIN cohort c USING(id) WHERE state='generated'").fetchall():
        publish([dict(row) | json.loads(row['answer'])])
    rows = [dict(r) for r in db.execute("""WITH ranked AS (
      SELECT c.*,row_number() over (partition by lower(substr(path,-4)) order by id) n
      FROM cohort c JOIN work w USING(id) WHERE w.state='pending')
      SELECT * FROM ranked ORDER BY n,id LIMIT ?""", (args.limit,))]
    retried_ids=set()
    if args.final_pass:
        retried_ids={r['id'] for r in db.execute('SELECT id FROM recovery_retry')}
    empty_batches=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0,len(rows),12):
            batch=rows[offset:offset+12]
            inputs=pod('stage',batch)
            tasks={}
            publishable=[]
            for i,(item,staged) in enumerate(zip(batch,inputs)):
                if staged['state']!='staged':
                    db.execute('UPDATE work SET state=?,reason=? WHERE id=?',(staged['state'],staged.get('reason'),item['id']))
                    continue
                fingerprint=hashlib.sha256(json.dumps([staged['duration'],staged['frames']]).encode()).hexdigest()
                cached=db.execute('SELECT answer FROM work WHERE frame_hash=? AND answer IS NOT NULL LIMIT 1',(fingerprint,)).fetchone()
                if cached:
                    answer=json.loads(cached['answer']) | {'mtime':staged['mtime']}
                    db.execute("UPDATE work SET state='generated',answer=?,frame_hash=? WHERE id=?",(json.dumps(answer),fingerprint,item['id']))
                    publishable.append(item | answer)
                else:
                    backend=args.rtx if args.rtx and i%2 else LOCAL
                    tasks[pool.submit(infer,staged,backend,key,item['id'] in retried_ids)]=(item,fingerprint)
            db.commit()
            for task in concurrent.futures.as_completed(tasks):
                item,fingerprint=tasks[task]
                try:
                    answer=task.result()
                except Exception as exc:
                    db.execute("UPDATE work SET state='error',reason=? WHERE id=?",(str(exc)[:150],item['id']))
                else:
                    db.execute("UPDATE work SET state='generated',answer=?,frame_hash=? WHERE id=?",(json.dumps(answer),fingerprint,item['id']))
                    publishable.append(item | answer)
                db.commit()
            if publishable: publish(publishable)
            verify(db)
            counts=dict(db.execute('SELECT state,count(*) FROM work GROUP BY state').fetchall())
            print(counts,flush=True)
            if args.journal and (offset%120==0 or offset+12>=len(rows)):
                with args.journal.open('a') as f:
                    stamp=dt.datetime.now().astimezone().isoformat(timespec='minutes')
                    f.write(f"\n- {stamp} · {counts.get('verified',0):,} read back from Immich, {counts.get('queued',0):,} submitted, {counts.get('already_described',0):,} independently filled, {counts.get('pending',0):,} pending, {counts.get('error',0):,} unresolved.\n")
            empty_batches = 0 if publishable or any(r['state']=='already_described' for r in inputs) else empty_batches+1
            if empty_batches>=3:
                raise RuntimeError('Three full batches produced no usable output; inspect model and media availability.')


if __name__=='__main__':
    main()
