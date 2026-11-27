#!/usr/bin/env python3
"""Stop only Waffles workers, preserving results, settings and other services.

Phases: prepare disables discovery with its advisory lock and checks the queue;
native disables Mac launch agents and native-host services/timers; verify checks
all hosts plus the zero replicas committed through Flux. Runtime snapshots stay
private. No host shutdown, model deletion or queue-row deletion is performed.
"""
import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import time

from distributed import KUBE, request

LABELS = ['com.panderosystems.waffles-worker', 'com.panderosystems.waffles-burst-workers']
HOSTS = ['fun-bedbug.maas', 'chief-horse.maas']
DEPLOYMENTS = ['waffles-worker-still-fawn', 'waffles-worker-pve',
               'waffles-burst-still-fawn', 'waffles-burst-pve', 'waffles-media']


def run(command: list, **kwargs) -> subprocess.CompletedProcess:
    """Bound each operation and suppress service environment output."""
    return subprocess.run(command, text=True, capture_output=True, timeout=110, **kwargs)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['status', 'prepare', 'native', 'verify'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    args.directory.mkdir(parents=True, exist_ok=True)
    status = request('/admin/status')
    active = [r for r in status['runs'] if r['status'] in ('running', 'classified') or
              (r['mode']=='production' and r['status']=='pending')]
    report = {'at':datetime.now(timezone.utc).isoformat(), 'active_jobs':sum(r['jobs'] for r in active),
              'discovery':status.get('discovery'), 'workers':status['workers']}
    logging.info('Waffles %s: %d unfinished production/in-flight jobs', args.phase, report['active_jobs'])
    if args.phase == 'status':
        logging.info('%s', json.dumps(report))
        return
    if args.phase == 'prepare':
        snapshot = args.directory/'before.json'
        if not snapshot.exists():
            snapshot.write_text(json.dumps({'status':status, 'tuning':request('/api/tuning'),
                                           'burst':request('/api/burst')}, indent=2)+'\n')
        if active:
            raise RuntimeError('Unfinished work: drain before shutdown; no settings changed')
        code = """import {createRequire} from 'node:module';
const {Client}=createRequire('/usr/src/app/server/package.json')('pg');const db=new Client();await db.connect();
await db.query('BEGIN');try{
await db.query("SET LOCAL lock_timeout='10s'");await db.query('SELECT pg_advisory_xact_lock(244,2)');
const n=(await db.query("SELECT count(*)::int n FROM waffles.jobs j JOIN waffles.runs r ON r.id=j.run_id WHERE j.status IN ('running','classified') OR (r.mode='production' AND j.status='pending')")).rows[0].n;
if(n)throw Error('New work appeared; drain first');
await db.query("UPDATE waffles.settings SET value=jsonb_set(value,'{enabled}','false') WHERE key='discovery'");
await db.query("UPDATE waffles.runs SET state='paused' WHERE state='running'");
await db.query('COMMIT');}catch(e){await db.query('ROLLBACK');throw e;}finally{await db.end();}
console.log('Discovery disabled; cursor retained; running empty queues paused');"""
        result = run(KUBE+['-n','immich-pilot','exec','-i','deployment/waffles-queue','--','node','--input-type=module','-'], input=code)
        if result.returncode:
            (args.directory/'prepare-error.log').write_text(result.stderr)
            raise RuntimeError('Preparation failed; private diagnostics retained')
        logging.info('%s', result.stdout.strip())
        return
    if active or status.get('discovery', {}).get('enabled'):
        raise RuntimeError('Prepare and drain before stopping or verifying workers')
    for label in LABELS:
        identity = f'gui/{os.getuid()}/{label}'
        if args.phase == 'native':
            run(['launchctl','disable',identity], check=True)
            if run(['launchctl','print',identity]).returncode == 0:
                run(['launchctl','bootout',identity], check=True)
        deadline = time.monotonic()+30
        while run(['launchctl','print',identity]).returncode == 0:
            if args.phase != 'native' or time.monotonic()>deadline:
                raise RuntimeError('Waffles launch agent remains loaded')
            time.sleep(.5)
        logging.info('Mac agent unloaded: %s', label)
    for host in HOSTS:
        # Only inventory-listed Proxmox hosts, never their K3s VMs.
        ssh = ['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10']
        try:
            socket.getaddrinfo(host, 22)
        except socket.gaierror:
            inventory = Path(__file__).resolve().parents[2]/'proxmox/inventory.txt'
            entries = [line.split('#',1)[0].strip() for line in inventory.read_text().splitlines()
                       if '#' in line and line.split('#',1)[1].strip()==host.removesuffix('.maas')]
            assert len(entries)==1, 'Unique inventory address required for DNS fallback'
            ssh += ['-o','HostName='+entries[0],'-o','HostKeyAlias='+host]
            logging.info('Using verified inventory address for %s; SSH host-key checks retained', host)
        ssh += ['root@'+host]
        if args.phase == 'native':
            stopped = run(ssh+['systemctl disable --now waffles-worker.timer waffles-worker.service'])
            if stopped.returncode:
                logging.error('Native shutdown failed on %s: %s', host, stopped.stderr.strip())
                raise RuntimeError('Native shutdown incomplete; rerun after resolving transport')
        result = run(ssh+['systemctl show waffles-worker.service waffles-worker.timer -p Id -p ActiveState -p UnitFileState'], check=True)
        if 'ActiveState=active' in result.stdout or 'ActiveState=activating' in result.stdout or 'UnitFileState=enabled' in result.stdout:
            raise RuntimeError('Native Waffles unit remains enabled or active: '+host)
        logging.info('Native service and timer stopped/disabled: %s', host)
    processes = run(['ps','-axo','command='], check=True).stdout.splitlines()
    remaining = [line for line in processes if 'Application Support/immich-pet-tagger/' in line and
                 any(name in line for name in ('supervisor.py','worker.py','burst-worker.py','burst-supervisor.py'))]
    if remaining:
        raise RuntimeError('Waffles Mac child processes remain; inspect before declaring shutdown')
    if args.phase == 'verify':
        result = run(KUBE+['-n','immich-pilot','get','deployments',*DEPLOYMENTS,'-o','json'], check=True)
        deployments = json.loads(result.stdout)['items']
        assert len(deployments)==len(DEPLOYMENTS)
        for deployment in deployments:
            assert deployment['spec']['replicas']==0 and deployment['status'].get('replicas',0)==0, 'Wait for Flux scale-down'
        pods = json.loads(run(KUBE+['-n','immich-pilot','get','pods','-o','json'], check=True).stdout)['items']
        assert not any(p['metadata'].get('labels',{}).get('app') in DEPLOYMENTS for p in pods), 'Worker pods remain'
        report = {'at':datetime.now(timezone.utc).isoformat(), 'state':'stopped', 'unfinished_production_jobs':0,
                  'discovery_enabled':False,'mac_worker_processes':0,'mac_agents_disabled':LABELS,
                  'native_services_disabled':HOSTS,'zero_replica_deployments':DEPLOYMENTS,
                  'retained':['PostgreSQL results','reference and worker PVCs','queue metrics','tagger UI','Grafana dashboard']}
        (args.directory/'verified.json').write_text(json.dumps(report,indent=2)+'\n')
        if args.output:
            args.output.write_text(json.dumps(report,indent=2)+'\n')
        logging.info('%s', json.dumps(report))


if __name__ == '__main__':
    main()
