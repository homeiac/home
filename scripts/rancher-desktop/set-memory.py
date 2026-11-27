#!/usr/bin/env python3
"""Back up and resize Rancher Desktop RAM; verify its VM and prior workloads."""
import argparse
from datetime import datetime,timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import time

RD=Path.home()/'.rd/bin/rdctl'
DOCKER=Path.home()/'.rd/bin/docker'

def run(args):
    return subprocess.check_output([str(a) for a in args],text=True,stderr=subprocess.PIPE,timeout=30)

def settings():
    return json.loads(run([RD,'list-settings']))

def kube(kind):
    return json.loads(run([RD,'shell','sudo','k3s','kubectl','get',kind,'-A','-o','json']))['items']

def healthy(pod):
    return any(c['type']=='Ready' and c['status']=='True' for c in pod['status'].get('conditions',[]))

def identity(pod):
    owner=next(iter(pod['metadata'].get('ownerReferences',[])),{})
    return (pod['metadata']['namespace'],owner.get('kind','Pod'),owner.get('name',pod['metadata']['name']))

def memory():
    entries=dict(line.split(':',1) for line in run([RD,'shell','cat','/proc/meminfo']).splitlines())
    return {key:int(entries[key].split()[0])*1024 for key in ('MemTotal','MemAvailable')}

def containers():
    return run([DOCKER,'--context','rancher-desktop','ps','--format','{{.Names}}']).splitlines()

def main():
    logging.basicConfig(level=logging.INFO,format='%(message)s')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gib',type=int);parser.add_argument('--backup-dir',type=Path,required=True)
    args=parser.parse_args();assert args.gib>=4
    os.umask(0o077);args.backup_dir.mkdir(parents=True,exist_ok=True)
    before=settings();vm=memory();pods=kube('pods') if before['kubernetes']['enabled'] else []
    required={identity(p) for p in pods if healthy(p)}
    external={name for name in containers() if not name.startswith('k8s_')}
    used=(vm['MemTotal']-vm['MemAvailable'])/1024**3
    assert args.gib>=used+2,'Keep at least 2 GiB above observed non-reclaimable use'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=args.backup_dir/f'rancher-{stamp}.json'
    backup.write_text(json.dumps({'settings':before,'vm':vm,'healthy_workloads':sorted(required),'external_containers':sorted(external)},indent=2)+'\n')
    logging.info('Backed up settings privately; resizing %s → %s GiB (observed used %.2f GiB)',before['virtualMachine']['memoryInGB'],args.gib,used)
    result=subprocess.run([str(RD),'set',f'--virtual-machine.memory-in-gb={args.gib}'],capture_output=True,text=True,timeout=180)
    if result.returncode:raise RuntimeError('Rancher rejected resize; inspect local application status')
    deadline=time.monotonic()+300;last='VM restarting'
    while time.monotonic()<deadline:
        try:
            after=settings();actual=memory()
            assert after['virtualMachine']['memoryInGB']==args.gib,'Configured memory mismatch'
            assert args.gib*.9<=actual['MemTotal']/1024**3<=args.gib*1.05,'VM memory has not changed yet'
            other=json.loads(json.dumps(after));other['virtualMachine']['memoryInGB']=before['virtualMachine']['memoryInGB']
            assert other==before,'Unexpected settings change'
            assert external<=set(containers()),'Waiting for previously running standalone containers'
            if before['kubernetes']['enabled']:
                assert all(healthy(n) for n in kube('nodes')),'Waiting for Kubernetes node Ready'
                ready={identity(p) for p in kube('pods') if healthy(p)}
                assert required<=ready,'Waiting for previously healthy Kubernetes workloads'
            report={'at':datetime.now(timezone.utc).isoformat(),'before_gib':before['virtualMachine']['memoryInGB'],'after_gib':args.gib,'vm_total_gib':round(actual['MemTotal']/1024**3,2),'vm_available_gib':round(actual['MemAvailable']/1024**3,2),'healthy_workloads_restored':len(required),'standalone_containers_restored':sorted(external),'backup':str(backup)}
            (args.backup_dir/f'rancher-{stamp}-result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2));return
        except (subprocess.SubprocessError,AssertionError,json.JSONDecodeError) as error:
            current=str(error) if isinstance(error,AssertionError) else 'Waiting for local runtime API'
            if current!=last:logging.info('%s',current);last=current
            time.sleep(5)
    raise RuntimeError('Resize applied but verification timed out: '+last)

if __name__=='__main__':main()
