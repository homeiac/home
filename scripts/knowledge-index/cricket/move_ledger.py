"""Move only cricket's transactional state to the verified host SSD, retaining online backups."""

import argparse
import shlex
import subprocess

REMOTE = r"""
import json,os,shutil,sqlite3,subprocess,sys,time
from pathlib import Path
os.umask(0o077)
state=Path('/local-3TB-backup/photo-enrichment/cricket')
fast=Path('/var/lib/photo-enrichment/cricket')
root=Path('/opt/photo-enrichment/gui').resolve()
sys.path.insert(0,str(root))
from cricket.ledger import backup
from cricket.prepare import save_private
unitroot=Path('/etc/systemd/system')
oldworker=unitroot/'cricket-highlights.service'
newworker=unitroot/'cricket-highlights-ssd.service'
gui=unitroot/'photo-enrichment-gui.service'
if (state/'ledger.sqlite3').resolve().parent==fast:
 print(json.dumps({'already_on_ssd':True}));sys.exit(0)
filesystem=subprocess.check_output(['findmnt','-T','/var/lib','-no','FSTYPE'],text=True).strip()
if filesystem!='ext4' or shutil.disk_usage('/var/lib').free<2*1024**3:raise RuntimeError('Verified SSD filesystem/capacity changed')
fast.mkdir(parents=True,exist_ok=True)
stamp=str(time.time_ns());recovery=fast/'backups'/stamp;recovery.mkdir(parents=True)
for unit in (gui,oldworker):shutil.copy2(unit,recovery/unit.name)
config=json.loads((state/'policy.json').read_text());config['enabled']=False;save_private(state/'policy.json',config)
backup(state/'ledger.sqlite3',recovery/'before-quiesce.sqlite3')
# Quiesce the review API before the final consistent snapshot. Baseline workers stay running.
subprocess.run(['systemctl','stop','photo-enrichment-gui.service'],check=True,timeout=30)
try:
 subprocess.run(['systemctl','disable','cricket-highlights.service'],check=True)
 subprocess.run(['systemctl','stop','--no-block','cricket-highlights.service'],check=True)
 # The blocked request cannot be usefully drained. Its cached answer is retained;
 # stale leases are fenced after cutover. Only this newly created worker is signalled.
 subprocess.run(['systemctl','kill','--kill-whom=all','--signal=SIGKILL','cricket-highlights.service'],check=False)
 backup(state/'ledger.sqlite3',recovery/'authority.sqlite3')
 backup(recovery/'authority.sqlite3',fast/'ledger.sqlite3')
 with sqlite3.connect(fast/'ledger.sqlite3') as db:
  db.execute("UPDATE jobs SET state='queued',checkpoint='{}' WHERE state='running'")
  db.commit();db.execute('PRAGMA journal_mode=WAL')
 for name in ('evidence','exports'):
  (state/name).mkdir(exist_ok=True)
  (fast/name).symlink_to(state/name)
 oldstate=state/('worker-zfs-'+stamp)
 (state/'worker').rename(oldstate)
 (fast/'worker').mkdir()
 if (oldstate/'answers').exists():shutil.copytree(oldstate/'answers',fast/'worker/answers')
 (state/'worker').symlink_to(fast/'worker')
 for suffix in ('','-wal','-shm'):
  original=state/('ledger.sqlite3'+suffix)
  if original.exists():original.rename(state/('ledger-zfs-'+stamp+'.sqlite3'+suffix))
 (state/'ledger.sqlite3').symlink_to(fast/'ledger.sqlite3')
 def permit(unit):
  return '\n'.join(line+' '+str(fast) if line.startswith('ReadWritePaths=') else line for line in unit.splitlines())+'\n'
 gui.write_text(permit(gui.read_text()))
 newworker.write_text(permit(oldworker.read_text()))
 subprocess.run(['systemd-analyze','verify',str(gui),str(newworker)],check=True)
 subprocess.run(['systemctl','daemon-reload'],check=True)
 subprocess.run(['systemctl','enable','--now',newworker.name],check=True)
 save_private(fast/'cutover.json',{'backup':str(recovery),'old_state':str(oldstate),'authority':'ssd','time':time.time()})
 print(json.dumps({'authority':'ssd','backup':str(recovery),'worker':'cricket-highlights-ssd','enabled':False}))
finally:
 subprocess.run(['systemctl','start','photo-enrichment-gui.service'],check=True,timeout=30)
"""


def main() -> None:
    """Apply the scoped ledger cutover after inspecting host filesystems and blocked commit evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    args = parser.parse_args()
    subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            args.host,
            "python3 -c " + shlex.quote(REMOTE),
        ],
        check=True,
        timeout=120,
    )


if __name__ == "__main__":
    main()
