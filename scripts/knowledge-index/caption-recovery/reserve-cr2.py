"""Temporarily reserve this recovery's in-flight CR2s before enabling catalog processing."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time


def main() -> None:
    """Publish only relative paths and sizes to a private, expiring file on the index host."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger', type=Path)
    args = parser.parse_args()
    with sqlite3.connect(args.ledger.resolve().as_uri() + '?mode=ro', uri=True) as db:
        rows = db.execute("""SELECT substr(c.path,length('/external/gphotos/')+1),c.size
          FROM cohort c JOIN work w USING(id) WHERE c.cohort='caption'
          AND c.path LIKE '/external/gphotos/%' AND lower(c.path) LIKE '%.cr2'
          AND w.state IN ('pending','generated','queued')""").fetchall()
    claims = dict(expires=int(time.time()) + 86400, items=[dict(path=p,size_bytes=s) for p,s in rows])
    subprocess.run(['ssh','-o','BatchMode=yes',os.environ['CB_HOST'],
        'set -eu; umask 077; cd /local-3TB-backup/knowledge-index; '
        'tmp=$(mktemp .caption-claims.XXXXXX); trap \'rm -f "$tmp"\' EXIT; '
        'cat > "$tmp"; mv "$tmp" _caption_reservations.json'],
        input=json.dumps(claims), text=True, check=True)
    print(f'Reserved {len(rows)} source revisions for up to 24 hours')


if __name__ == '__main__':
    main()
