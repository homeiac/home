"""Inspect worker errors, service resources, and thread wait states without private model inputs."""

import argparse
import shlex
import subprocess

REMOTE = r"""
import json,subprocess,os
from pathlib import Path
unit='cricket-highlights-ssd.service' if Path('/local-3TB-backup/photo-enrichment/cricket/ledger.sqlite3').resolve().parent==Path('/var/lib/photo-enrichment/cricket') else 'cricket-highlights.service'
fields=subprocess.check_output(['systemctl','show',unit,'-p','MainPID','-p','NRestarts','-p','ActiveState','-p','SubState','-p','MemoryCurrent','-p','CPUUsageNSec'],text=True)
print(fields)
pid=next(line.split('=',1)[1] for line in fields.splitlines() if line.startswith('MainPID='))
waits={}
folder=Path('/proc')/pid/'task'
if folder.exists():
 for path in folder.iterdir():
  try:
   wait=(path/'wchan').read_text().strip();waits[wait]=waits.get(wait,0)+1
   print('kernel_stack',path.name,(path/'stack').read_text()[:1600])
  except OSError:pass
print(json.dumps({'thread_waits':waits,'host_load':os.getloadavg()}))
for command in (['zpool','status','-x'],['findmnt','-T','/local-3TB-backup/photo-enrichment/cricket','-o','SOURCE,FSTYPE,TARGET'],['findmnt','-T','/var/lib','-o','SOURCE,FSTYPE,TARGET'],['df','-h','/var/lib','/local-3TB-backup']):
 subprocess.run(command,check=False)
for unit in ('photo-enrichment-gui.service','photo-enrichment-export.service'):
 subprocess.run(['systemctl','show',unit,'-p','User','-p','Group','-p','DynamicUser','-p','RootDirectory','-p','ReadWritePaths','-p','ReadOnlyPaths','-p','CapabilityBoundingSet','-p','InaccessiblePaths'],check=True)
for path in (Path('/var/lib/photo-enrichment'),Path('/var/lib/photo-enrichment/cricket'),Path('/var/lib/photo-enrichment/cricket/evidence')):
 stat=path.stat();print('path_permissions',str(path),oct(stat.st_mode&0o777),stat.st_uid,stat.st_gid)
subprocess.run(['journalctl','-u',unit,'-n','35','--no-pager','-o','cat'],check=True)
subprocess.run(['journalctl','-u','photo-enrichment-export.service','-n','12','--no-pager','-o','cat'],check=True)
"""


def main() -> None:
    """Read service diagnostics only; never restart or change concurrency here."""
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
        timeout=45,
    )


if __name__ == "__main__":
    main()
