#!/usr/bin/env python3
"""Versioned PostgreSQL cutover with quiesced backup and no automatic data rollback."""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path('/opt/photo-enrichment')
STATE=Path('/local-3TB-backup/photo-enrichment')
CONFIG=Path('/etc/photo-enrichment')
PROM=Path('/var/lib/prometheus/node-exporter')
WORKER='photo-enrichment-worker.service'
UNITS=Path('/etc/systemd/system')


def run(*args,**kwargs):
    return subprocess.run(args,check=True,**kwargs)


def source_paths():
    pid=subprocess.check_output(['systemctl','show','knowledge-index-enrich','-p','MainPID','--value'],text=True).strip()
    argv=Path('/proc',pid,'cmdline').read_bytes().decode().split('\0')
    return tuple(Path(argv[argv.index(flag)+1]).resolve() for flag in ('--index','--library'))


def unit(command,description,extra='',oneshot=False):
    return f'''[Unit]
Description={description}
After=network-online.target
Wants=network-online.target
[Service]
Type={'oneshot' if oneshot else 'simple'}
EnvironmentFile=/etc/default/photo-enrichment-worker
Environment=PGSERVICEFILE=/etc/photo-enrichment/pg_service.conf
Environment=PGPASSFILE=/etc/photo-enrichment/pgpass
Environment=PHOTO_PG_SERVICE=photo_pipeline
Environment=HOME=/local-3TB-backup/photo-enrichment
Environment=OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2
ExecStart={command}
TimeoutStopSec=180
Nice=10
IOSchedulingClass=idle
CPUQuota=200%
MemoryHigh=1G
MemoryMax=2G
UMask=0077
NoNewPrivileges=true
CapabilityBoundingSet=
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/local-3TB-backup/photo-enrichment /var/lib/prometheus/node-exporter
{extra}
[Install]
WantedBy=multi-user.target
'''


def status():
    for name in (WORKER,'photo-enrichment-gui.service','photo-enrichment-export.timer','photo-enrichment-catalog.timer'):
        print(name,subprocess.run(['systemctl','show',name,'-p','ActiveState','-p','SubState','-p','NRestarts'],capture_output=True,text=True).stdout.strip())
    manifest=STATE/'analytics/current.json'
    if manifest.exists():
        data=json.loads(manifest.read_text())
        print('Snapshot',data['generation'],'age_seconds',round(time.time()-data['captured_at'],1),
              'rows',{k:v['rows'] for k,v in data['tables'].items()})


def main():
    os.umask(0o077)
    payload=json.load(sys.stdin)
    if payload['mode']=='status':return status()
    index,library=source_paths()
    if payload['mode']=='inspect':
        print('Source catalog exists:',(index/'knowledge.duckdb').exists(),'legacy state exists:',(STATE/'enrichment.duckdb').exists())
        print('Free GiB:',round(shutil.disk_usage(STATE).free/2**30,1));return status()
    release=ROOT/'releases'/payload['release']
    release.mkdir(parents=True,exist_ok=True)
    for name,content in payload['files'].items():
        path=release/name
        if not path.resolve().is_relative_to(release.resolve()):raise ValueError('Invalid source path')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content)
    CONFIG.mkdir(mode=0o700,exist_ok=True)
    if payload.get('pgpass'):
        (CONFIG/'pgpass').write_text('postgres.app.home.panderosystems.com:5432:photo_enrichment:photo_enrichment:'+payload['pgpass']+'\n')
        (CONFIG/'pgpass').chmod(0o600)
    if not (CONFIG/'pgpass').exists():raise RuntimeError('Dedicated PostgreSQL credentials are absent; no service was stopped')
    (CONFIG/'pg_service.conf').write_text('[photo_pipeline]\nhost=postgres.app.home.panderosystems.com\nport=5432\ndbname=photo_enrichment\nuser=photo_enrichment\nsslmode=prefer\nconnect_timeout=10\n')
    env=dict(os.environ,PGSERVICEFILE=str(CONFIG/'pg_service.conf'),PGPASSFILE=str(CONFIG/'pgpass'),PHOTO_PG_SERVICE='photo_pipeline',HOME=str(STATE),OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2')
    if not (release/'venv/bin/python').exists():run(sys.executable,'-m','venv','--without-pip',str(release/'venv'))
    python=str(release/'venv/bin/python')
    run(sys.executable,'-m','pip','--python',python,'install','--disable-pip-version-check','-r',str(release/'photo_enrichment/requirements.txt'))
    run(python,'-c',"import psycopg,duckdb; c=psycopg.connect(service='photo_pipeline'); print('PostgreSQL connected:',c.info.server_version); c.close(); d=duckdb.connect(); d.execute('INSTALL postgres; LOAD postgres'); print('Signed DuckDB PostgreSQL extension ready')",env=env)
    print('Prepared release:',payload['release'],flush=True)
    if payload['mode']=='prepare':return
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=ROOT/'backups'/('postgres-'+stamp);backup.mkdir(parents=True)
    for name in (WORKER,'photo-enrichment-gui.service','photo-enrichment-export.service','photo-enrichment-export.timer','photo-enrichment-catalog.service','photo-enrichment-catalog.timer'):
        path=UNITS/name
        if path.exists():shutil.copy2(path,backup/name)
    (backup/'previous-release.txt').write_text(str((ROOT/'current').resolve()))
    run('systemctl','stop',WORKER)
    # Stop any PG services on a redeploy; existing PG results/labels remain authoritative.
    for name in ('photo-enrichment-export.timer','photo-enrichment-catalog.timer','photo-enrichment-gui.service','photo-enrichment-export.service','photo-enrichment-catalog.service'):
        subprocess.run(['systemctl','stop',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for path in STATE.glob('enrichment.duckdb*'):shutil.copy2(path,backup/path.name)
    print('Quiesced recovery backup:',backup,flush=True)
    cli=[python,str(release/'photo-enrich.py'),'--backend','postgres','--index',str(index),'--library',str(library),'--state',str(STATE)]
    # On failure retain both stores and leave writers paused: silently resuming the
    # old writer after PG-only progress could discard new facts or user edits.
    run(*cli,'migrate',env=env,timeout=600)
    run(*cli,'worker','--batch-size','3','--max-batches','1',env=env,timeout=600)
    run(*cli,'--prom',str(PROM/'photo_snapshot.prom'),'export',env=env,timeout=600)
    current=ROOT/'current';temporary=ROOT/'current.new'
    temporary.unlink(missing_ok=True);temporary.symlink_to(release);temporary.replace(current)
    base='/opt/photo-enrichment/current/venv/bin/python /opt/photo-enrichment/current/photo-enrich.py --backend postgres --index ${PHOTO_INDEX} --library ${PHOTO_LIBRARY} --state ${PHOTO_STATE}'
    (UNITS/WORKER).write_text(unit(base+' --prom /var/lib/prometheus/node-exporter/photo_enrichment.prom worker --batch-size 25 --timezone UTC','Photo enrichment PostgreSQL worker','Restart=on-failure\nRestartSec=30'))
    (UNITS/'photo-enrichment-gui.service').write_text(unit(base+' --prom /var/lib/prometheus/node-exporter/photo_review.prom serve --bind 0.0.0.0 --port 8765 --public-origin https://photos.app.home.panderosystems.com','Photo face and event review',
        'Restart=on-failure\nRestartSec=10\nIPAddressDeny=any\nIPAddressAllow=localhost\nIPAddressAllow=192.168.4.0/24\nIPAddressAllow=10.42.0.0/16\nIPAddressAllow=100.64.0.0/10\nEnvironment=PHOTO_FRIGATE_URL=https://frigate.app.home.panderosystems.com'))
    for name,action,interval in (('export','--prom /var/lib/prometheus/node-exporter/photo_snapshot.prom export','5min'),('catalog','refresh-catalog','1h')):
        (UNITS/f'photo-enrichment-{name}.service').write_text(unit(base+' '+action,'Photo enrichment '+name,oneshot=True))
        (UNITS/f'photo-enrichment-{name}.timer').write_text(f'[Unit]\nDescription=Photo enrichment {name} schedule\n[Timer]\nOnBootSec=3min\nOnUnitInactiveSec={interval}\n[Install]\nWantedBy=timers.target\n')
    run('systemctl','daemon-reload')
    run('systemd-analyze','verify',str(UNITS/WORKER),str(UNITS/'photo-enrichment-gui.service'),str(UNITS/'photo-enrichment-export.service'),str(UNITS/'photo-enrichment-catalog.service'))
    run('systemctl','enable','--now',WORKER,'photo-enrichment-gui.service','photo-enrichment-export.timer','photo-enrichment-catalog.timer')
    status()


if __name__=='__main__':main()
