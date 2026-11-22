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
    parser.add_argument('mode',choices=('inspect','install','configure','seed','status','start','verify','review'))
    parser.add_argument('--piglet',required=True)
    parser.add_argument('--runner',required=True)
    parser.add_argument('--budget-usd',type=int,default=2)
    parser.add_argument('--still-fawn-slots',type=int,default=2)
    parser.add_argument('--mac-slots',type=int,default=0)
    parser.add_argument('--global-slots',type=int,default=2)
    parser.add_argument('--limit',type=int,default=10)
    args=parser.parse_args()
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
    runners=db.execute("SELECT runner,count(*) FROM reconciled_summaries WHERE state='ok' GROUP BY runner").fetchall())))
'''
        if args.mode=='review':
            code+='''print(json.dumps(db.execute("SELECT local_summary,luna_summary,reconciled_summary,conflicts,notes FROM reconciled_summaries WHERE state='ok' ORDER BY needs_visual_review DESC,id LIMIT 3").fetchall(),ensure_ascii=False))
'''
        print(ssh(args.piglet,'/opt/photo-enrichment/context/venv/bin/python -c '+shlex.quote(code)).decode())
        return
    request={'op':'reconcile_'+args.mode}
    if args.mode=='seed':request['limit']=args.limit
    if args.mode=='configure':
        request.update(budget_usd=args.budget_usd,global_parallel=args.global_slots,
                       runners={k:v for k,v in [('still-fawn',args.still_fawn_slots),('mac',args.mac_slots)] if v})
    print(ssh(args.piglet,f'/opt/photo-enrichment/context/venv/bin/python {BASE}/host.py',json.dumps(request).encode()).decode())


if __name__=='__main__':main()
