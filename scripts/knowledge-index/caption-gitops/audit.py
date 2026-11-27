#!/usr/bin/env python3
"""Read-only Parquet audit across a rollout/restart; never print photo paths.

Run with the host's existing venv: audit.py snapshot|verify BASELINE.json.
The snapshot records immutable completed batch filenames, not private content.
"""
import argparse
import datetime
import json
from pathlib import Path

import duckdb

INDEX = Path('/local-3TB-backup/knowledge-index')
KEY = 'source, path, size_bytes, enricher'


def main() -> None:
    """Compare new successful rows with all previously saved successful keys."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('snapshot', 'verify'))
    parser.add_argument('baseline', type=Path)
    args = parser.parse_args()
    files = sorted(str(p) for p in (INDEX / 'summaries').glob('*/*.parquet'))
    if args.action == 'snapshot':
        with args.baseline.open('x') as stream:
            json.dump({'files': files, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat()}, stream)
        args.baseline.chmod(0o600)
        print(json.dumps({'baseline_files': len(files), 'baseline': str(args.baseline)}))
        return
    baseline = json.loads(args.baseline.read_text())
    old = baseline['files']
    if not set(old).issubset(files):
        raise RuntimeError('Baseline files disappeared; cannot make an exact comparison')
    new = sorted(set(files) - set(old))
    if not new:
        print(json.dumps({'new_files': 0, 'new_successful_rows': 0, 'since': baseline['at']}))
        return
    con = duckdb.connect(config={'threads': 2})
    con.read_parquet(new, union_by_name=True).create_view('new_rows')
    con.execute('CREATE VIEW fresh AS SELECT ' + KEY + " FROM new_rows WHERE status = 'ok'")
    total = con.execute('SELECT count(*) FROM fresh').fetchall()[0][0]
    unique = con.execute('SELECT count(*) FROM (SELECT DISTINCT ' + KEY + ' FROM fresh)').fetchall()[0][0]
    prior = 0
    if old:
        con.read_parquet(old, union_by_name=True).create_view('old_rows')
        prior = con.execute("SELECT count(*) FROM fresh SEMI JOIN (SELECT * FROM old_rows WHERE status = 'ok') USING (" + KEY + ')').fetchall()[0][0]
    result = {'since': baseline['at'], 'new_files': len(new), 'new_successful_rows': total,
              'new_unique_items': unique, 'duplicates_within_new_rows': total - unique,
              'duplicates_of_previously_completed_items': prior,
              'last_batch_saved_at': datetime.datetime.fromtimestamp(
                  max(Path(p).stat().st_mtime for p in new), datetime.timezone.utc).isoformat(),
              'new_errors': con.execute("SELECT count(*) FROM new_rows WHERE status <> 'ok'").fetchall()[0][0]}
    print(json.dumps(result, sort_keys=True))
    if prior or total != unique:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
