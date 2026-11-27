"""Operate the host's authoritative cricket worker using the existing private deployment."""

import argparse
import json
import shlex
import subprocess

REMOTE = r"""
import json,subprocess,sys
from pathlib import Path
packet=json.load(sys.stdin)
root=Path('/opt/photo-enrichment/gui').resolve()
state=Path('/local-3TB-backup/photo-enrichment/cricket')
command=[str(root/'venv/bin/python'),'-m','cricket.ops','--ledger',str(state/'ledger.sqlite3'),'--policy',str(state/'policy.json'),packet['command']]
if packet.get('backend'):command+=['--backend',packet['backend']]
if packet.get('workers') is not None:command+=['--workers',str(packet['workers'])]
subprocess.run(command,cwd=root,check=True)
if packet['command']=='status':
    status=state/'worker/status.json'
    if status.exists():print(status.read_text())
    manifest=state.parent/'analytics/current.json'
    if manifest.exists():
        snapshot=json.loads(manifest.read_text());table=snapshot.get('tables',{}).get('cricket_highlights')
        print(json.dumps({'search_publication':{'published_at':snapshot.get('published_at'),'rows':table.get('rows') if table else None}}))
    for name in ('photo-enrichment-gui','cricket-highlights','knowledge-index-enrich','knowledge-index-audio-story'):
        print(name,subprocess.run(['systemctl','is-active',name],text=True,capture_output=True).stdout.strip())
"""


def main() -> None:
    """Keep all state changes on the host, never copy a stale local ledger back."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument(
        "command", choices=["status", "pause", "resume", "workers", "retry"]
    )
    parser.add_argument("--backend")
    parser.add_argument("--workers", type=int)
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
        input=json.dumps(vars(args)),
        text=True,
        timeout=45,
        check=True,
    )


if __name__ == "__main__":
    main()
