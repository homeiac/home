#!/usr/bin/env python3
"""Check repeated discovery against a private ledger clone; never invoke a model."""
import argparse,importlib.util,json,shlex,sqlite3,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host');a=p.parse_args()
if a.host:
 directory='/opt/knowledge-index/audio-story/discovery-validation'
 for source,target in [('worker.py','worker-candidate.py'),('verify-discovery.py','verify-discovery.py')]:
  subprocess.run(['ssh','-o','BatchMode=yes',a.host,'install -d -m 0700 '+directory+'; cat > '+directory+'/'+target],input=Path(__file__).with_name(source).read_bytes(),check=True)
 subprocess.run(['ssh','-o','BatchMode=yes',a.host,shlex.join(['/opt/knowledge-index/venv/bin/python',directory+'/verify-discovery.py'])],check=True);raise SystemExit
spec=importlib.util.spec_from_file_location('candidate',Path(__file__).with_name('worker-candidate.py'));w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
config=json.loads(w.CONFIG.read_text())
with tempfile.TemporaryDirectory(dir=w.ROOT,prefix='.discovery-check-') as temporary:
 clone=Path(temporary)
 with sqlite3.connect('file:'+str(w.ROOT/'ledger.sqlite3')+'?mode=ro',uri=True) as source,sqlite3.connect(clone/'ledger.sqlite3') as target:source.backup(target)
 with w.connect(clone) as d:production=dict(d.execute('SELECT id,visual_hash FROM jobs WHERE active=1'))
 w.discover(config,clone)
 with w.connect(clone) as d:
  before=dict(d.execute('SELECT id,visual_hash FROM jobs WHERE active=1'))
  d.execute("UPDATE jobs SET story_state='ok' WHERE active=1")
 w.discover(config,clone)
 with w.connect(clone) as d:
  after=dict(d.execute('SELECT id,visual_hash FROM jobs WHERE active=1'))
  queued=d.execute("SELECT count(*) FROM jobs WHERE active=1 AND story_state<>'ok'").fetchone()[0]
 changes=sum(before.get(key)!=value for key,value in after.items())+len(set(before)-set(after))
 print(json.dumps({'checked_video_groups':len(after),'changed_inputs_against_production':sum(production.get(k)!=v for k,v in before.items())+len(set(production)-set(before)),'changed_inputs_on_repeat':changes,'stories_requeued_on_repeat':queued,'models_called':0,'production_ledger_modified':False}),flush=True)
 if changes or queued:raise RuntimeError('Unchanged discovery was not stable')
