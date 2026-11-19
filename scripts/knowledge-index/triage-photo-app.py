#!/usr/bin/env python3
"""Read-only, bounded photo-app triage; report timings/resources without photo data."""
import concurrent.futures
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
import urllib.request
import re

REMOTE = r'''
import json, pathlib, subprocess, time, urllib.request
unit='photo-enrichment-gui.service'
def command(argv):
    return subprocess.run(argv,text=True,capture_output=True,timeout=10).stdout.strip()
props=command(['systemctl','show',unit,'-p','MainPID','-p','ActiveState','-p','SubState','-p','NRestarts','-p','MemoryCurrent','-p','CPUUsageNSec','-p','TasksCurrent','-p','ControlGroup'])
data=dict(line.split('=',1) for line in props.splitlines())
pid=data.get('MainPID','0')
data['release']=str(pathlib.Path('/opt/photo-enrichment/gui').resolve())
cg=pathlib.Path('/sys/fs/cgroup')/data.get('ControlGroup','').lstrip('/')
for name in ['cpu.stat','cpu.pressure','memory.events','memory.pressure','io.pressure']:
    p=cg/name
    if p.exists():data[name]=p.read_text().strip()
waits={}
for p in pathlib.Path('/proc',pid,'task').glob('*/wchan'):
    try:
        value=p.read_text().strip();waits[value]=waits.get(value,0)+1
    except OSError:pass
data['thread_waits']=waits
data['profiler_available']=bool(command(['sh','-c','command -v py-spy']))
data['journal_errors']=command(['journalctl','-u',unit,'--since','-10 min','-p','err','--no-pager','-o','cat'])[:4000]
started=time.monotonic()
try:
    with urllib.request.urlopen('http://127.0.0.1:8765/api/status',timeout=5) as r:
        data['loopback_probe']={'code':r.status,'seconds':round(time.monotonic()-started,3)}
except Exception as exc:data['loopback_probe']={'error':type(exc).__name__,'seconds':round(time.monotonic()-started,3)}
print(json.dumps(data))
'''

SQL = """SELECT state,coalesce(wait_event_type,'none') AS wait_type,coalesce(wait_event,'none') AS wait_event,
 round(extract(epoch FROM now()-query_start)::numeric,2) AS query_age_s,
 CASE WHEN query LIKE '%enriched_media%' THEN 'catalog_view'
 WHEN query LIKE '%face%' THEN 'faces' WHEN query LIKE '%photo_jobs%' THEN 'job_queue'
 ELSE split_part(query,' ',1) END AS operation,
 cardinality(pg_blocking_pids(pid)) AS blockers
 FROM pg_stat_activity WHERE datname='photo_enrichment' AND pid<>pg_backend_pid()
 ORDER BY query_start LIMIT 30;"""


def main() -> None:
    host=os.environ['CB_HOST']
    env=dict(os.environ,KUBECONFIG=os.environ.get('KUBECONFIG',str(Path.home()/'kubeconfig')))
    def probe(path):
        started=time.monotonic()
        try:
            with urllib.request.urlopen('https://photos.app.home.panderosystems.com'+path,timeout=8) as response:
                response.read()
                return dict(path=path,status=response.status,seconds=round(time.monotonic()-started,3))
        except Exception as exc:return dict(path=path,error=type(exc).__name__,seconds=round(time.monotonic()-started,3))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        probes=list(pool.map(probe,['/','/app.js','/api/status']))
    print(json.dumps(dict(https=probes)),flush=True)
    with urllib.request.urlopen('https://photos.app.home.panderosystems.com/api/diagnostics',timeout=5) as response:
        diagnostics=json.load(response)
        print(json.dumps(dict(diagnostics=diagnostics)),flush=True)
    subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,'python3 -c '+shlex.quote(REMOTE)],check=True,timeout=30)
    subprocess.run(['kubectl','-n','database','exec','-i','postgres-postgresql-0','--','psql','-X','-U','postgres','-d','photo_enrichment','-P','pager=off','-c',SQL],env=env,check=True,timeout=20)
    query="SELECT json_agg(query) FROM pg_stat_activity WHERE datname='photo_enrichment' AND state='active' AND pid<>pg_backend_pid();"
    result=subprocess.run(['kubectl','-n','database','exec','postgres-postgresql-0','--','psql','-X','-U','postgres','-d','photo_enrichment','-At','-c',query],env=env,check=True,timeout=15,text=True,capture_output=True)
    for statement in json.loads(result.stdout.strip() or 'null') or []:
        # SQL templates only: remove literal data before displaying diagnostics.
        print('active_query_template:',re.sub(r"'(?:''|[^'])*'", "'?'",statement)[:5000])


if __name__=='__main__':main()
