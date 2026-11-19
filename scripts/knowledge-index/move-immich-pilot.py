#!/usr/bin/env python3
"""Move the isolated Immich pilot to piglet using backups and existing virtiofs.

Git/Flux controls workload placement and replicas. This helper copies private
state only after the server is quiesced. Source PVCs are retained for rollback.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

ROOT=Path('/private/tmp/immich-pilot/move-to-piglet')
HOST='root@192.168.4.175'  # proxmox/inventory.txt
KUBE=['kubectl','--kubeconfig',str(Path.home()/'kubeconfig'),'-n','immich-pilot']
HOST_STAGE='/local-3TB-backup/gphotos/.immich-pilot-migration'


def host(code: str) -> str:
    """Run controlled Python on the inventoried Proxmox host."""
    return subprocess.check_output(['ssh','-o','BatchMode=yes',HOST,'python3 -c '+shlex.quote(code)],text=True)


def guest(code: str) -> str:
    """Use the guest agent; never SSH to the Kubernetes VM."""
    command=['qm','guest','exec','105','--timeout','120','--','python3','-c',code]
    result=json.loads(host('import subprocess\nprint(subprocess.check_output('+repr(command)+',text=True))'))
    if result.get('exitcode')!=0:
        raise RuntimeError(result)
    return result.get('out-data','')


def paused() -> None:
    """Refuse inconsistent backups while the Immich server is still running."""
    pods=json.loads(subprocess.check_output(KUBE+['get','pods','-l','app.kubernetes.io/instance=immich,app.kubernetes.io/name=server','-o','json']))
    if pods['items']:
        raise RuntimeError('Wait for Flux to stop Immich server pods before copying state')


def inspect() -> None:
    """Discover mount paths and capacity without changing state."""
    print(guest("""
import subprocess,json,pathlib
for cmd in (['findmnt','-t','virtiofs','-o','TARGET,SOURCE,FSTYPE,OPTIONS'],['df','-h','/var/lib'],['free','-h']):
 print(subprocess.check_output(cmd,text=True))
print('Active virtiofs tags:',[p.read_text().strip() for p in pathlib.Path('/sys/bus/virtio/devices').glob('*/tag')])
"""))
    print(host("import subprocess,json\nr=json.loads(subprocess.check_output(['pvesh','get','/nodes/pumped-piglet/qemu/105/pending','--output-format','json'],text=True));print(json.dumps([x for x in r if x['key'].startswith('virtiofs')]))"))


def backup() -> None:
    """Take a logical DB backup and byte-preserving media/queue archive."""
    paused()
    if (ROOT/'backup-complete.json').exists():
        raise RuntimeError('Immutable migration backup already exists')
    with (ROOT/'database.dump').open('wb') as output:
        subprocess.run(KUBE+['exec','deployment/immich-postgres','--','pg_dump','-U','immich','-d','immich','-Fc'],stdout=output,check=True)
    subprocess.run(KUBE+['exec','deployment/immich-valkey','--','valkey-cli','SAVE'],check=True)
    with (ROOT/'media-queue.tar').open('wb') as output:
        subprocess.run(KUBE+['exec','deployment/immich-migration-source','--','tar','-C','/source','-cf','-','library','valkey'],stdout=output,check=True)
    # Stage outside the source library; the existing virtiofs mount exposes this to VM 105.
    print(host('import pathlib\np=pathlib.Path('+repr(HOST_STAGE)+');p.mkdir(mode=0o700,exist_ok=True)\nprint("Private host staging ready")'))
    for name in ('database.dump','media-queue.tar'):
        subprocess.run(['scp','-q',str(ROOT/name),HOST+':'+HOST_STAGE+'/'+name],check=True)
    import hashlib
    sizes={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in ROOT.iterdir() if p.is_file()}
    (ROOT/'backup-complete.json').write_text(json.dumps(sizes,indent=2))
    print(json.dumps({k:v['bytes'] for k,v in sizes.items()}))


def prepare_mount() -> None:
    """Mount the existing virtiofs device read-only; preserve fstab before persistence."""
    print(guest("""
import pathlib,subprocess,shutil,json
target=pathlib.Path('/mnt/gphotos')
existing=subprocess.run(['findmnt','-J','--mountpoint',str(target)],capture_output=True,text=True)
if existing.returncode==0:
 mount=json.loads(existing.stdout)['filesystems'][0]
 if mount['source']!='gphotos' or mount['fstype']!='virtiofs': raise RuntimeError('Unexpected existing mount')
else:
 target.mkdir(mode=0o755,exist_ok=True)
 subprocess.run(['mount','-t','virtiofs','-o','ro,nosuid,nodev','gphotos',str(target)],check=True)
if not (target/'library').is_dir(): raise RuntimeError('Mounted dataset lacks library directory')
fstab=pathlib.Path('/etc/fstab')
if not any(line.split()[:2]==['gphotos',str(target)] for line in fstab.read_text().splitlines()):
 backup=pathlib.Path('/var/backups/immich-pilot');backup.mkdir(mode=0o700,parents=True,exist_ok=True)
 saved=backup/'fstab-before-gphotos'
 if not saved.exists(): shutil.copy2(fstab,saved)
 with fstab.open('a') as out: out.write('\\n# Photo library via existing Proxmox virtiofs mapping (Immich pilot)\\ngphotos /mnt/gphotos virtiofs ro,nosuid,nodev,nofail 0 0\\n')
print('Direct photo library available read-only at /mnt/gphotos/library')
"""))


def restore_files() -> None:
    """Populate fresh local SSD directories; reject accidental replacement."""
    paused()
    if not (ROOT/'backup-complete.json').exists():
        raise RuntimeError('Complete backup required')
    print(guest("""
import pathlib,subprocess,json,tarfile
mounts=json.loads(subprocess.check_output(['findmnt','-J','-t','virtiofs'],text=True))['filesystems']
mount=next(pathlib.Path(m['target']) for m in mounts if m['source']=='gphotos')
archive=mount/'.immich-pilot-migration/media-queue.tar'
target=pathlib.Path('/var/lib/immich-pilot')
if target.exists(): raise RuntimeError('Destination exists; refusing to overwrite')
target.mkdir(mode=0o755)
with tarfile.open(archive) as source:
 source.extractall(target,filter='data')
for name in ('postgres','cache'): (target/name).mkdir(mode=0o755)
(target/'migration-source.json').write_text(json.dumps(dict(source=str(archive))))
print(json.dumps(dict(target=str(target),library_bytes=sum(p.stat().st_size for p in (target/'library').rglob('*') if p.is_file()),direct_library=str(mount/'library'))))
"""))


def restore_database() -> None:
    """Restore only into the fresh target database after GitOps moves PostgreSQL."""
    paused()
    pod=json.loads(subprocess.check_output(KUBE+['get','pods','-l','app=immich-postgres','-o','json']))['items'][0]
    if pod['spec']['nodeName']!='k3s-vm-pumped-piglet-gpu':
        raise RuntimeError('Database is not on target node')
    count=subprocess.check_output(KUBE+['exec','deployment/immich-postgres','--','psql','-U','immich','-d','immich','-Atc',"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"],text=True).strip()
    if count!='0':
        raise RuntimeError('Target database is not empty; refusing to overwrite')
    with (ROOT/'database.dump').open('rb') as source:
        subprocess.run(KUBE+['exec','-i','deployment/immich-postgres','--','pg_restore','--exit-on-error','--no-owner','-U','immich','-d','immich'],stdin=source,check=True)
    (ROOT/'database-restored.json').write_text(json.dumps(dict(node=pod['spec']['nodeName'])))
    print('Database restored to piglet; server remains paused until GitOps resumes it')


def main() -> None:
    """Run one explicit migration phase."""
    os.umask(0o077)
    ROOT.mkdir(parents=True,mode=0o700,exist_ok=True)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inspect','prepare-mount','backup','restore-files','restore-database'])
    globals()[parser.parse_args().action.replace('-','_')]()


if __name__=='__main__':
    main()
