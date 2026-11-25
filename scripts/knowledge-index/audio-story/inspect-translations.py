#!/usr/bin/env python3
"""Inspect authorized Codex translation outcomes; private examples require --review."""
import argparse,json,shlex,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--host');p.add_argument('--review',action='store_true');p.add_argument('--useful-only',action='store_true');a=p.parse_args()
if a.host:
 target='/opt/knowledge-index/audio-story/inspect-translations.py'
 subprocess.run(['ssh','-o','BatchMode=yes',a.host,'cat > '+target],input=Path(__file__).read_bytes(),check=True)
 command=shlex.join(['/opt/knowledge-index/venv/bin/python',target]+(['--review'] if a.review else [])+(['--useful-only'] if a.useful_only else []))
 subprocess.run(['ssh','-o','BatchMode=yes',a.host,command],check=True);raise SystemExit
import worker
with worker.connect() as d:
 rows=d.execute('SELECT id,job,state,cost,result FROM codex_requests').fetchall()
 answered=[json.loads(r['result']) for r in rows if r['state']=='ok']
 production=[json.loads(r['result']) for r in rows if r['state']=='ok' and not r['job'].startswith('pilot:')]
 summary={'checked_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'states':dict(d.execute('SELECT state,count(*) FROM codex_requests GROUP BY state')),
  'pilot_requests':sum(r['job'].startswith('pilot:') for r in rows),'production_requests':sum(not r['job'].startswith('pilot:') for r in rows),
  'production_completed':len(production),'production_assessments':{kind:sum(r['assessment']==kind for r in production) for kind in ('useful','unclear','incidental')},
  'assessments':{kind:sum(r['assessment']==kind for r in answered) for kind in ('useful','unclear','incidental')},
  'estimated_and_held_usd':sum(r['cost'] for r in rows)/1e6,
  'waiting':d.execute("SELECT count(*) FROM jobs WHERE active=1 AND audio_state='speech' AND needs_codex(language,transcript)=1 AND story_state IN ('pending','inflight','error')").fetchone()[0],
  'story_failures':dict(d.execute("SELECT error,count(*) FROM jobs WHERE active=1 AND story_state='skipped' GROUP BY error"))}
 print(json.dumps(summary),flush=True)
 if a.review:
  for r in d.execute("SELECT j.language,j.visual_summary,j.transcript,c.result FROM codex_requests c JOIN jobs j ON j.id=c.job WHERE c.state='ok' AND (?=0 OR json_extract(c.result,'$.assessment')='useful') ORDER BY j.updated DESC LIMIT 3",[int(a.useful_only)]):
   print(json.dumps(dict(r),ensure_ascii=False),flush=True)
