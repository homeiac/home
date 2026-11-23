"""Piglet-side Luna queue, cost ledger, and Parquet outbox. Only frames leave Piglet."""
import base64
from contextlib import closing, nullcontext
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

import duckdb

sys.path[:0] = [str(Path(__file__).resolve().parent), '/opt/photo-enrichment/context', '/opt/knowledge-index/enrichers']
import reconciliation
from photo_enrichment.snapshots import analytical_connection
from photo_enrichment import places
from photo_enrichment.postgres import connect
from media_summary import VIDEO_EXTS, jpeg_frame, video_duration

ROOT = Path('/local-3TB-backup/photo-enrichment/luna-backfill')
LIBRARY = Path('/local-3TB-backup/gphotos/library').resolve()
# In-flight requests reserve a dollar. Completed requests without reported
# usage settle at a conservative estimate from the observed media cohort.
RESERVE = 1_000_000
LIMIT = 250_000_000
MIN_PROJECTION = 2_000  # $0.002 per request
LEGACY_HOLDS = ('unknown usage or exceeded reservation', 'interrupted request with unknown usage')
MODEL = 'gpt-6-luna'
os.umask(0o077)


def seed(db):
    """Pin one catalog generation and snapshot the current uncaptioned work."""
    if db.execute("SELECT count(*) FROM config WHERE key='seeded'").fetchone()[0]:
        return
    reader, snapshot = analytical_connection(Path('/local-3TB-backup/photo-enrichment'))
    try:
        reader.execute("ATTACH '/local-3TB-backup/knowledge-index/knowledge.duckdb' AS ki (READ_ONLY)")
        # The attached catalog macro resolves its source views in the calling catalog.
        reader.execute('CREATE TEMP VIEW gphotos_media AS SELECT * FROM ki.gphotos_media')
        reader.execute('CREATE TEMP VIEW media_summaries AS SELECT * FROM ki.media_summaries')
        query = """WITH labels AS (
          SELECT f.path,f.size_bytes,to_json(list(struct_pack(name:=f.person,box:=f.box)
            ORDER BY f.id)) AS faces FROM faces f JOIN face_scans s USING(path,size_bytes,mtime_ns,model)
            WHERE f.label_source='user' AND f.person IS NOT NULL GROUP BY f.path,f.size_bytes)
          SELECT q.path,q.size_bytes,lower(q.ext),q.people,coalesce(e.latitude,s.geo_lat),
            coalesce(e.longitude,s.geo_lon),l.faces,c.context
          FROM ki.gphotos_to_summarize('gemma4-e2b-p1') q
          JOIN ki.gphotos_media m ON m.path=q.path AND m.size_bytes=q.size_bytes
          LEFT JOIN ki.gphotos_sidecars s ON s.path=m.sidecar_path
          LEFT JOIN enriched_media e ON e.path=q.path AND e.size_bytes=q.size_bytes
          LEFT JOIN labels l ON l.path=q.path AND l.size_bytes=q.size_bytes
          LEFT JOIN photo_context c ON c.path=q.path AND c.size_bytes=q.size_bytes
          WHERE NOT EXISTS (SELECT 1 FROM ki.gphotos_album_dup d WHERE d.path=q.path)
          ORDER BY q.taken_ts DESC NULLS LAST,q.path"""
        rows = reader.execute(query)
        with db:
            while chunk := rows.fetchmany(512):
                records = []
                for path,size,ext,people,lat,lon,faces,context in chunk:
                    labels = json.loads(faces or '[]')
                    gps = dict(latitude=lat,longitude=lon) if lat is not None and lon is not None and -90<=lat<=90 and -180<=lon<=180 and (lat or lon) else None
                    candidates = (json.loads(context or '{}').get('candidates') or [])[:5]
                    meta = dict(confirmed_photo_faces=labels,saved_unlocalized_names=sorted(set(people or [])-{p['name'] for p in labels}),
                                gps=gps,nearby_candidates=[c.get('title') for c in candidates if c.get('title')] if gps else [])
                    records.append((path,size,ext,json.dumps(meta)))
                db.executemany("INSERT OR IGNORE INTO jobs(path,size_bytes,ext,metadata) VALUES (?,?,?,?)",records)
            db.execute("INSERT INTO config VALUES ('seeded',?)",[snapshot['generation']])
    finally:
        reader.close()


def migrate(db):
    """Preserve earlier costs and captions, and give corrections a stable Parquet filename."""
    cols={r[1] for r in db.execute('PRAGMA table_info(jobs)')}
    for name,kind in [('origin_batch','TEXT'),('available_after','REAL DEFAULT 0')]:
        if name not in cols:
            db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {kind}')
    db.execute("""CREATE TABLE IF NOT EXISTS previous_captions(
        job_id INTEGER PRIMARY KEY,metadata TEXT,result TEXT,cost INTEGER,original_state TEXT)""")
    db.commit()


def schedule_corrections(db):
    """Retry the first captions that missed place hints and early video decoder failures once."""
    with db:
        db.execute("""INSERT OR IGNORE INTO previous_captions SELECT id,metadata,result,cost,state FROM jobs
            WHERE published=1 AND ((state='ok' AND json_type(metadata,'$.gps')='object'
            AND json_type(metadata,'$.place_lookup') IS NULL AND json_type(metadata,'$.location_context_source') IS NULL)
            OR (state='source_error' AND ext IN ('mp4','mov','3gp','avi','mpg','m4v')))""")
        db.execute("""UPDATE jobs SET origin_batch=batch,state='pending',cost=0,published=0
            WHERE origin_batch IS NULL AND id IN (SELECT job_id FROM previous_captions)""")


def immich_context():
    path = ROOT/'immich-context.sqlite3'
    return closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) if path.exists() else nullcontext(None)


def add_context(db, grant):
    """Reuse Immich metadata and cached landmarks without remote lookups in the claim path."""
    if not grant['items']:
        return grant
    os.environ.setdefault('PGSERVICEFILE','/etc/photo-enrichment/pg_service.conf')
    os.environ.setdefault('PGPASSFILE','/etc/photo-enrichment/pgpass')
    with connect() as pg, immich_context() as snapshot:
        for item in grant['items']:
            m=item['metadata']
            groups=pg.execute("""SELECT DISTINCT g.event,g.location,g.venue FROM photo_groups g
                JOIN group_members gm ON gm.group_id=g.id WHERE gm.path=%s AND gm.size_bytes=%s""",
                [item['path'],item['size']]).fetchall()
            m['saved_groups']=[dict(event=e,location=l,venue=v) for e,l,v in groups if e or l or v]
            context = snapshot.execute('SELECT metadata FROM context WHERE path=? AND size=?',
                                       (item['path'],item['size'])).fetchone() if snapshot else None
            if context:
                saved = json.loads(context[0])
                m['immich_place'] = saved['place']
                m['immich_named_people'] = saved['people']
            gps=m.get('gps')
            m['location_context_source'] = 'immich' if m.get('immich_place') else 'saved_metadata'
            if gps and not m.get('place_lookup'):
                key=places.cache_key(gps['latitude'],gps['longitude'])
                cached=pg.execute('SELECT context FROM photo_place_cache WHERE key=%s',[key]).fetchone()
                if cached:
                    feed=cached[0]
                    m['place_lookup']=feed.get('provider',places.VERSION)
                    m['nearby_candidates']=[dict(name=c['title'],description=c.get('description',''),
                        distance_m=places.distance(gps['latitude'],gps['longitude'],c['latitude'],c['longitude']))
                        for c in feed.get('candidates',[])[:5]]
                    m['location_context_source'] = 'cached_landmarks'
            with db:
                db.execute("UPDATE jobs SET metadata=? WHERE id=? AND state='reserved'",[json.dumps(m),item['id']])
    return grant


def reserve(db, request):
    """Atomically reserve the worst-case estimate and claim disjoint items."""
    schedule_corrections(db)
    cap = min(int(request['estimated_limit_usd'])*1_000_000,LIMIT)
    db.execute('BEGIN IMMEDIATE')
    used = db.execute('SELECT coalesce(sum(cost),0) FROM jobs').fetchone()[0]
    used += reconciliation.extra_cost(db)
    used += db.execute('SELECT coalesce(sum(cost),0) FROM previous_captions').fetchone()[0]
    pilot = int(db.execute("SELECT value FROM config WHERE key='pilot_cost'").fetchone()[0])
    blocked = db.execute("SELECT value FROM config WHERE key='blocked'").fetchone()
    parallel = int(request.get('parallel', 2))
    if not 1 <= parallel <= 20:
        db.rollback()
        raise ValueError('Invalid Luna concurrency')
    limit = min(48,int(request['batch_size']),max(0,(cap-used-pilot)//RESERVE))
    rows = [] if blocked else db.execute("SELECT id,path,size_bytes,ext,metadata FROM jobs WHERE state='pending' AND available_after<=unixepoch() ORDER BY id LIMIT ?",[limit]).fetchall()
    batch = uuid.uuid4().hex
    db.executemany("UPDATE jobs SET state='reserved',batch=?,cost=?,started=CURRENT_TIMESTAMP WHERE id=?",[(batch,RESERVE,row[0]) for row in rows])
    db.execute("INSERT OR REPLACE INTO config VALUES ('parallel',?)",[str(parallel)])
    db.commit()
    return dict(batch=batch,items=[dict(id=r[0],path=r[1],size=r[2],ext=r[3],metadata=json.loads(r[4])) for r in rows],
                held_or_used_usd=(used+pilot)/1e6,blocked=bool(blocked))


def frames(db, request):
    """Prepare only the requested reserved item using the canonical source."""
    path,size,ext = db.execute("SELECT path,size_bytes,ext FROM jobs WHERE id=? AND batch=? AND state='reserved'",
                              [request['id'],request['batch']]).fetchone()
    file = (LIBRARY/path).resolve()
    if not file.is_relative_to(LIBRARY) or file.stat().st_size != size:
        raise ValueError('Source changed')
    if ext in VIDEO_EXTS:
        duration = video_duration(str(file))
        n = min(8,max(1,int(duration)))
        images = []
        for i in range(n):
            try:
                images.append(jpeg_frame(str(file),duration*(i+.5)/n))
            except RuntimeError:
                # Containers can extend past their last decodable video frame.
                continue
        if not images:
            images = [jpeg_frame(str(file),0)]
    else:
        images = [jpeg_frame(str(file))]
    return dict(images=[base64.b64encode(b).decode() for b in images])


def projected_cost(db, ext):
    """Use twice the highest observed cost for the same media type."""
    video_formats = tuple(sorted(VIDEO_EXTS))
    placeholders = ','.join('?' for _ in video_formats)
    same_kind = f'(ext IN ({placeholders})) = ?'
    observed = db.execute(
        f"SELECT max(cost) FROM jobs WHERE state='ok' AND {same_kind}",
        (*video_formats, ext in VIDEO_EXTS),
    ).fetchone()[0]
    return min(RESERVE, max(MIN_PROJECTION, 2 * observed)) if observed is not None else RESERVE


def recover(db):
    """Release unsent leases and account for interrupted submissions without retrying them."""
    db.execute('BEGIN IMMEDIATE')
    with db:
        if not db.execute("SELECT 1 FROM config WHERE key='location_deferrals_cleared'").fetchone():
            db.execute("UPDATE jobs SET available_after=0 WHERE state='pending' AND available_after>0")
            db.execute("INSERT INTO config VALUES ('location_deferrals_cleared','1')")
        db.execute("UPDATE jobs SET state='pending',cost=0,batch=NULL WHERE state='reserved' AND started<datetime('now','-45 minutes')")
        stale = db.execute("SELECT id,ext FROM jobs WHERE state='sent' AND started<datetime('now','-45 minutes')").fetchall()
        for job_id, ext in stale:
            db.execute("""UPDATE jobs SET state='unknown',cost=?,finished=CURRENT_TIMESTAMP,
                          result='{}' WHERE id=?""", (projected_cost(db, ext), job_id))
        hold = db.execute("SELECT value FROM config WHERE key='blocked'").fetchone()
        if hold and hold[0] in LEGACY_HOLDS:
            for job_id, ext in db.execute("SELECT id,ext FROM jobs WHERE state='unknown' AND cost=?", (RESERVE,)).fetchall():
                db.execute("UPDATE jobs SET cost=? WHERE id=?", (projected_cost(db, ext), job_id))
            overrun = db.execute("""SELECT 1 FROM jobs WHERE state='ok' AND cost>?
                                     UNION ALL SELECT 1 FROM previous_captions WHERE cost>? LIMIT 1""",
                                 (RESERVE, RESERVE)).fetchone()
            if overrun:
                db.execute("UPDATE config SET value='reported usage exceeded reservation' WHERE key='blocked'")
            else:
                db.execute("DELETE FROM config WHERE key='blocked'")
    return {'recovered_unknown':len(stale)}


def finish(db, request):
    """Settle each reservation once, projecting cost when the CLI usage is missing."""
    db.execute('BEGIN IMMEDIATE')
    with db:
        for row in request['results']:
            state = row['state']
            expected_state = 'reserved' if state == 'source_error' else 'sent'
            job = db.execute("SELECT ext FROM jobs WHERE id=? AND batch=? AND state=?",
                             (row['id'], request['batch'], expected_state)).fetchone()
            if not job:
                continue
            if state == 'source_error':
                cost = 0  # No CLI invocation.
            elif state == 'ok':
                i,c,o = (row[k] for k in ['input','cached','output'])
                if not (0 <= c <= i and o >= 0):
                    raise ValueError('Invalid token usage')
                mult = 2 if i>272000 else 1
                # Ceiling to a microdollar. Cached input is included in total input.
                cost = ((i-c)*10*mult+c*mult+o*(75 if mult==2 else 50)+99)//100
            elif state == 'unknown':
                cost = projected_cost(db, job[0])
            else:
                raise ValueError('Invalid outcome')
            if cost>RESERVE:
                db.execute("INSERT OR REPLACE INTO config VALUES ('blocked','reported usage exceeded reservation')")
            db.execute("""UPDATE jobs SET state=?,cost=?,result=?,finished=CURRENT_TIMESTAMP
                          WHERE id=? AND batch=?""",
                       [state,cost,json.dumps(row),row['id'],request['batch']])
    return {'recorded':len(request['results'])}


def publish(db):
    """Publish settled batches atomically in a separate, private Parquet dataset."""
    dest=ROOT/'luna_codex_captions'
    dest.mkdir(exist_ok=True)
    db.execute('BEGIN IMMEDIATE')
    try:
        batches=db.execute("""SELECT coalesce(origin_batch,batch) FROM jobs WHERE coalesce(origin_batch,batch) IS NOT NULL
                              GROUP BY coalesce(origin_batch,batch) HAVING min(published)=0 AND sum(state IN ('pending','reserved','sent'))=0""").fetchall()
        for (batch,) in batches:
            con=duckdb.connect()
            try:
                con.execute("""CREATE TABLE captions(source_path VARCHAR,size_bytes BIGINT,model VARCHAR,
                    prompt_version VARCHAR,kind VARCHAR,saved_context JSON,summary VARCHAR,tags VARCHAR[],
                    input_tokens BIGINT,cached_input_tokens BIGINT,output_tokens BIGINT,elapsed_seconds DOUBLE,
                    standard_api_cost_proxy_usd DOUBLE,state VARCHAR,finished_at TIMESTAMP)""")
                records=[]
                for path,size,ext,meta,result,cost,state,ts in db.execute('SELECT path,size_bytes,ext,metadata,result,cost,state,finished FROM jobs WHERE coalesce(origin_batch,batch)=?',[batch]):
                    r=json.loads(result)
                    records.append((path,size,MODEL,r.get('prompt_version','saved-context-v2'),
                                    'video' if ext in VIDEO_EXTS else 'photo',meta,
                                    r.get('summary'),r.get('tags'),r.get('input'),r.get('cached'),r.get('output'),
                                    r.get('seconds'),cost/1e6 if state=='ok' else None,state,ts))
                con.executemany('INSERT INTO captions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',records)
                tmp=dest/(batch+'.tmp')
                con.execute('COPY captions TO ? (FORMAT PARQUET, COMPRESSION ZSTD)',[str(tmp)])
                tmp.replace(dest/(batch+'.parquet'))
            finally:
                con.close()
            db.execute('UPDATE jobs SET published=1 WHERE coalesce(origin_batch,batch)=?',[batch])
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'published':len(batches)}


def export_metrics(db):
    """Publish aggregate progress without paths, captions, names, or coordinates."""
    dest=Path('/var/lib/prometheus/node-exporter/knowledge_index_luna.prom')
    rows=db.execute("SELECT state,count(*),sum(cost),sum(published) FROM jobs GROUP BY state").fetchall()
    costs={state:total/1e6 for state,_,total,_ in rows}
    settled=costs.get('ok',0)+costs.get('unknown',0)+db.execute('SELECT coalesce(sum(cost),0) FROM previous_captions').fetchone()[0]/1e6
    held=sum(costs.get(state,0) for state in ('sent','reserved'))
    prior=int(db.execute("SELECT value FROM config WHERE key='pilot_cost'").fetchone()[0])/1e6
    saved=sum(n for state,_,_,n in rows if state=='ok')
    # The original Parquet file remains readable until its corrected batch is
    # atomically replaced. Count those captions throughout the retry.
    saved+=db.execute("""SELECT count(*) FROM previous_captions h JOIN jobs j ON j.id=h.job_id
                         WHERE h.original_state='ok' AND j.published=0""").fetchone()[0]
    content=[f'knowledge_index_luna_saved {saved}',
             f'knowledge_index_luna_proxy_usd {settled}',
             f'knowledge_index_luna_budget_held_usd {prior+held}']
    counts = {state: n for state, n, _, _ in rows}
    for state in ("pending", "reserved", "sent", "ok", "unknown", "source_error"):
        content.append(f'knowledge_index_luna_jobs{{state="{state}"}} {counts.get(state, 0)}')
    unpublished = db.execute("SELECT count(*) FROM jobs WHERE state='ok' AND published=0").fetchone()[0]
    blocked = db.execute("SELECT EXISTS(SELECT 1 FROM config WHERE key='blocked' AND value!='')").fetchone()[0]
    runner = db.execute("SELECT value FROM config WHERE key='runner'").fetchone()
    parallel = db.execute("SELECT value FROM config WHERE key='parallel'").fetchone()
    content.append(f'knowledge_index_luna_parallel {int(parallel[0]) if parallel else 2}')
    content.append(f'knowledge_index_luna_runner {2 if runner and runner[0]=="still-fawn" else 1}')
    content.extend([f'knowledge_index_luna_awaiting_publish {unpublished}', f'knowledge_index_luna_blocked {blocked}',
                    f'knowledge_index_luna_heartbeat_timestamp_seconds {int(time.time())}'])
    tmp=dest.with_name(dest.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text('\n'.join(content)+'\n')
    tmp.chmod(0o644)
    tmp.replace(dest)


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    request=json.load(sys.stdin)
    op=request['op']
    if os.environ.get('KI_LUNA_BRIDGE') == '1' and op not in {
        'status','recover','reserve','frames','start','finish','release','publish',
        'reconcile_status','reconcile_recover','reconcile_reserve','reconcile_start',
        'reconcile_finish','reconcile_release','reconcile_publish','reconcile_discover'
    }:
        raise ValueError('Unexpected bridge operation')
    with sqlite3.connect(ROOT/'luna-ledger.sqlite3',timeout=60) as db:
        db.executescript("""CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,path TEXT,size_bytes INTEGER,ext TEXT,metadata TEXT,
            state TEXT DEFAULT 'pending',batch TEXT,cost INTEGER DEFAULT 0,result TEXT,started TEXT,finished TEXT,published INTEGER DEFAULT 0,
            UNIQUE(path,size_bytes));
            CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(state,id);
            CREATE INDEX IF NOT EXISTS jobs_batch ON jobs(batch);""")
        migrate(db)
        if op.startswith('reconcile_'):
            result=reconciliation.handle(db,ROOT,request)
            if op in ('reconcile_publish','reconcile_skip_unresolved'):
                reconciliation.export_metrics(db,Path('/var/lib/prometheus/node-exporter/knowledge_index_reconciliation.prom'))
            print(json.dumps(result,ensure_ascii=False))
            return
        if op=='init':
            if not 0 < request['pilot_microdollars'] <= 1_000_000:
                raise ValueError('Invalid prior pilot estimate')
            db.execute("INSERT OR IGNORE INTO config VALUES ('pilot_cost',?)",[str(request['pilot_microdollars'])])
            db.commit()
            seed(db)
        if op in ('init','status'):
            result=dict(states=dict(db.execute('SELECT state,count(*) FROM jobs GROUP BY state')),
                        estimated_and_held_usd=(db.execute('SELECT coalesce(sum(cost),0) FROM jobs').fetchone()[0]+int(db.execute("SELECT value FROM config WHERE key='pilot_cost'").fetchone()[0])+db.execute('SELECT coalesce(sum(cost),0) FROM previous_captions').fetchone()[0])/1e6)
        elif op=='recover':
            result=recover(db)
            runner='still-fawn' if os.environ.get('KI_LUNA_BRIDGE')=='1' else 'mac'
            with db:
                db.execute("INSERT OR REPLACE INTO config VALUES ('runner',?)",[runner])
        elif op=='start':
            with db:
                count=db.execute("UPDATE jobs SET state='sent',started=CURRENT_TIMESTAMP WHERE id=? AND batch=? AND state='reserved'",[request['id'],request['batch']]).rowcount
            if count!=1:raise ValueError('Already submitted or not reserved')
            result={'started':True}
        elif op=='release':
            with db:
                db.execute("UPDATE jobs SET state='pending',batch=NULL,cost=0 WHERE batch=? AND state='reserved'",[request['batch']])
            result={'released':True}
        elif op=='publish':result=publish(db)
        elif op=='frames':
            try:result=frames(db,request)
            except (ValueError,OSError,RuntimeError) as e:result={'source_error':type(e).__name__}
        elif op=='reserve':result=add_context(db,reserve(db,request))
        elif op=='finish':result=finish(db,request)
        else:raise ValueError('Unexpected operation')
        if op in ('init','publish','reserve','start','finish','release','recover'):
            export_metrics(db)
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
