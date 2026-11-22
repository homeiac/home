#!/usr/bin/env python3
"""Inspect uncovered canonical media without changing sources or submitting work.

Run with the existing Piglet venv. The private manifest stays on that host;
console output uses ledger IDs rather than filenames or photo metadata.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import duckdb

ROOT = Path('/local-3TB-backup')
LIBRARY = ROOT / 'gphotos/library'
REPORT = Path('/var/tmp/caption-gaps-20261122.json')
sys.path.insert(0, '/opt/knowledge-index/enrichers')
from media_summary import jpeg_frame, video_duration, VIDEO_EXTS


def main() -> None:
    os.umask(0o077)
    with duckdb.connect(str(ROOT / 'knowledge-index/knowledge.duckdb'), read_only=True) as db:
        db.execute('SET threads=2')
        rows = db.execute("""WITH saved AS (
            SELECT path,size_bytes FROM media_summaries WHERE source='gphotos' AND status='ok'
            UNION SELECT source_path,size_bytes FROM read_parquet(?,union_by_name=true) WHERE state='ok')
            SELECT m.path,m.size_bytes,lower(m.ext) FROM gphotos_media m
            ANTI JOIN saved s USING(path,size_bytes)
            WHERE m.kind='media' AND NOT EXISTS (SELECT 1 FROM gphotos_album_dup d WHERE d.path=m.path)
            ORDER BY m.path""", [str(ROOT / 'photo-enrichment/luna-backfill/luna_codex_captions/*.parquet')]).fetchall()
    ledger = sqlite3.connect(f'file:{ROOT}/photo-enrichment/luna-backfill/luna-ledger.sqlite3?mode=ro', uri=True)
    results = []
    for path, size, ext in rows:
        file = LIBRARY / path
        job = ledger.execute('SELECT id,state,result FROM jobs WHERE path=? AND size_bytes=?', [path,size]).fetchone()
        info = {'item': hashlib.sha256(path.encode()).hexdigest()[:12], 'ext':ext, 'indexed_bytes':size,
                'job_id':job[0] if job else None, 'luna_state':job[1] if job else None,
                'failure':json.loads(job[2] or '{}').get('failure') if job else None,
                'exists':file.exists()}
        if file.exists():
            info['actual_bytes'] = file.stat().st_size
            with file.open('rb') as stream:
                info['header_hex'] = stream.read(16).hex()
            probe = subprocess.run(['ffprobe','-v','error','-show_entries',
                'format=format_name,duration:stream=codec_type,codec_name,width,height,duration',
                '-of','json',str(file)], capture_output=True,text=True,timeout=60)
            info['probe'] = json.loads(probe.stdout or '{}')
            info['probe_error'] = probe.stderr.replace(str(file),'<item>').replace(file.name,'<item>')[:500]
            try:
                frame = jpeg_frame(str(file), 0 if ext in VIDEO_EXTS else None)
                info['first_frame_bytes'] = len(frame)
            except Exception as exc:
                info['decode_error'] = str(exc).replace(str(file),'<item>').replace(file.name,'<item>')[:500]
        print(json.dumps(info, sort_keys=True),flush=True)
        results.append({'path':path, 'size_bytes':size, **info})
    if REPORT.exists():
        REPORT.with_suffix('.previous.json').write_bytes(REPORT.read_bytes())
    REPORT.write_text(json.dumps(results,indent=2))
    print('Private diagnostic manifest:',str(REPORT),'items:',len(results))


if __name__ == '__main__':
    main()
