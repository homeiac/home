"""Refresh the private Luna metadata snapshot using Immich's completed work."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile

ROOT = Path('/local-3TB-backup/photo-enrichment/luna-backfill')
PREFIX = '/external/gphotos/'
SQL = """
WITH assets AS (
    SELECT a.id,a."ownerId",a."originalPath",e."fileSizeInByte",e.city,e.state,e.country
    FROM asset a JOIN asset_exif e ON e."assetId"=a.id
    WHERE a."isExternal" AND NOT a."isOffline" AND a."deletedAt" IS NULL
      AND a."originalPath" LIKE '/external/gphotos/%' AND e."fileSizeInByte">0
      AND left(a.id::text,1)='{shard}'
), names AS (
    SELECT f."assetId", array_agg(DISTINCT trim(p.name) ORDER BY trim(p.name)) AS people
    FROM assets a JOIN asset_face f ON f."assetId"=a.id
    JOIN person p ON p."personGroupId"=f."personGroupId" AND p."ownerId"=a."ownerId"
    WHERE f."deletedAt" IS NULL AND f."isVisible" AND NOT p."isHidden" AND trim(p.name)<>''
    GROUP BY f."assetId"
)
SELECT json_build_array(substr(a."originalPath",{prefix_length}),a."fileSizeInByte",a.city,a.state,a.country,
                        coalesce(n.people,ARRAY[]::text[]))
FROM assets a LEFT JOIN names n ON n."assetId"=a.id
"""


def rows(shard):
    call = ['qm','guest','exec','105','--timeout','90','--','/usr/local/bin/k3s','kubectl',
            '-n','immich-pilot','exec','deploy/immich-postgres','--','psql','-XAt','-v','ON_ERROR_STOP=1',
            '-U','immich','-d','immich','-c',SQL.format(shard=shard,prefix_length=len(PREFIX)+1)]
    try:
        result = json.loads(subprocess.check_output(call, timeout=100, stderr=subprocess.DEVNULL))
        if result.get('exitcode') or result.get('out-truncated') or not result.get('exited'):
            raise ValueError
        for line in result.get('out-data','').splitlines():
            path,size,city,state,country,names = json.loads(line)
            yield path,size,json.dumps(dict(
                place={k:v for k,v in dict(city=city,state=state,country=country).items() if v},
                people=names), ensure_ascii=False)
    except (ValueError, KeyError, subprocess.SubprocessError):
        raise RuntimeError(f'Immich metadata export failed for shard {shard}') from None


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(dir=ROOT, prefix='.immich-context-') as folder:
        tmp=Path(folder)/'context.sqlite3'
        with sqlite3.connect(tmp) as db:
            db.execute('CREATE TEMP TABLE raw(path TEXT,size INTEGER,metadata TEXT)')
            for shard in '0123456789abcdef':
                db.executemany('INSERT INTO raw VALUES (?,?,?)', rows(shard))
            db.execute('CREATE TABLE context(path TEXT,size INTEGER,metadata TEXT,PRIMARY KEY(path,size)) WITHOUT ROWID')
            db.execute('INSERT INTO context SELECT path,size,metadata FROM raw GROUP BY path,size HAVING count(*)=1')
            count,places,people=db.execute("""SELECT count(*),sum(json_extract(metadata,'$.place')<>'{}'),
              sum(json_array_length(json_extract(metadata,'$.people'))>0) FROM context""").fetchone()
            if not count:
                raise RuntimeError('No matching Immich assets. Retained previous snapshot')
        tmp.replace(ROOT/'immich-context.sqlite3')
    print(f'Immich snapshot: {count} unique assets, {places} with place labels, {people} with visible named people')


if __name__=='__main__':
    main()
