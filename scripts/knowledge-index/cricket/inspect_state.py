"""Read the deployed Cricket authority, policy and rollback inventory without mutation."""

import argparse
import json
import logging
import shlex
import subprocess
from pathlib import Path

from .prepare import save_private

REMOTE = r"""
import hashlib,json,sqlite3,subprocess,time
from contextlib import closing
from pathlib import Path
root=Path('/opt/photo-enrichment/gui').resolve()
state=Path('/local-3TB-backup/photo-enrichment/cricket')
ledger=(state/'ledger.sqlite3').resolve()
policy=json.loads((state/'policy.json').read_text())
result={'captured_at':time.time(),'release':str(root),'ledger':str(ledger),
        'policy':{'enabled':policy['enabled'],'analysis_version':policy.get('analysis_version','cricket-v1'),
                  'scope_assets':len(policy['allowed_assets']) if policy.get('allowed_assets') is not None else 'album',
                  'backends':{k:{f:v[f] for f in ('workers','max_workers')} for k,v in policy['backends'].items()}},
        'policy_sha256':hashlib.sha256((state/'policy.json').read_bytes()).hexdigest()}
with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    result['assets']=dict(db.execute('SELECT kind,count(*) FROM assets GROUP BY kind'))
    result['jobs']=[dict(version=v,state=s,count=n) for v,s,n in db.execute('SELECT version,state,count(*) FROM jobs GROUP BY version,state')]
    result['review_states']=dict(db.execute('SELECT review_state,count(*) FROM events GROUP BY review_state'))
    result['correction_revisions']=db.execute('SELECT count(*) FROM revisions').fetchone()[0]
    db.rollback()
result['source_hashes']={}
for name in ('cricket/worker.py','cricket/ledger.py','cricket/openlabel.py','photo_enrichment/server.py'):
    file=root/name
    result['source_hashes'][name]=hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
result['rollback_directories']=[str(p) for p in sorted(Path('/opt/photo-enrichment/backups').glob('cricket-*'))[-5:] if p.is_dir()]
result['ledger_backups']=[p.name for p in sorted((ledger.parent/'backups').glob('*.sqlite3'))[-5:]]
result['units']={}
for unit in ('cricket-highlights-ssd','photo-enrichment-gui','knowledge-index-enrich','knowledge-index-audio-story'):
    result['units'][unit]=subprocess.run(['systemctl','is-active',unit],text=True,capture_output=True).stdout.strip()
print(json.dumps(result))
"""


def main() -> None:
    """Save a private, aggregate-only receipt using the inventory-confirmed host."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    response = subprocess.run(
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
        capture_output=True,
        text=True,
        timeout=45,
    )
    result = json.loads(response.stdout)
    save_private(args.output, result)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
