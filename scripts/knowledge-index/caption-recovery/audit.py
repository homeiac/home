"""Check the frozen recovery cohort directly in Immich and update its local readback states."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import UUID

import process


def readback(rows: list[tuple]) -> dict:
    """One database snapshot. Only IDs and presence/match booleans leave Immich."""
    if not rows:
        raise ValueError('Empty caption recovery cohort')
    values = []
    for asset, _, answer in rows:
        text = json.loads(answer)['summary'] if answer else None
        # Hash equality avoids transporting private captions in either direction.
        checksum = "'" + hashlib.md5(text.encode()).hexdigest() + "'" if text else 'NULL::text'
        values.append(f"('{UUID(asset)}'::uuid,{checksum})")
    sql = """
        WITH cohort(id, expected) AS (VALUES """ + ','.join(values) + """)
        SELECT json_build_array(c.id, a.id IS NOT NULL,
            coalesce(md5(m.value->>'summary')=c.expected,false),
            coalesce(length(trim(m.value->>'summary'))>0,false),
            coalesce(length(trim(e.description))>0,false))
        FROM cohort c LEFT JOIN asset a ON a.id=c.id AND a."deletedAt" IS NULL
        LEFT JOIN asset_metadata m ON m."assetId"=a.id AND m.key='home.knowledge-index.v1'
        LEFT JOIN asset_exif e ON e."assetId"=a.id;
    """
    cmd = process.KUBE + ['deploy/immich-postgres', '--', 'psql', '-XqAt', '-v',
                          'ON_ERROR_STOP=1', '-U', 'immich', '-d', 'immich']
    lines = process.kubectl_output(cmd, 'BEGIN READ ONLY;' + sql + 'ROLLBACK;', 60).splitlines()
    report = {asset: flags for asset, *flags in map(json.loads, lines)}
    if set(report) != {asset for asset, _, _ in rows} or len(lines) != len(rows):
        raise ValueError('Incomplete or duplicated Immich readback')
    return report


def audit(db: sqlite3.Connection, record: bool) -> dict:
    rows = db.execute("""SELECT c.id,coalesce(w.state,'pending'),w.answer FROM cohort c LEFT JOIN work w USING(id)
                         WHERE c.cohort='caption'""").fetchall()
    result = readback(rows)
    totals = Counter(dict.fromkeys(('cohort','asset_present','missing_caption','verified','already_described',
                                    'owned_summary','visible_description'), 0))
    with db:
        for asset, previous, _ in rows:
            exists, exact, owned, visible = result[asset]
            totals['cohort'] += 1
            totals['asset_present'] += exists
            totals['owned_summary'] += owned
            totals['visible_description'] += visible
            if exact:
                state, reason = 'verified', None
            elif owned or visible:
                state, reason = 'already_described', 'existing_caption_read_back'
            else:
                totals['missing_caption'] += 1
                if previous not in ('verified', 'already_described'):
                    continue
                state, reason = 'error', 'previous_caption_missing' if exists else 'asset_missing'
            if state in ('verified', 'already_described'):
                totals[state] += 1
            if record and previous != state:
                db.execute('UPDATE work SET state=?,reason=? WHERE id=?', (state, reason, asset))
    return dict(totals)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger', type=Path)
    parser.add_argument('--record', action='store_true', help='Record checked states under the recovery writer lock')
    args = parser.parse_args()
    path = args.ledger.resolve(strict=True)
    with path.with_suffix('.lock').open('r') as lock:
        if args.record:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with sqlite3.connect(path.as_uri() + ('?mode=rw' if args.record else '?mode=ro'), uri=True) as db:
            print(json.dumps(audit(db, args.record), sort_keys=True))


if __name__ == '__main__':
    main()
