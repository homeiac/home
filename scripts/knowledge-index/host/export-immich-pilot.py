#!/usr/bin/env python3
"""Export a bounded, immutable migration sample; never modify source records (#217)."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile

import psycopg
from psycopg.rows import dict_row
from PIL import Image, ImageOps


def main() -> None:
    """Copy diverse photos and their authoritative metadata into a private archive."""
    os.umask(0o077)
    root = Path('/local-3TB-backup/photo-enrichment/migrations/immich-pilot')
    root.mkdir(parents=True, exist_ok=True)
    if (root/'manifest.json').exists():
        print('Existing immutable pilot export retained')
        return
    library = Path('/local-3TB-backup/gphotos/library').resolve()
    os.environ.update(PGSERVICEFILE='/etc/photo-enrichment/pg_service.conf',
                      PGPASSFILE='/etc/photo-enrichment/pgpass')
    samples = json.loads(Path('/local-3TB-backup/photo-enrichment/benchmarks/bonsai-27b/samples.json').read_text())
    paths = [s['path'] for s in samples['samples']]
    records = []
    with psycopg.connect(service='photo_pipeline', row_factory=dict_row) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        db.execute("SET LOCAL statement_timeout='30s'")
        paths += [r['path'] for r in db.execute("SELECT DISTINCT ON (person) path FROM faces WHERE label_source='user' AND person IS NOT NULL ORDER BY person, path LIMIT 8")]
        paths += [r['path'] for r in db.execute('SELECT path FROM group_members ORDER BY group_id,path LIMIT 2')]
        for path in dict.fromkeys(paths):
            source = (library/path).resolve()
            if not source.is_relative_to(library) or not source.is_file() or source.stat().st_size > 25*1024**2:
                continue
            if source.suffix.lower() not in {'.jpg','.jpeg','.png','.webp'}:
                continue
            key = hashlib.sha256(path.encode()).hexdigest()
            destination = root/(key+source.suffix.lower())
            shutil.copy2(source, destination)
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            with Image.open(source) as image:
                size = ImageOps.exif_transpose(image).size
            metadata = db.execute('SELECT * FROM enriched_media WHERE path=%s', [path]).fetchone()
            faces = db.execute('SELECT * FROM faces WHERE path=%s AND size_bytes=%s', [path,source.stat().st_size]).fetchall()
            groups = db.execute('SELECT g.* FROM photo_groups g JOIN group_members m ON m.group_id=g.id WHERE m.path=%s', [path]).fetchall()
            context = db.execute('SELECT status,summary,tags,model,context FROM photo_context WHERE path=%s', [path]).fetchone()
            records.append(dict(key=key,filename=destination.name,source_path=path,sha256=digest,
                                size_bytes=source.stat().st_size,oriented_size=size,
                                metadata=metadata,faces=faces,groups=groups,context=context))
    (root/'manifest.json').write_text(json.dumps(dict(version=1,records=records), default=str, indent=2))
    archive = root.parent/'immich-pilot.tar'
    with tarfile.open(archive, 'w') as output:
        for file in root.iterdir():
            output.add(file, arcname=file.name)
    print(json.dumps(dict(photos=len(records), confirmed_faces=sum(f['label_source']=='user' and bool(f['person']) for r in records for f in r['faces']), archive_bytes=archive.stat().st_size)))


if __name__ == '__main__':
    main()
