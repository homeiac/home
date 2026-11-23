#!/usr/bin/env python3
"""Deploy the committed reconciliation code and operate its bounded shared queue."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
BASE='/opt/knowledge-index/luna-backfill'


def ssh(host: str, command: str, data: bytes | None = None) -> bytes:
    """Use existing administrator access; caller chooses verified inventory hosts."""
    return subprocess.check_output(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',host,command],input=data)


def install(host: str, name: str) -> None:
    """Back up and atomically replace fixed worker sources without touching credentials."""
    path=f'{BASE}/{name}'
    command=(f'set -eu; umask 077; test -d {BASE}; '
             f'if test -f {path}; then cp -p {path} {path}.before-reconciliation; fi; '
             f'cat > {path}.new; /usr/bin/python3 -m py_compile {path}.new; '
             f'chmod 0644 {path}.new; mv {path}.new {path}')
    ssh(host,command,(HERE/name).read_bytes())


def main() -> None:
    """Keep enabling/scaling explicit, with Git policy controlling worker admission."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('inspect','probe','health','install','configure','seed','discover','status','start','verify','review','skip-unresolved','aliases','refresh-policy'))
    parser.add_argument('--piglet',required=True)
    parser.add_argument('--runner',required=True)
    parser.add_argument('--budget-usd',type=int,default=2)
    parser.add_argument('--still-fawn-slots',type=int,default=2)
    parser.add_argument('--mac-slots',type=int,default=0)
    parser.add_argument('--global-slots',type=int,default=2)
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--expected-unresolved',type=int,default=1)
    parser.add_argument('--aliases-file',type=Path)
    args=parser.parse_args()
    if args.mode=='probe':
        code='''import json,os,socket
from pathlib import Path
m=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
print(json.dumps(dict(host=socket.gethostname(),cpus=os.cpu_count(),available_kib=int(m['MemAvailable'].split()[0]),
    existing_luna_cli=Path('/opt/knowledge-index/luna-backfill/bin/codex').is_file(),
    existing_luna_signin=Path('/var/lib/ki-luna/.codex/auth.json').is_file())))
'''
        print(ssh(args.runner,'python3 -c '+shlex.quote(code)).decode())
        return
    if args.mode=='health':
        piglet='''import json,os,time
from pathlib import Path
processes=[]
for p in Path('/proc').glob('[0-9]*'):
    try:
        args=p.joinpath('cmdline').read_bytes().split(b'\\0')
        if b'/opt/knowledge-index/luna-backfill/host.py' not in args:continue
        s=dict(line.split(':',1) for line in p.joinpath('status').read_text().splitlines())
        processes.append(dict(pid=p.name,rss=s.get('VmRSS',''),state=s.get('State',''),wait=p.joinpath('wchan').read_text()))
    except (FileNotFoundError,ProcessLookupError,PermissionError):pass
root=Path('/local-3TB-backup/photo-enrichment/summary-reconciliation')
print(json.dumps(dict(ledger_processes=processes,publication_files=[dict(name=p.name,bytes=p.stat().st_size,age_seconds=round(time.time()-p.stat().st_mtime)) for p in root.glob('*') if p.is_file()])))
'''
        print(ssh(args.piglet,'python3 -c '+shlex.quote(piglet)).decode())
        code='''import json,subprocess
from pathlib import Path
print(subprocess.check_output(['systemctl','show','knowledge-index-luna.service','-p','ActiveState','-p','SubState','-p','ExecMainStatus','-p','MemoryCurrent','-p','MemoryPeak'],text=True))
raw=subprocess.check_output(['journalctl','-u','knowledge-index-luna.service','--since','10 minutes ago','--no-pager','-o','cat'],text=True)
lines=[]
for line in raw.splitlines():
    if line.startswith('RECONCILIATION_BATCH '):
        b=json.loads(line.split(' ',1)[1]);results=b.pop('results')
        b['ok']=sum(r['state']=='ok' for r in results)
        b['unknown']=sum(r['state']=='unknown' for r in results)
        b['skipped']=sum(r['state']=='skipped' for r in results)
        lines.append(json.dumps(b))
    elif line.startswith('RECONCILIATION_IDLE '):lines.append(line)
print('\\n'.join(lines[-4:]))
memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
print('MemAvailable',memory['MemAvailable'])
'''
        print(ssh(args.runner,'python3 -c '+shlex.quote(code)).decode())
        local=Path.home()/'Library/Application Support/knowledge-index-luna/reconciliation.log'
        if local.exists():
            for line in local.read_text().splitlines()[-4:]:
                if line.startswith('RECONCILIATION_BATCH '):
                    batch=json.loads(line.split(' ',1)[1]);results=batch.pop('results')
                    batch['ok']=sum(r['state']=='ok' for r in results)
                    batch['unknown']=sum(r['state']=='unknown' for r in results)
                    batch['skipped']=sum(r['state']=='skipped' for r in results)
                    print(json.dumps(batch))
                else:print(line)
        return
    if args.mode=='inspect':
        print(ssh(args.runner,"hostname; nproc; free -m; runuser -u ki-luna -- /opt/knowledge-index/luna-backfill/bin/codex login status").decode())
        print(subprocess.check_output(['codex','login','status'],stderr=subprocess.STDOUT,text=True).strip())
        return
    if args.mode=='install':
        for name in ('reconciliation.py','host.py'):install(args.piglet,name)
        for name in ('reconciliation.py','worker.py'):install(args.runner,name)
        local=Path.home()/'Library/Application Support/knowledge-index-luna'
        local.mkdir(parents=True,exist_ok=True,mode=0o700)
        for name in ('reconciliation.py','worker.py'):
            target=local/name
            if target.exists():shutil.copy2(target,target.with_suffix('.before-reconciliation'))
            temporary=target.with_suffix('.new');shutil.copyfile(HERE/name,temporary);temporary.replace(target)
        print('Updated existing runner sources; Git policy controls when they submit.')
        return
    if args.mode=='start':
        ssh(args.runner,'systemctl start --no-block knowledge-index-luna.service')
        # Launch one bounded worker in this shell too; its lock prevents a duplicate
        # when the existing launch agent is loaded. Use its already-signed-in CLI.
        if args.mac_slots:
            local=Path.home()/'Library/Application Support/knowledge-index-luna'
            env=dict(os.environ,CB_HOST=args.piglet,KI_LUNA_STATE=str(local),KI_LUNA_RUNNER='mac')
            log=(local/'reconciliation.log').open('ab');os.chmod(log.name,0o600)
            subprocess.Popen([sys.executable,str(local/'worker.py')],env=env,cwd=local,
                             stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            log.close()
        print('Started configured runners; no credentials copied.')
        return
    if args.mode in ('verify','review'):
        code='''import json,sqlite3,duckdb
from pathlib import Path
root=Path('/local-3TB-backup/photo-enrichment')
db=duckdb.connect(str(root/'summary-reconciliation/reconciliation.duckdb'),read_only=True)
print(json.dumps(dict(rows=db.execute('SELECT count(*) FROM reconciled_summaries').fetchone()[0],
    unique_files=db.execute('SELECT count(*) FROM (SELECT DISTINCT path,size_bytes FROM reconciled_summaries)').fetchone()[0],
    states=db.execute('SELECT state,count(*) FROM reconciled_summaries GROUP BY state').fetchall(),
    needs_visual_review=db.execute('SELECT count(*) FROM reconciled_summaries WHERE needs_visual_review').fetchone()[0],
    runners=db.execute("SELECT runner,count(*) FROM reconciled_summaries WHERE state='ok' GROUP BY runner").fetchall(),
    policy_results=db.execute("SELECT prompt_version,runner,risk_level,count(*) FROM reconciled_summaries WHERE state='ok' GROUP BY ALL ORDER BY ALL").fetchall())))
with sqlite3.connect((root/'luna-backfill/luna-ledger.sqlite3').as_uri()+'?mode=ro',uri=True) as ledger:
    print(json.dumps(dict(unsettled_versions=ledger.execute("SELECT prompt_version,state,count(*) FROM reconciliations WHERE state IN ('pending','reserved','sent') GROUP BY prompt_version,state").fetchall())))
'''
        if args.mode=='review':
            code+='''print(json.dumps(db.execute("SELECT local_summary,luna_summary,reconciled_summary,conflicts,notes FROM reconciled_summaries WHERE state='ok' ORDER BY needs_visual_review DESC,id LIMIT 3").fetchall(),ensure_ascii=False))
'''
        print(ssh(args.piglet,'/opt/photo-enrichment/context/venv/bin/python -c '+shlex.quote(code)).decode())
        return
    request={'op':'reconcile_'+args.mode.replace('-','_')}
    if args.mode=='aliases':
        if args.aliases_file is None:parser.error('aliases requires a private --aliases-file')
        values=json.loads(args.aliases_file.read_text())
        request.update(canonical_name=values['canonical_name'],aliases=values['aliases'])
    if args.mode=='skip-unresolved':request['expected']=args.expected_unresolved
    if args.mode=='seed':request['limit']=args.limit
    if args.mode=='configure':
        request.update(budget_usd=args.budget_usd,global_parallel=args.global_slots,
                       runners={k:v for k,v in [('still-fawn',args.still_fawn_slots),('mac',args.mac_slots)] if v})
    print(ssh(args.piglet,f'/opt/photo-enrichment/context/venv/bin/python {BASE}/host.py',json.dumps(request).encode()).decode())


if __name__=='__main__':main()
