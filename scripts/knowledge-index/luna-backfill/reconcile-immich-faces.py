"""Carry saved names across only when the boxes identify the same face."""
import argparse
from collections import Counter
from itertools import groupby
import json
import math
import os
from pathlib import Path
import sqlite3
import time

MIN_OVERLAP = 0.50
MIN_MARGIN = 0.20
STATE = Path('/local-3TB-backup/photo-enrichment')
SNAPSHOT = STATE / 'luna-backfill/immich-context.sqlite3'
METRICS = Path('/var/lib/prometheus/node-exporter/photo_immich_faces.prom')

ACTIVE = """
    FROM faces f JOIN face_scans fs ON (f.path,f.size_bytes,f.mtime_ns,f.model)=
        (fs.path,fs.size_bytes,fs.mtime_ns,fs.model)
    WHERE EXISTS (SELECT 1 FROM catalog.gphotos_media m
        WHERE m.path=f.path AND m.size_bytes=f.size_bytes AND m.kind='media'
        AND m.ext IN ('jpg','jpeg','heic','png','gif','webp'))
    AND NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=f.path)
"""
REJECTED = 'EXISTS (SELECT 1 FROM rejected_matches r WHERE r.face_id=f.id)'
UPDATE = f"""
    UPDATE faces f SET person=m.person,label_source='immich',updated_at=clock_timestamp()
    FROM immich_face_matches m, face_scans fs
    WHERE f.id=m.id AND f.updated_at IS NOT DISTINCT FROM m.revision AND f.person IS NULL
      AND f.label_source IS DISTINCT FROM 'user_cleared' AND NOT {REJECTED}
      AND (f.path,f.size_bytes,f.mtime_ns,f.model)=(fs.path,fs.size_bytes,fs.mtime_ns,fs.model)
"""


def usable(box):
    return (box and len(box) == 4 and
            all(x is not None and math.isfinite(x) and 0 <= x <= 1 for x in box) and
            box[0] < box[2] and box[1] < box[3])


def iou(a, b):
    intersection = (max(0, min(a[2], b[2]) - max(a[0], b[0])) *
                    max(0, min(a[3], b[3]) - max(a[1], b[1])))
    return intersection / ((a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection)


def best(scores):
    """Require overlap and clear separation from the next candidate."""
    ranked = sorted(enumerate(scores), key=lambda entry: entry[1], reverse=True)
    if not ranked or ranked[0][1] < MIN_OVERLAP:
        return None
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < MIN_MARGIN:
        return None
    return ranked[0][0]


def match(local, immich):
    """Return names for mutual, unique box matches, including unnamed competitors."""
    remote = [(name, box) for name, *box in immich if usable(box)]
    if not remote or not local:
        return {}
    scores = [[iou(a, b) if usable(a) else 0.0 for _, b in remote] for a in local]
    forward = [best(row) for row in scores]
    reverse = [best(column) for column in zip(*scores)]
    return {i: remote[j][0] for i, j in enumerate(forward)
            if j is not None and reverse[j] == i and remote[j][0] and len(remote[j][0]) <= 200}


def reconcile(connection, snapshot, apply):
    count = Counter(active=0, unreviewed=0, eligible=0, agree=0, disagree=0,
                    already_imported=0, protected=0, applied=0)
    candidates = []
    with sqlite3.connect(snapshot.resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as source:
        with connection.transaction():
            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            with connection.cursor(name='immich_local_faces') as cursor:
                cursor.execute(f"""SELECT f.path,f.size_bytes,f.id,f.box,f.person,f.label_source,
                    f.updated_at,{REJECTED} {ACTIVE} ORDER BY f.path,f.size_bytes,f.id""")
                for key, group in groupby(cursor, key=lambda row: row[:2]):
                    rows = list(group)
                    count['active'] += len(rows)
                    count['unreviewed'] += sum(row[4] is None for row in rows)
                    count['already_imported'] += sum(row[5] == 'immich' for row in rows)
                    entry = source.execute('SELECT metadata FROM context WHERE path=? AND size=?', key).fetchone()
                    if not entry:
                        continue
                    boxes = json.loads(entry[0]).get('faces', ())
                    for i, name in match([row[3] for row in rows], boxes).items():
                        _, _, face_id, _, current, label_source, revision, rejected = rows[i]
                        if label_source == 'user' and current:
                            count['agree' if current.casefold() == name.casefold() else 'disagree'] += 1
                        elif current is None and label_source != 'user_cleared' and not rejected:
                            candidates.append((face_id, revision, name))
                        elif current is None:
                            count['protected'] += 1
    count['eligible'] = len(candidates)
    if apply and candidates:
        with connection.transaction():
            connection.execute("SET LOCAL lock_timeout='10s'")
            connection.execute("""CREATE TEMP TABLE immich_face_matches
                (id text PRIMARY KEY,revision timestamp,person text) ON COMMIT DROP""")
            with connection.cursor().copy('COPY immich_face_matches FROM STDIN') as copy:
                for candidate in candidates:
                    copy.write_row(candidate)
            count['applied'] = connection.execute(UPDATE).rowcount
    return count


def publish(count):
    values = {**count, 'unreviewed': count['unreviewed'] - count['applied'],
              'imported': count['already_imported'] + count['applied']}
    tmp = METRICS.with_suffix('.tmp')
    tmp.write_text('# TYPE photo_immich_face_reconciliation gauge\n' + ''.join(
        f'photo_immich_face_reconciliation{{result="{key}"}} {value}\n'
        for key, value in values.items()) + f'photo_immich_context_timestamp_seconds {time.time()}\n'
        'photo_pipeline_edge_info{id="immich-context",source="immich_metadata",target="immich_named_faces"} 1\n'
        'photo_pipeline_edge_info{id="immich-review",source="immich_named_faces",target="photo_export"} 1\n'
        'photo_pipeline_edge_info{id="immich-place",source="immich_metadata",target="photo_search"} 1\n')
    tmp.chmod(0o644)
    tmp.replace(METRICS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    import psycopg
    with psycopg.connect(service=os.environ.get('PHOTO_PG_SERVICE', 'photo_pipeline'),
                         autocommit=True, connect_timeout=10) as pg:
        count = reconcile(pg, args.snapshot, args.apply)
    print(json.dumps(count, sort_keys=True))
    if args.apply:
        publish(count)


if __name__ == '__main__':
    main()
