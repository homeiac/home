"""Operate the host's authoritative cricket worker using the existing private deployment."""

import argparse
import json
import shlex
import subprocess
from pathlib import Path

REMOTE = r"""
import json,subprocess,sys
from pathlib import Path
packet=json.load(sys.stdin)
root=Path('/opt/photo-enrichment/gui').resolve()
state=Path('/local-3TB-backup/photo-enrichment/cricket')
command=[str(root/'venv/bin/python'),'-m','cricket.ops','--ledger',str(state/'ledger.sqlite3'),'--policy',str(state/'policy.json'),packet['command']]
if packet.get('backend'):command+=['--backend',packet['backend']]
if packet.get('workers') is not None:command+=['--workers',str(packet['workers'])]
if packet.get('version'):command+=['--version',packet['version']]
if packet['command']=='scope':
    sys.path.insert(0,str(root))
    from cricket.prepare import save_private
    from cricket.ledger import Ledger
    allowed=packet.get('assets')
    if allowed is not None:
        if not isinstance(allowed,list) or not all(isinstance(a,str) for a in allowed):raise ValueError('Invalid scope')
        with Ledger(state/'ledger.sqlite3').connect() as db:known={r[0] for r in db.execute('SELECT id FROM assets')}
        if not set(allowed)<=known:raise ValueError('Unknown pilot assets')
    config=json.loads((state/'policy.json').read_text());config['allowed_assets']=allowed
    save_private(state/'policy.json',config)
    print(json.dumps({'scope_assets':len(allowed) if allowed is not None else 'album'}))
elif packet['command']=='publish':subprocess.run(['systemctl','start','--no-block','photo-enrichment-export.service'],check=True)
else:subprocess.run(command,cwd=root,check=True)
if packet['command'] in ('status','publish'):
    status=state/'worker/status.json'
    if status.exists():print(status.read_text())
    manifest=state.parent/'analytics/current.json'
    if manifest.exists():
        snapshot=json.loads(manifest.read_text());table=snapshot.get('tables',{}).get('cricket_highlights')
        print(json.dumps({'search_publication':{'published_at':snapshot.get('published_at'),'rows':table.get('rows') if table else None}}))
    worker='cricket-highlights-ssd' if (state/'ledger.sqlite3').resolve().parent!=state else 'cricket-highlights'
    for name in ('photo-enrichment-gui',worker,'photo-enrichment-export','knowledge-index-enrich','knowledge-index-audio-story'):
        print(name,subprocess.run(['systemctl','is-active',name],text=True,capture_output=True).stdout.strip())
"""


def main() -> None:
    """Keep all state changes on the host, never copy a stale local ledger back."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument(
        "command",
        choices=[
            "status",
            "pause",
            "resume",
            "workers",
            "retry",
            "publish",
            "scope",
            "reanalyze",
        ],
    )
    parser.add_argument("--backend")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--version")
    parser.add_argument(
        "--scope-file",
        type=Path,
        help="Private JSON array of pilot asset IDs; omit to allow the album",
    )
    args = parser.parse_args()
    packet = vars(args).copy()
    packet.pop("scope_file")
    if args.command == "scope":
        packet["assets"] = (
            json.loads(args.scope_file.read_text()) if args.scope_file else None
        )
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
        input=json.dumps(packet),
        text=True,
        timeout=45,
        check=True,
    )


if __name__ == "__main__":
    main()
