"""Publish immutable, coherent PostgreSQL-to-Parquet generations (#217)."""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import shutil
import time
import uuid

import duckdb

from .postgres import TABLES, connect
from .store import sql_path

CONTEXT_TABLES = ("photo_context", "photo_place_cache")


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('w') as output:
        json.dump(value,output,sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent,os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


def export_snapshot(state: Path, prom: Path | None = None) -> dict:
    """Keep the previous manifest on any failure; readers resolve it exactly once."""
    root = state/'analytics'
    root.mkdir(parents=True,exist_ok=True)
    with (root/'export.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return {'skipped':True}
        started = time.time()
        generation = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]
        directory = root/'generations'/generation
        directory.mkdir(parents=True)
        result = dict(schema_version=1,generation=generation,directory=str(directory),tables={},captured_at=started)
        try:
            with duckdb.connect() as db:
                db.execute("SET threads=2; SET memory_limit='512MB'; LOAD postgres")
                service = os.environ.get('PHOTO_PG_SERVICE','photo_pipeline')
                if not service.replace('_','').isalnum(): raise ValueError('Invalid libpq service name')
                db.execute("SET pg_use_ctid_scan=false")
                db.execute(f"ATTACH 'service={service}' AS source (TYPE postgres, READ_ONLY, SCHEMA 'public', ISOLATION_LEVEL 'REPEATABLE READ')")
                db.execute('BEGIN')
                isolation = db.execute("SELECT * FROM postgres_query('source', $$SELECT current_setting('transaction_isolation') AS isolation,current_setting('transaction_read_only') AS read_only,extract(epoch FROM transaction_timestamp())::double precision$$)").fetchone()
                if isolation[:2] != ('repeatable read','on'): raise RuntimeError('Export isolation validation failed')
                result['captured_at'] = isolation[2]
                optional=[name for name in CONTEXT_TABLES if db.execute("SELECT * FROM postgres_query('source', $$SELECT to_regclass('public."+name+"') IS NOT NULL$$)").fetchone()[0]]
                for table in (*TABLES,'photo_jobs','enriched_media','album_duplicates',*optional):
                    target = directory/(table+'.parquet')
                    relation=f'source.public.{table}' if table!='album_duplicates' else "postgres_query('source', 'SELECT path FROM catalog.gphotos_album_dup')"
                    db.execute(f'COPY (SELECT * FROM {relation}) TO {sql_path(target)} (FORMAT parquet, COMPRESSION zstd)')
                    count = db.execute('SELECT count(*) FROM read_parquet(?)',[str(target)]).fetchone()[0]
                    expected = db.execute(f'SELECT count(*) FROM {relation}').fetchone()[0]
                    if count != expected: raise RuntimeError('Snapshot count mismatch')
                    with target.open('rb') as handle: os.fsync(handle.fileno())
                    result['tables'][table] = {'file':str(target),'rows':count,'bytes':target.stat().st_size}
                db.execute('COMMIT')
            descriptor = os.open(directory,os.O_RDONLY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
            result['published_at'] = time.time()
            result['duration_seconds'] = time.time()-started
            atomic_json(root/'current.json',result)
            prune_generations(root,generation)
            # Preserve the old six-table exports as recovery material; new readers
            # explicitly use the manifest. Do not repoint individual legacy files.
            with connect() as connection:
                connection.execute("INSERT INTO pipeline_state VALUES ('snapshot',%s,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()",[json.dumps(result)])
            if prom:
                temporary = prom.with_suffix('.prom.tmp')
                temporary.write_text('\n'.join([
                    '# HELP photo_snapshot_published_timestamp_seconds Last complete analytical generation',
                    '# TYPE photo_snapshot_published_timestamp_seconds gauge',
                    f'photo_snapshot_published_timestamp_seconds {result["published_at"]}',
                    '# HELP photo_snapshot_captured_timestamp_seconds PostgreSQL snapshot capture time',
                    '# TYPE photo_snapshot_captured_timestamp_seconds gauge',
                    f'photo_snapshot_captured_timestamp_seconds {result["captured_at"]}',
                    '# HELP photo_snapshot_export_seconds Duration of last successful export',
                    '# TYPE photo_snapshot_export_seconds gauge',
                    f'photo_snapshot_export_seconds {result["duration_seconds"]}',
                    '# HELP photo_snapshot_bytes Total Parquet bytes in the current generation',
                    '# TYPE photo_snapshot_bytes gauge',
                    f'photo_snapshot_bytes {sum(t["bytes"] for t in result["tables"].values())}',
                    '# HELP photo_snapshot_success Last export attempt succeeded',
                    '# TYPE photo_snapshot_success gauge','photo_snapshot_success 1',
                    '# HELP photo_pipeline_edge_info Durable queue and snapshot data flow',
                    '# TYPE photo_pipeline_edge_info gauge',
                    'photo_pipeline_edge_info{id="jobs-queue",source="photo_jobs",target="photo_queue"} 1',
                    'photo_pipeline_edge_info{id="export-analytics",source="photo_export",target="photo_analytics"} 1','']))
                temporary.chmod(0o644);temporary.replace(prom)
            return result
        except BaseException:
            if prom and prom.exists():
                temporary=prom.with_suffix('.prom.tmp')
                temporary.write_text(prom.read_text().replace('photo_snapshot_success 1','photo_snapshot_success 0'))
                temporary.chmod(0o644);temporary.replace(prom)
            raise


def prune_generations(root: Path, current: str) -> None:
    """Retain at least a day and three generations; never remove a pinned reader."""
    generations=sorted((root/'generations').iterdir(),key=lambda p:p.stat().st_mtime,reverse=True)
    for directory in generations[3:]:
        if directory.name==current or time.time()-directory.stat().st_mtime<86400:continue
        try:
            with (directory/'.readers').open('a') as lease:
                fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
                shutil.rmtree(directory)
        except (BlockingIOError,FileNotFoundError):continue


class SnapshotReader:
    """Hold a generation lease until the analytical connection closes."""
    def __init__(self,connection,lease):self.connection,self.lease=connection,lease
    def __getattr__(self,name):return getattr(self.connection,name)
    def close(self):
        try:self.connection.close()
        finally:self.lease.close()


def analytical_connection(state: Path):
    """Each request pins one immutable generation; never glob generations together."""
    root=(state/'analytics/generations').resolve()
    for _ in range(3):
        manifest = json.loads((state/'analytics/current.json').read_text())
        directory=Path(manifest['directory']).resolve()
        if not directory.is_relative_to(root):raise ValueError('Invalid generation path')
        try:
            lease=(directory/'.readers').open('a')
            fcntl.flock(lease,fcntl.LOCK_SH)
            if directory.exists():break
            lease.close()
        except FileNotFoundError:continue
    else:raise RuntimeError('Analytical generation changed while opening; retry')
    connection = duckdb.connect()
    connection.execute("SET threads=2; SET memory_limit='512MB'")
    for table,info in manifest['tables'].items():
        if table not in (*TABLES,'photo_jobs','enriched_media','album_duplicates',*CONTEXT_TABLES): raise ValueError('Invalid snapshot table')
        path = Path(info['file']).resolve()
        if not path.is_relative_to((state/'analytics/generations').resolve()): raise ValueError('Invalid snapshot path')
        connection.execute(f'CREATE VIEW {table} AS SELECT * FROM read_parquet({sql_path(path)})')
    return SnapshotReader(connection,lease),manifest
