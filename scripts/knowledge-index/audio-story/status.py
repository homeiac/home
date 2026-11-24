#!/usr/bin/env python3
"""Inspect audio backfill aggregates or prepare the initial queue without inference."""
import fcntl,argparse,importlib.util,json,subprocess,sys
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host');p.add_argument('--discover',action='store_true');a=p.parse_args()
if a.host:
 for source,target in [('worker.py','worker-next.py'),('config.json','config-next.json'),('status.py','status.py')]:
  subprocess.run(['ssh',a.host,'mkdir -p /opt/knowledge-index/audio-story; cat > /opt/knowledge-index/audio-story/'+target],input=Path(__file__).with_name(source).read_bytes(),check=True)
 subprocess.run(['ssh',a.host,'/opt/knowledge-index/venv/bin/python /opt/knowledge-index/audio-story/status.py'+(' --discover' if a.discover else '')],check=True)
 sys.exit()
s=importlib.util.spec_from_file_location('audio',Path(__file__).with_name('worker-next.py'));w=importlib.util.module_from_spec(s);s.loader.exec_module(w)
if a.discover:
 w.ROOT.mkdir(parents=True,exist_ok=True)
 fence=(w.ROOT/'worker.lock').open('a');fcntl.flock(fence,fcntl.LOCK_EX|fcntl.LOCK_NB)
 w.initialize();w.discover(json.loads(Path(__file__).with_name('config-next.json').read_text()))
with w.connect() as d:
 result={'audio':dict(d.execute('SELECT audio_state,count(*) FROM jobs WHERE active=1 GROUP BY 1')),
         'story':dict(d.execute('SELECT story_state,count(*) FROM jobs WHERE active=1 GROUP BY 1')),
         'rows_and_unique':list(d.execute('SELECT count(*),count(DISTINCT id) FROM jobs').fetchone()),
         'by_backend':dict(d.execute("SELECT backend,count(*) FROM jobs WHERE active=1 AND audio_state IN ('speech','no_speech','no_audio','uncertain_speech') GROUP BY backend")),
         'settings':dict(d.execute('SELECT key,value FROM settings'))}
 print(json.dumps(result))
