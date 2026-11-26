"""PostgreSQL authority for the existing extractors and review application (#217).

DuckDB reads immutable Parquet for gallery queries and analytical snapshots.
No live service opens the legacy writable enrichment.duckdb file.
"""
import datetime as dt
from contextlib import contextmanager
import copy
import json
import logging
import os
from pathlib import Path
import threading
import time
import uuid
from zoneinfo import ZoneInfo

import duckdb
import psycopg
from psycopg import sql

from .faces import MODEL_ID
from .metadata import VERSION, contained, read_metadata
from .metrics import Metrics
from .store import Store, SCHEMA_SQL, MEDIA_VIEW_SQL

TABLES = ('extracted', 'photo_groups', 'group_members', 'faces', 'face_scans',
          'rejected_matches', 'annotation_history', 'worker_attempts')
CATALOG = ('gphotos_media', 'gphotos_sidecars', 'gphotos_album_dup', 'media_summaries')
JOBS_SQL = """
CREATE TABLE IF NOT EXISTS worker_attempts (
 path varchar PRIMARY KEY, size_bytes bigint, version varchar, model varchar,
 timezone varchar, attempts integer, retry_after double precision);
CREATE TABLE IF NOT EXISTS photo_jobs (
 path varchar PRIMARY KEY, size_bytes bigint NOT NULL, version varchar NOT NULL,
 model varchar NOT NULL, timezone varchar NOT NULL, status varchar NOT NULL DEFAULT 'ready'
 CHECK(status IN ('ready','running','retry','done')), attempts integer NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT now(), lease_until timestamptz,
 claim varchar, enqueued_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
 last_error varchar);
CREATE INDEX IF NOT EXISTS photo_jobs_ready ON photo_jobs(status,available_at);
CREATE TABLE IF NOT EXISTS migration_log (
 id varchar PRIMARY KEY, counts jsonb NOT NULL, imported_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS pipeline_state (
 key varchar PRIMARY KEY, value jsonb NOT NULL, updated_at timestamptz DEFAULT now());
"""


class Connection:
    """Small parameter adapter for the shared, portable review queries."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        from .telemetry import get_telemetry,query_attributes
        with get_telemetry().stage('db.query',**query_attributes(statement)):
            return self.connection.execute(statement.replace('%', '%%').replace('?', '%s'), parameters)

    def executemany(self, statement, parameters):
        with self.connection.cursor() as cursor:
            cursor.executemany(statement.replace('%', '%%').replace('?', '%s'), parameters)

    def close(self):
        self.connection.close()


def connect():
    """Credentials stay in libpq service/pass files, never SQL or application logs."""
    return psycopg.connect(service=os.environ.get('PHOTO_PG_SERVICE', 'photo_pipeline'),
                           autocommit=True, connect_timeout=10)


def initialize(connection) -> None:
    """Create additive application tables inside the dedicated photo database."""
    with connection.transaction():
        connection.execute(SCHEMA_SQL.replace('DOUBLE', 'DOUBLE PRECISION'))
        connection.execute(JOBS_SQL)
        connection.execute('CREATE SCHEMA IF NOT EXISTS catalog')


def copy_table(source, connection, name: str, target: str, replace: bool = False) -> int:
    """Stream DuckDB rows into typed PostgreSQL tables without changing identities."""
    columns = source.execute(f'DESCRIBE SELECT * FROM {name}').fetchall()
    types = {'DOUBLE': 'double precision', 'FLOAT': 'real', 'UBIGINT': 'numeric(20)',
             'UINTEGER': 'bigint', 'UTINYINT': 'smallint', 'USMALLINT': 'integer',
             'TIMESTAMP WITH TIME ZONE': 'timestamptz', 'TIMESTAMP_NS': 'timestamp'}
    definition = ','.join('"'+c[0].replace('"','""')+'" '+types.get(c[1], c[1]).replace('DOUBLE[]','double precision[]') for c in columns)
    target_sql = sql.SQL('.').join(sql.Identifier(n) for n in target.split('.'))
    connection.execute(sql.SQL('CREATE TABLE IF NOT EXISTS {} (').format(target_sql) + sql.SQL(definition+')'))
    if replace:
        connection.execute(sql.SQL('DELETE FROM {}').format(target_sql))
    names = sql.SQL(',').join(sql.Identifier(c[0]) for c in columns)
    count = 0
    with connection.cursor() as cursor, cursor.copy(sql.SQL('COPY {} ({}) FROM STDIN').format(target_sql, names)) as copy:
        result = source.execute(f'SELECT * FROM {name}')
        while rows := result.fetchmany(1000):
            for row in rows:
                copy.write_row(row)
            count += len(rows)
    return count


def refresh_catalog(connection, index: Path) -> dict:
    """Import the existing Parquet-backed catalog; transactional replacement for UI."""
    with duckdb.connect(str(index/'knowledge.duckdb'), read_only=True) as source:
        with connection.transaction():
            connection.execute('SELECT pg_advisory_xact_lock(217,1)')
            counts = {name: copy_table(source, connection, name, 'catalog.'+name, True) for name in CATALOG}
            connection.execute('CREATE INDEX IF NOT EXISTS media_path ON catalog.gphotos_media(path)')
            connection.execute('CREATE INDEX IF NOT EXISTS sidecar_path ON catalog.gphotos_sidecars(path)')
            connection.execute('CREATE INDEX IF NOT EXISTS album_path ON catalog.gphotos_album_dup(path)')
            connection.execute('CREATE INDEX IF NOT EXISTS summary_path ON catalog.media_summaries(path,created_at DESC)')
            view = MEDIA_VIEW_SQL.replace('TEMP VIEW', 'VIEW').replace(
                "SELECT * FROM catalog.media_summaries WHERE status='ok'\n                QUALIFY row_number() OVER (PARTITION BY path ORDER BY created_at DESC, enricher DESC)=1",
                "SELECT DISTINCT ON (path) * FROM catalog.media_summaries WHERE status='ok' ORDER BY path, created_at DESC, enricher DESC")
            if not connection.execute("SELECT to_regclass('public.enriched_media')").fetchone()[0]:
                connection.execute(view)
            connection.execute("INSERT INTO pipeline_state VALUES ('catalog',%s,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()", [json.dumps(counts)])
    return counts


def migrate(connection, index: Path, state: Path) -> dict:
    """One atomic import from a quiesced legacy DB, including zero-face/retry state.

    The caller must stop the old worker and make a backup first. The ledger makes
    reruns safe and a nonempty destination without a ledger is rejected.
    """
    initialize(connection)
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(217,2)')
        existing = connection.execute("SELECT counts FROM migration_log WHERE id='legacy-duckdb-v1'").fetchone()
        if existing:
            return existing[0]
        if any(connection.execute(sql.SQL('SELECT EXISTS(SELECT 1 FROM {})').format(sql.Identifier(t))).fetchone()[0] for t in TABLES):
            raise RuntimeError('Destination is nonempty without a migration ledger; refusing to overwrite')
        counts = {}
        with duckdb.connect(str(state/'enrichment.duckdb'), read_only=True) as source:
            present = {r[0] for r in source.execute('SHOW TABLES').fetchall()}
            for table in TABLES:
                counts[table] = copy_table(source, connection, table, table) if table in present else 0
                actual = connection.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
                if actual != counts[table]:
                    raise RuntimeError('Migration count mismatch: '+table)
        refresh_catalog(connection, index)
        connection.execute('CREATE INDEX IF NOT EXISTS faces_path ON faces(path,size_bytes,mtime_ns)')
        connection.execute('CREATE INDEX IF NOT EXISTS faces_person ON faces(person)')
        connection.execute("INSERT INTO migration_log(id,counts) VALUES ('legacy-duckdb-v1',%s)", [json.dumps(counts)])
    return counts


class PostgresStore(Store):
    """Reuse validated review behavior while allowing separate worker/UI processes."""
    background_only = True

    def __init__(self, index: Path, library: Path, state: Path, metrics=None):
        self.index, self.library, self.state = index, library.resolve(), state.resolve()
        self.lock = threading.RLock()
        self.pools=None
        self.pool_lock=threading.Lock()
        self.metrics = metrics or Metrics()
        self.connection = connect()
        self.db = Connection(self.connection)
        if self.metrics.prefix=='photo_review':
            self.connection.execute("SET statement_timeout='15s'; SET lock_timeout='3s'")

    def enable_pooling(self):
        """Keep independent bounded reader and writer capacity for the GUI."""
        from psycopg_pool import ConnectionPool
        from .telemetry import get_telemetry
        with self.pool_lock:
            if self.pools is not None:return
            pools={}
            try:
                for role,minimum,maximum in [('read',2,12),('write',1,2)]:
                    def configure(connection,role=role):
                        connection.execute("SET statement_timeout='15s'; SET lock_timeout='3s'")
                        connection.execute('SET default_transaction_read_only='+('on' if role=='read' else 'off'))
                    def reset(connection,configure=configure):
                        connection.execute('RESET ALL');configure(connection)
                    pool=ConnectionPool(kwargs=dict(service=os.environ.get('PHOTO_PG_SERVICE','photo_pipeline'),
                        autocommit=True,connect_timeout=5,application_name='photo-review-'+role),
                        min_size=minimum,max_size=maximum,timeout=5,max_waiting=32,
                        max_lifetime=900,max_idle=60,configure=configure,reset=reset,
                        check=ConnectionPool.check_connection,name='photo-'+role,open=False)
                    pools[role]=pool;pool.open(wait=True,timeout=10)
            except BaseException:
                for pool in pools.values():pool.close()
                raise
            self.pools=pools
            get_telemetry().pools=pools

    @contextmanager
    def request_session(self,readonly=True):
        """Borrow a session for one request; always return it, including errors."""
        from .telemetry import get_telemetry
        self.enable_pooling()
        role='read' if readonly else 'write';pool=self.pools[role]
        with get_telemetry().stage('pg.pool.wait',pool=role):connection=pool.getconn()
        try:
            reader=copy.copy(self)
            reader.lock=threading.RLock()
            reader.connection=connection;reader.db=Connection(connection)
            yield reader
        finally:pool.putconn(connection)

    def close(self):
        if self.pools:
            for pool in self.pools.values():pool.close()
        self.db.close()

    def export(self) -> dict:
        from .snapshots import export_snapshot
        target=os.environ.get('PHOTO_SNAPSHOT_PROM')
        return export_snapshot(self.state,Path(target) if target else None)

    def rows(self,statement,parameters=()):
        """Serialize only the shared PostgreSQL connection, never DuckDB or I/O."""
        from .telemetry import get_telemetry
        with get_telemetry().stage('lock.wait'):
            if not self.lock.acquire(timeout=getattr(self,'query_lock_timeout',3)):
                raise TimeoutError('Photo database is busy; retry shortly')
        try:
            result=self.db.execute(statement,parameters)
            names=[item[0] for item in result.description]
            return [dict(zip(names,row)) for row in result.fetchall()]
        finally:self.lock.release()

    def status(self) -> dict:
        rows=self.rows("SELECT value FROM pipeline_state WHERE key='snapshot'")
        snapshot=rows[0]['value'] if rows else {}
        return dict(backend='postgres',query_backend='duckdb' if (self.state/'analytics/current.json').exists() else 'postgres_bootstrap',
            captured_at=snapshot.get('captured_at'),published_at=snapshot.get('published_at'))

    def gallery_query(self,method,*args):
        from .readside import GalleryReader
        reader=GalleryReader(self)
        try:return getattr(reader,method)(*args)
        finally:reader.close()

    def dates(self,timezone):
        if (self.state/'analytics/current.json').exists():return self.gallery_query('dates',timezone)
        return super().dates(timezone)

    def photos(self,date,timezone,offset=0,limit=100):
        if (self.state/'analytics/current.json').exists():return self.gallery_query('photos',date,timezone,offset,limit)
        return super().photos(date,timezone,offset,limit)

    def detail(self,path):
        photo=super().detail(path)
        review=self.review_state()
        for face in photo['faces']:
            face['match_details']=review.get('details',{}).get(face['id'],dict(reason='pending',score=None,person=None,qualified=False))
        if self.rows("SELECT to_regclass('public.photo_context') IS NOT NULL AS present")[0]['present']:
            context=self.rows("SELECT summary AS context_summary,context AS location_context,model AS context_model FROM photo_context WHERE path=? AND size_bytes=? AND status='done'",[path,photo['size_bytes']])
            if context:
                photo.update(context[0])
                names={f['person'] for f in photo['faces'] if f['person']}
                if names!={p['name'] for p in (photo.get('location_context') or {}).get('saved_people',[])}:
                    photo['context_summary']=None
        return photo

    def search(self,query,timezone='UTC',offset=0):
        return self.gallery_query('photos','unknown',timezone,offset,100,query)

    def group_suggestions(self,paths,timezone='UTC'):
        return self.gallery_query('group_suggestions',paths,timezone)

    def priority_review(self) -> dict:
        """Read private review preferences from the photo database."""
        rows=self.rows("SELECT value FROM pipeline_state WHERE key='priority_review'")
        return rows[0]['value'] if rows else {}

    def priority_matches(self, matches: dict) -> dict:
        people=set(self.priority_review().get('people', []))
        return {face_id:match for face_id,match in matches.items()
                if match['person'].strip().lower() in people}

    def matching_pass(self) -> dict:
        """Read saved embeddings in bounded batches; never change confirmed labels.

        Cache until faces, reviews or the analytical generation change.
        A repeatable-read snapshot keeps references/candidates coherent during a pass.
        """
        from .matching import rank_batch, ReviewGroups, vectors
        if hasattr(self,'suggestion_source'):
            # HTTP requests consume the last completed pass. Never run a whole
            # library embedding comparison while a browser waits for its page.
            cache=getattr(self.suggestion_source,'_matching_cache',None)
            return cache['matches'] if cache else {}
        with self.lock:
            signature=self.rows("""SELECT count(*) AS faces,max(updated_at) AS last_updated,
                (SELECT count(*) FROM rejected_matches) AS rejected FROM faces""")[0]
            manifest=self.state/'analytics/current.json'
            signature['snapshot']=manifest.stat().st_mtime_ns if manifest.exists() else None
            priority=set(self.priority_review().get('people', []))
            signature['priority']=priority
            cache=getattr(self,'_matching_cache',None)
            if cache and cache['signature']==signature:
                return cache['matches']
            base="""FROM faces f JOIN face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes
                AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
                WHERE EXISTS (SELECT 1 FROM catalog.gphotos_media m WHERE m.path=f.path AND m.size_bytes=f.size_bytes)
                AND NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=f.path)"""
            matches={}
            details={}
            review_groups=ReviewGroups()
            reader=None
            try:
                if manifest.exists():
                    from .readside import GalleryReader
                    reader=GalleryReader(self)
                    read=reader.rows
                    base=base.replace('FROM faces f','FROM reviewed_faces f').replace('catalog.gphotos_media','enriched_media').replace('catalog.gphotos_album_dup','album_duplicates')
                else:read=self.rows
                with self.metrics.measure('match'),self.connection.transaction():
                    self.db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    references=read('SELECT f.id,f.person,f.model,f.embedding '+base+" AND f.person IS NOT NULL AND f.label_source='user'")
                    missing=priority-{ref['person'].strip().lower() for ref in references}
                    if missing:
                        references.extend(read('SELECT f.id,f.person,f.model,f.embedding '+base+
                            " AND f.label_source='immich' AND lower(trim(f.person))=ANY(?)",[sorted(missing)]))
                    reference_groups=vectors(references)
                    def candidate_batches():
                        query='SELECT f.id,f.person,f.model,f.embedding '+base
                        if reader:
                            yield from reader.batches(query+' ORDER BY f.id')
                            return
                        last=''
                        while True:
                            candidates=read(query+' AND f.id>? ORDER BY f.id LIMIT 256',[last])
                            if not candidates:return
                            yield candidates
                            last=candidates[-1]['id']
                    for candidates in candidate_batches():
                        rejected=self.rows('SELECT face_id,reference_id FROM rejected_matches WHERE face_id=ANY(?)',
                            [[r['id'] for r in candidates]])
                        ranked=rank_batch(candidates,references,{(r['face_id'],r['reference_id']) for r in rejected},reference_groups=reference_groups)
                        details.update(ranked)
                        for row in candidates:
                            match=ranked[row['id']]
                            if row['person'] is None and match['qualified']:
                                matches[row['id']]={key:match[key] for key in ('person','reference_id','score')}
                        review_groups.add(candidates,ranked)
            finally:
                if reader:reader.close()
            self._matching_cache=dict(signature=signature,at=time.monotonic(),matches=matches,
                details=details,groups=review_groups.groups,generation=uuid.uuid4().hex)
            return matches

    def review_state(self) -> dict:
        """Overlay durable rejections on the last pass, without waiting for a rebuild.

        Read fresh decisions even when another process or an in-flight matching
        pass published the cache. Never mutate the shared background snapshot.
        """
        self.matching_pass()
        review=getattr(getattr(self,'suggestion_source',self),'_matching_cache',None) or {}
        blocked={(row['face_id'],row['person']) for row in self.rows("""SELECT r.face_id,ref.person
            FROM rejected_matches r JOIN faces ref ON ref.id=r.reference_id WHERE ref.person IS NOT NULL""")}
        matches=review.get('matches',{})
        removed={face_id for face_id,match in matches.items() if (face_id,match['person']) in blocked}
        details={face_id:dict(detail,qualified=False,reason='rejected')
                 if (face_id,detail.get('person')) in blocked else detail
                 for face_id,detail in review.get('details',{}).items()}
        result=dict(review,matches={key:match for key,match in matches.items() if key not in removed},details=details)
        if removed and 'groups' in review:
            # A rejected identity must also leave its cached suggested-person
            # collection. Keep the detection as a singleton until regrouping.
            groups={key:[face_id for face_id in ids if face_id not in removed]
                    for key,ids in review['groups'].items()}
            groups={key:ids for key,ids in groups.items() if ids}
            for face_id in removed:
                # Preserve the old group ID when its anchor was rejected, so
                # an open group still shows its remaining members.
                groups['rejected:'+face_id]=[face_id]
            result['groups']=groups
        return result

    def face_library(self, person: str = '', status: str = 'unreviewed', offset: int = 0, limit: int = 48,
                     grouped: bool = False, group: str = '', scope: str = 'repeated') -> dict:
        """Group previously processed unnamed faces into bulk-review suggestions."""
        if status not in ('all','unreviewed','named','suggested') or offset<0 or not 1<=limit<=100:
            raise ValueError('Invalid face filter')
        review=self.review_state()
        matches=review.get('matches',{})
        if status=='suggested' and scope=='priority':
            matches=self.priority_matches(matches)
        if (self.state/'analytics/current.json').exists():
            result=self.gallery_query('faces',person,status,offset,limit,matches,review,grouped,group,scope)
            result['suggestions_refreshing']=hasattr(self,'suggestion_source') and not getattr(self.suggestion_source,'_matching_cache',None)
            return result
        with self.lock:
            # Paginate before fetching captions. Joining the global latest-caption
            # view before LIMIT can repeatedly scan every caption for every face.
            base="""FROM faces f JOIN face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes
                AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
                JOIN catalog.gphotos_media m ON m.path=f.path AND m.size_bytes=f.size_bytes
                WHERE m.kind='media' AND m.ext IN ('jpg','jpeg','heic','png','gif','webp')
                AND NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=f.path)"""
            counts=self.rows('SELECT count(*) AS total,count(*) FILTER(WHERE f.person IS NULL) AS unreviewed '+base)[0]
            people=self.rows('SELECT f.person,count(*) AS faces '+base+' AND f.person IS NOT NULL GROUP BY f.person ORDER BY lower(f.person)')
            data=dict(counts=counts,people=people,offset=offset)
            visible={r['id'] for r in self.rows('SELECT f.id '+base+' AND f.person IS NULL')}
            review_page=None
            if status=='unreviewed' and (grouped or group):
                from .matching import review_page as select_review_page
                review_page=select_review_page(visible,review,offset,limit,group,scope)
                ids=review_page.pop('ids')
                data.update(review_page)
            elif status!='suggested':
                filters,params='',[]
                if status=='unreviewed':filters+=' AND f.person IS NULL'
                if status=='named':filters+=' AND f.person IS NOT NULL'
                if person:
                    clause, params = self.face_person_filter(person, status)
                    filters += clause
                data['total']=self.rows('SELECT count(*) n '+base+filters,params)[0]['n']
                dated=base.replace('WHERE m.kind', 'LEFT JOIN extracted e ON e.path=m.path AND e.size_bytes=m.size_bytes WHERE m.kind')
                ids=[r['id'] for r in self.rows('SELECT f.id '+dated+filters+
                    ' ORDER BY coalesce(e.capture_ts,m.taken_ts) DESC NULLS LAST,f.id LIMIT ? OFFSET ?',[*params,limit,offset])]
            else:
                selected=sorted((face_id for face_id,m in matches.items() if face_id in visible and (not person or m['person']==person)),
                    key=lambda face_id:(matches[face_id]['person'],-matches[face_id]['score'],face_id))
                data['total'],data['offset']=len(selected),offset
                ids=selected[offset:offset+limit]
            data['faces']=self.rows("""SELECT f.id,f.path,f.box,f.confidence,f.person,f.label_source,f.updated_at AS revision,
                coalesce(e.capture_ts,m.taken_ts) AS capture_ts,
                CASE WHEN e.path IS NOT NULL THEN e.latitude WHEN s.geo_lat BETWEEN -90 AND 90
                    AND s.geo_lon BETWEEN -180 AND 180 AND NOT(s.geo_lat=0 AND s.geo_lon=0) THEN s.geo_lat END AS latitude,
                CASE WHEN e.path IS NOT NULL THEN e.longitude WHEN s.geo_lat BETWEEN -90 AND 90
                    AND s.geo_lon BETWEEN -180 AND 180 AND NOT(s.geo_lat=0 AND s.geo_lon=0) THEN s.geo_lon END AS longitude,
                caption.summary FROM faces f JOIN catalog.gphotos_media m ON m.path=f.path AND m.size_bytes=f.size_bytes
                LEFT JOIN extracted e ON e.path=m.path AND e.size_bytes=m.size_bytes
                LEFT JOIN catalog.gphotos_sidecars s ON s.path=m.sidecar_path
                LEFT JOIN LATERAL (SELECT summary,size_bytes FROM catalog.media_summaries
                    WHERE path=m.path AND status='ok' ORDER BY created_at DESC,enricher DESC LIMIT 1) caption ON caption.size_bytes=m.size_bytes
                WHERE f.id=ANY(?)""",[ids]) if ids else []
            if status=='suggested':data['faces']=[f for f in data['faces'] if f['person'] is None]
            data['faces'].sort(key=lambda r:ids.index(r['id']))
            groups={}
            for match in matches.values():groups[match['person']]=groups.get(match['person'],0)+1
            data['suggested_people']=[dict(person=name,faces=count) for name,count in sorted(groups.items())]
            data['counts']['suggested']=len(matches)
            for face in data['faces']:
                face['suggestion']=matches.get(face['id']) if face['person'] is None else None
                face['match_details']=review.get('details',{}).get(face['id'],dict(reason='pending',score=None,person=None,qualified=False))
                if review_page and not group:
                    face['review_group']=data['group_cards'].get(face['id'])
            from .matching import review_group_counts
            data['counts'].update(review_group_counts(visible,review))
            data['grouping_refreshing']='groups' not in review
            data.pop('group_cards',None)
            return data

    def group_selection(self, group: str, generation: str) -> dict:
        """Snapshot explicitly selected group members; never propagate a name here."""
        review=self.review_state()
        if not generation or generation != review.get('generation'):
            raise ValueError('Face groups changed; refresh the group before selecting it')
        ids=review.get('groups',{}).get(group,[])
        if not ids:raise ValueError('Face group is no longer available; refresh')
        matches=review['matches']
        faces=[]
        for offset in range(0,len(ids),1000):
            rows=self.rows("""SELECT f.id,f.updated_at AS revision FROM faces f
                JOIN face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes
                  AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
                WHERE f.id=ANY(?) AND f.person IS NULL ORDER BY f.id""",[ids[offset:offset+1000]])
            faces.extend(dict(id=row['id'],revision=row['revision'],person=matches.get(row['id'],{}).get('person')) for row in rows)
        return dict(faces=faces,total=len(faces),generation=generation)

    def source_file(self, path: str) -> Path:
        """Validate originals without evaluating captions or other enrichment joins."""
        rows=self.rows('SELECT size_bytes FROM catalog.gphotos_media WHERE path=?',[path])
        if not rows:raise ValueError('Unknown photo')
        file=contained(self.library,path)
        if file.stat().st_size!=rows[0]['size_bytes']:raise ValueError('Photo changed since indexing; re-index it before enrichment')
        return file

    def suggested_selection(self, threshold: float = .9, person: str = '', priority: bool = False) -> dict:
        """Snapshot all eligible displayed names/revisions for explicit bulk review."""
        if not 0<=threshold<=1:
            raise ValueError('Similarity must be between 0 and 1')
        with self.lock:
            matches=self.review_state().get('matches',{})
            if priority:
                matches=self.priority_matches(matches)
            ids=sorted(face_id for face_id,match in matches.items()
                if match['score']>=threshold and (not person or match['person']==person))
            faces=[]
            for offset in range(0,len(ids),1000):
                rows=self.rows("""SELECT f.id,f.updated_at AS revision FROM faces f
                    JOIN face_scans fs ON fs.path=f.path AND fs.size_bytes=f.size_bytes
                      AND fs.mtime_ns=f.mtime_ns AND fs.model=f.model
                    WHERE f.id=ANY(?) AND f.person IS NULL ORDER BY f.id""",[ids[offset:offset+1000]])
                faces.extend(dict(id=row['id'],revision=row['revision'],person=matches[row['id']]['person']) for row in rows)
            return dict(faces=faces,total=len(faces),threshold=threshold)

    def reject(self, face_id: str, reference_id: str) -> None:
        """Save a rejection and invalidate selections made before that decision."""
        with self.lock,self.connection.transaction():
            super().reject(face_id,reference_id)
            self.db.execute('UPDATE faces SET updated_at=clock_timestamp() WHERE id=?',[face_id])

    def label_face(self, face_id: str, person: str, revision=None) -> None:
        """Check revisions while holding the row lock; audit the actual prior value."""
        if not isinstance(person,str) or len(person)>200: raise ValueError('Invalid person name')
        with self.lock, self.metrics.measure('review'), self.connection.transaction():
            rows=self.rows('SELECT * FROM faces WHERE id=? FOR UPDATE',[face_id])
            if not rows: raise ValueError('Unknown face')
            face=rows[0]
            if revision is not None and str(face['updated_at'])!=str(revision):
                raise ValueError('This face was edited elsewhere; refresh before saving')
            self.face(face_id)  # validate the original file identity too
            self.db.execute('UPDATE faces SET person=?,label_source=?,updated_at=clock_timestamp() WHERE id=?',
                [person.strip() or None,'user' if person.strip() else 'user_cleared',face_id])
            self._history('label_face',dict(id=face_id,person=person.strip(),previous=face['person']))

    def label_faces(self, faces: list, person: str | None = None) -> None:
        """Save one shared name or each user's selected name in a single transaction."""
        if not isinstance(faces,list) or not 1<=len(faces)<=100:
            raise ValueError('Select 1–100 faces')
        if not all(isinstance(f,dict) and f.get('id') and f.get('revision') for f in faces):
            raise ValueError('Face revisions are required')
        if len({f['id'] for f in faces}) != len(faces):
            raise ValueError('Select each face only once')
        if person is None and not all(isinstance(f.get('person'),str)
                and f['person'].strip() and len(f['person'])<=200 for f in faces):
            raise ValueError('Each selected face must have a suggested name to confirm')
        with self.lock,self.connection.transaction():
            for face in sorted(faces,key=lambda f:f['id']):
                self.label_face(face['id'],face['person'] if person is None else person,face['revision'])

    def auto_accept_settings(self) -> dict:
        """Read the durable opt-in rule and distinguish machine labels from reviews."""
        with self.lock:
            rows=self.rows("SELECT value FROM pipeline_state WHERE key='auto_accept'")
            rule=rows[0]['value'] if rows else dict(enabled=False,threshold=.9)
            status=self.rows("SELECT value FROM pipeline_state WHERE key='auto_accept_status'")
            count=self.rows("SELECT count(*) n FROM faces WHERE label_source='automatic'")[0]['n']
            return dict(**rule,accepted=count,last_pass=status[0]['value'] if status else None)

    def configure_auto_accept(self, enabled: bool, threshold: float) -> dict:
        """Save a user-controlled rule; this request does not itself process faces."""
        if not isinstance(enabled,bool) or isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not .55<=threshold<=1:
            raise ValueError('Choose enabled/disabled and a similarity between 55 and 100')
        rule=dict(enabled=enabled,threshold=threshold)
        with self.lock,self.connection.transaction():
            self.db.execute("INSERT INTO pipeline_state VALUES ('auto_accept',?,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()",[json.dumps(rule)])
            self._history('configure_auto_accept',rule)
        return self.auto_accept_settings()

    def auto_accept_pass(self, limit: int = 100) -> dict:
        """Apply an opted-in rule in bounded batches, preserving human decisions.

        Only human-confirmed references are eligible. Conditional updates and a
        locked rule prevent concurrent edits, overlapping pods or a disabled rule
        from being overwritten. Automatically named faces are never references.
        """
        if not 1<=limit<=100:raise ValueError('Invalid automatic batch size')
        with self.lock:
            settings=self.auto_accept_settings()
            if not settings['enabled']:return dict(saved=0,skipped=0)
            matches=self.matching_pass()
            candidates=self.suggested_selection(settings['threshold'])['faces']
            cursor=(settings.get('last_pass') or {}).get('last_id','')
            candidates=[f for f in candidates if f['id']>cursor]+[f for f in candidates if f['id']<=cursor]
            result=dict(saved=0,skipped=0,checked_at=time.time())
            with self.metrics.measure('auto_accept'),self.connection.transaction():
                rows=self.rows("SELECT value FROM pipeline_state WHERE key='auto_accept' FOR UPDATE")
                if not rows or not rows[0]['value']['enabled'] or rows[0]['value']['threshold']!=settings['threshold']:
                    return dict(saved=0,skipped=0)
                # Leave explicitly cleared faces for human review, even when a
                # reference still produces a high score for the previous name.
                ids=[f['id'] for f in candidates]
                eligible={r['id'] for r in self.rows("SELECT id FROM faces WHERE id=ANY(?) AND person IS NULL AND label_source IS DISTINCT FROM 'user_cleared'",[ids])} if ids else set()
                for candidate in (f for f in candidates if f['id'] in eligible):
                    if result['saved']+result['skipped']>=limit:break
                    result['last_id']=candidate['id']
                    try:self.face(candidate['id'])
                    except (OSError,ValueError):
                        result['skipped']+=1;continue
                    match=matches[candidate['id']]
                    # Re-check the reference and revision after taking the rule
                    # lock; another GUI/pod may have edited them since matching.
                    changed=self.rows("""UPDATE faces SET person=?,label_source='automatic',updated_at=clock_timestamp()
                        WHERE id=? AND person IS NULL AND updated_at=?
                        AND label_source IS DISTINCT FROM 'user_cleared'
                        AND EXISTS (SELECT 1 FROM faces ref WHERE ref.id=? AND ref.person=? AND ref.label_source='user')
                        AND NOT EXISTS (SELECT 1 FROM rejected_matches r JOIN faces ref ON ref.id=r.reference_id
                            WHERE r.face_id=? AND ref.person=?) RETURNING id""",
                        [candidate['person'],candidate['id'],candidate['revision'],match['reference_id'],candidate['person'],candidate['id'],candidate['person']])
                    if not changed:
                        result['skipped']+=1;continue
                    self._history('auto_accept_face',dict(id=candidate['id'],person=candidate['person'],
                        previous=None,score=match['score'],threshold=settings['threshold'],reference_id=match['reference_id']))
                    result['saved']+=1
                self.db.execute("INSERT INTO pipeline_state VALUES ('auto_accept_status',?,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()",[json.dumps(result)])
            return result

    def seed_jobs(self, timezone='UTC', faces=True) -> int:
        """Queue only missing/stale work; preserve imported retries and completed scans."""
        ZoneInfo(timezone)
        with self.lock, self.metrics.measure('queue'):
            cursor = self.db.execute("""INSERT INTO photo_jobs(path,size_bytes,version,model,timezone,attempts,available_at)
              SELECT m.path,m.size_bytes,?,?,?,coalesce(a.attempts,0),
                     coalesce(to_timestamp(a.retry_after),now())
              FROM enriched_media m
              LEFT JOIN extracted e ON e.path=m.path AND e.size_bytes=m.size_bytes
              LEFT JOIN face_scans f ON f.path=m.path AND f.size_bytes=m.size_bytes AND f.model=?
              LEFT JOIN worker_attempts a ON a.path=m.path AND a.size_bytes=m.size_bytes
                AND a.version=? AND a.model=? AND a.timezone=?
              WHERE NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=m.path)
                AND (e.path IS NULL OR e.error IS NOT NULL OR e.version<>?
                  OR (e.capture_source LIKE 'exif.assumed:%' AND e.capture_source<>?)
                  OR (? AND f.path IS NULL))
              ON CONFLICT(path) DO UPDATE SET size_bytes=excluded.size_bytes,version=excluded.version,
                model=excluded.model,timezone=excluded.timezone,status='ready',available_at=excluded.available_at,
                claim=NULL,lease_until=NULL,enqueued_at=now(),completed_at=NULL
              WHERE photo_jobs.status='done' OR
                (photo_jobs.size_bytes,photo_jobs.version,photo_jobs.model,photo_jobs.timezone)
                  IS DISTINCT FROM (excluded.size_bytes,excluded.version,excluded.model,excluded.timezone)""",
              [VERSION, MODEL_ID if faces else '', timezone, MODEL_ID, VERSION, MODEL_ID if faces else '', timezone,
               VERSION, 'exif.assumed:'+timezone, faces])
            return cursor.rowcount

    def claim_job(self, lease_seconds=600) -> dict | None:
        with self.lock, self.metrics.measure('queue'), self.connection.transaction():
            rows = self.rows("""WITH candidate AS (
              SELECT path FROM photo_jobs WHERE
                (status IN ('ready','retry') AND available_at<=now()) OR
                (status='running' AND lease_until<now())
              ORDER BY attempts,enqueued_at,path FOR UPDATE SKIP LOCKED LIMIT 1)
              UPDATE photo_jobs j SET status='running',claim=?,lease_until=now()+? * interval '1 second',
                attempts=attempts+1 FROM candidate c WHERE j.path=c.path RETURNING j.*""",
              [uuid.uuid4().hex, lease_seconds])
            return rows[0] if rows else None

    def process_job(self, job: dict, engine=None, retry_seconds=3600) -> bool:
        """Compute without a DB transaction; fence stale claims before atomic commit."""
        try:
            row = self.photo(job['path'])
            file = contained(self.library, job['path'])
            before = file.stat()
            if before.st_size != job['size_bytes'] or row['size_bytes'] != job['size_bytes']:
                raise ValueError('Source changed since indexing')
            old = self.rows('SELECT * FROM extracted WHERE path=?', [job['path']])
            old = old[0] if old else None
            unchanged = old and (old['size_bytes'],old['mtime_ns'],old['version']) == (before.st_size,before.st_mtime_ns,VERSION) and not old['error']
            if unchanged and (old['capture_source'] or '').startswith('exif.assumed:'):
                unchanged = old['capture_source'] == 'exif.assumed:'+job['timezone']
            meta = None
            if not unchanged:
                with self.metrics.measure('exif'):
                    sidecar = contained(self.library,row['sidecar_path']) if row['sidecar_path'] else None
                    meta = read_metadata(file,sidecar,job['timezone'])
            scan = self.rows('SELECT * FROM face_scans WHERE path=?', [job['path']])
            scan = scan[0] if scan else None
            detected = None
            if engine and not (scan and (scan['size_bytes'],scan['mtime_ns'],scan['model']) == (before.st_size,before.st_mtime_ns,MODEL_ID)):
                with self.metrics.measure('faces'):
                    detected = engine.detect(file)
            after = file.stat()
            if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
                raise ValueError('Source changed during extraction')
            with self.lock, self.metrics.measure('persist'), self.connection.transaction():
                held = self.rows("SELECT claim FROM photo_jobs WHERE path=? AND claim=? AND status='running' AND lease_until>now() FOR UPDATE", [job['path'],job['claim']])
                if not held:
                    return False
                if meta is not None:
                    self.upsert('extracted',[job['path'],before.st_size,before.st_mtime_ns]+list(meta.values()))
                if detected is not None:
                    for face in detected:
                        self.db.execute('INSERT INTO faces VALUES (?,?,?,?,?,?,?,?,NULL,NULL,current_timestamp)',
                            [face['id'],job['path'],before.st_size,before.st_mtime_ns,list(map(float,face['box'])),face['confidence'],list(map(float,face['embedding'])),face['model']])
                    self.upsert('face_scans',[job['path'],before.st_size,before.st_mtime_ns,MODEL_ID])
                error = bool(meta and meta['error'])
                self.db.execute("UPDATE photo_jobs SET status=?,completed_at=CASE WHEN ? THEN NULL ELSE now() END,available_at=now()+? * interval '1 second',lease_until=NULL,claim=NULL,last_error=? WHERE path=?",
                    ['retry' if error else 'done',error,retry_seconds,'metadata_error' if error else None,job['path']])
                self.db.execute('DELETE FROM worker_attempts WHERE path=?',[job['path']])
            return not error
        except Exception as exc:
            # Exception text can contain private filenames: persist only a bounded category.
            with self.lock:
                self.db.execute("UPDATE photo_jobs SET status='retry',available_at=now()+? * interval '1 second',claim=NULL,lease_until=NULL,last_error=? WHERE path=? AND claim=?",
                    [retry_seconds,type(exc).__name__,job['path'],job['claim']])
            logging.warning('Photo job failed: %s', type(exc).__name__)
            return False

    def queue_metrics(self) -> dict:
        return self.rows("""SELECT count(*) FILTER(WHERE status='ready') AS ready,
          count(*) FILTER(WHERE status='running') AS running, count(*) FILTER(WHERE status='retry') AS retry,
          count(*) FILTER(WHERE status='done') AS done,
          coalesce(extract(epoch FROM now()-min(enqueued_at) FILTER(WHERE status<>'done')),0) AS oldest_seconds
          FROM photo_jobs""")[0]


def run_worker(index, library, state, models, metrics, batch_size=25, timezone='UTC', faces=True,
               pause_seconds=2, idle_seconds=60, max_batches=0):
    """Continuously claim independent jobs; a separate timer publishes analytics."""
    import signal
    from .faces import FaceEngine
    metrics.stages = ("queue","exif","faces","persist")
    stop = threading.Event()
    previous = {sig: signal.signal(sig,lambda *_:stop.set()) for sig in (signal.SIGTERM,signal.SIGINT)}
    store = PostgresStore(index,library,state,metrics)
    try:
        engine = None
        if faces:
            import cv2
            cv2.setNumThreads(2)
            with metrics.measure('faces'):
                engine = FaceEngine(models)
        count = 0
        while not stop.is_set():
            store.seed_jobs(timezone,faces)
            selected = 0
            for _ in range(batch_size):
                if stop.is_set(): break
                job = store.claim_job()
                if not job: break
                store.process_job(job,engine)
                selected += 1
            store.refresh_metrics()
            metrics.jobs = store.queue_metrics()
            metrics.publish()
            logging.info('PostgreSQL batch completed: %d jobs',selected)
            count += 1
            if max_batches and count>=max_batches: break
            stop.wait(pause_seconds if selected else idle_seconds)
    finally:
        store.close()
        for sig,handler in previous.items(): signal.signal(sig,handler)
