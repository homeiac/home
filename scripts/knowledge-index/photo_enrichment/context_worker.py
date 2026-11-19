"""Durable GPS-context backfill; preserves original captions and human annotations."""
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

from . import places
from .metadata import contained
from .postgres import connect
from .snapshots import analytical_connection
from .telemetry import get_telemetry

VERSION='gps-context-v1'
SCHEMA="""
CREATE TABLE IF NOT EXISTS photo_context (
 path text PRIMARY KEY, size_bytes bigint NOT NULL, input_hash text NOT NULL,
 input jsonb NOT NULL, status text NOT NULL DEFAULT 'ready', attempts integer NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 summary text, tags text[], model text, context jsonb, error_type text);
CREATE INDEX IF NOT EXISTS photo_context_ready ON photo_context(status,available_at);
CREATE TABLE IF NOT EXISTS photo_place_cache (
 key text PRIMARY KEY, context jsonb NOT NULL, retrieved_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS photo_place_budget (
 id integer PRIMARY KEY CHECK(id=1), day date NOT NULL DEFAULT current_date,
 requests integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now());
INSERT INTO photo_place_budget(id) VALUES(1) ON CONFLICT DO NOTHING;
"""


def initialize(connection):
    with connection.transaction():connection.execute(SCHEMA)


def seed(connection,state,model):
    """Stream one pinned analytical generation; no library-wide remote SELECT."""
    reader,manifest=analytical_connection(state)
    try:
        rows=reader.execute("""SELECT m.path,m.size_bytes,m.latitude,m.longitude,m.summary,m.capture_ts
            FROM enriched_media m WHERE m.latitude IS NOT NULL AND m.longitude IS NOT NULL AND m.summary IS NOT NULL
            AND NOT EXISTS(SELECT 1 FROM album_duplicates d WHERE d.path=m.path)""")
        with connection.transaction():
            connection.execute('CREATE TEMP TABLE context_seed(path text,size_bytes bigint,input_hash text,input jsonb) ON COMMIT DROP')
            with connection.cursor().copy('COPY context_seed FROM STDIN') as copy:
                while batch:=rows.fetchmany(256):
                    for path,size,lat,lon,summary,captured in batch:
                        try:places.coordinates(lat,lon)
                        except (ValueError,TypeError):continue
                        data=dict(latitude=lat,longitude=lon,original_summary=summary,capture_ts=captured,version=VERSION,model=model)
                        encoded=json.dumps(data,sort_keys=True)
                        copy.write_row((path,size,hashlib.sha256(encoded.encode()).hexdigest(),encoded))
            connection.execute("""INSERT INTO photo_context(path,size_bytes,input_hash,input)
                SELECT * FROM context_seed ON CONFLICT(path) DO UPDATE SET size_bytes=excluded.size_bytes,
                input_hash=excluded.input_hash,input=excluded.input,status='ready',attempts=0,available_at=now(),
                summary=NULL,tags=NULL,context=NULL,error_type=NULL,updated_at=now()
                WHERE photo_context.input_hash<>excluded.input_hash OR photo_context.size_bytes<>excluded.size_bytes""")
        return manifest['generation']
    finally:reader.close()


def lookup(connection,lat,lon,provider=places.nearby,daily_budget=1000):
    key=places.cache_key(lat,lon)
    cached=connection.execute('SELECT context FROM photo_place_cache WHERE key=%s',[key]).fetchone()
    if cached:return cached[0],True
    # The session advisory lock in run() serializes all provider calls. Reserve a
    # daily budget slot durably, and never hold a transaction across the network.
    allowed=connection.execute("""UPDATE photo_place_budget SET day=current_date,
        requests=CASE WHEN day=current_date THEN requests+1 ELSE 1 END,
        available_at=now()+interval '20 seconds' WHERE id=1 AND available_at<=now()
        AND (day<>current_date OR requests<%s) RETURNING requests""",[daily_budget]).fetchone()
    if not allowed:raise places.LookupDeferred(60)
    try:
        context=provider(lat,lon)
    except places.LookupDeferred as error:
        connection.execute("UPDATE photo_place_budget SET available_at=now()+(%s * interval '1 second') WHERE id=1",[error.seconds])
        raise
    finally:
        # Five seconds after completion, including slow/failed requests.
        connection.execute("UPDATE photo_place_budget SET available_at=greatest(available_at,now()+interval '5 seconds') WHERE id=1")
    context['retrieved_at']=time.time()
    connection.execute('INSERT INTO photo_place_cache(key,context) VALUES(%s,%s) ON CONFLICT DO NOTHING',[key,json.dumps(context)])
    return context,False


def process(*args,**kwargs):
    """Give each complete job one trace shared by all stage spans and logs."""
    with get_telemetry().stage('context.job'):
        return _process(*args,**kwargs)


def _process(connection,library,endpoint,model,metrics,provider=places.nearby,infer=None,first_photo=""):
    """One durable job, with retries; singleton session lock fences worker restarts."""
    row=connection.execute("""UPDATE photo_context SET status='running',attempts=attempts+1,updated_at=now()
        WHERE path=(SELECT path FROM photo_context WHERE status IN ('ready','retry') AND available_at<=now()
        ORDER BY (regexp_replace(path,'^.*/','')=%s) DESC,attempts,(input->>'capture_ts')::double precision DESC NULLS LAST,path LIMIT 1)
        RETURNING path,size_bytes,input_hash,input,attempts""",[first_photo]).fetchone()
    if not row:return False
    path,size,digest,data,attempts=row
    telemetry=get_telemetry()
    from opentelemetry import trace
    trace_id=format(trace.get_current_span().get_span_context().trace_id,'032x')
    started=time.monotonic()
    try:
        with metrics.measure('location'),telemetry.stage('context.location_lookup'):
            context,hit=lookup(connection,data['latitude'],data['longitude'],provider)
            metrics.inventory['cache_hits' if hit else 'provider_requests']=metrics.inventory.get('cache_hits' if hit else 'provider_requests',0)+1
        summary,tags=None,[]
        if context['candidates']:
            source=contained(library,path)
            if source.stat().st_size!=size:raise ValueError('Source size changed')
            prompt=('Describe this photo factually in 1-3 sentences, using the location references only when visually supported. '
                'Return JSON with summary and up to 8 tags. Do not identify people.\n'+
                places.prompt_context(context,data['latitude'],data['longitude']))
            with metrics.measure('context_llm'),telemetry.stage('context.llm'):
                if infer:summary,tags=infer(source,prompt)
                else:
                    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'enrichers'))
                    from media_summary import jpeg_frame,ask_model,parse_answer
                    summary,tags=parse_answer(ask_model(endpoint,model,prompt,[jpeg_frame(str(source))],
                        timeout=180,api='ollama',extra={'think':False}))
            if source.stat().st_size!=size:raise ValueError('Source changed during inference')
        with metrics.measure('context_save'),telemetry.stage('context.persist'):
            connection.execute("""UPDATE photo_context SET status='done',summary=%s,tags=%s,model=%s,context=%s,
                error_type=NULL,updated_at=now() WHERE path=%s AND input_hash=%s""",
                [summary,tags,model,json.dumps(context),path,digest])
        telemetry.emit('context.finished',trace_id=trace_id,duration_seconds=round(time.monotonic()-started,3),cache_hit=hit,
            candidates=len(context['candidates']),caption_generated=bool(summary))
    except Exception as error:
        deferred=isinstance(error,places.LookupDeferred)
        seconds=error.seconds if deferred else min(3600,30*2**min(attempts,7))
        connection.execute("""UPDATE photo_context SET status=%s,available_at=now()+(%s * interval '1 second'),
            attempts=attempts-%s,error_type=%s,updated_at=now() WHERE path=%s AND input_hash=%s""",
            ['retry' if deferred or attempts<5 else 'failed',seconds,int(deferred),type(error).__name__,path,digest])
        telemetry.emit('context.deferred' if deferred else 'context.error',trace_id=trace_id,error_type=type(error).__name__,retry_seconds=seconds)
    return True


def run(state,library,endpoint,model,metrics,max_jobs=0,first_photo=""):
    with connect() as connection:
        initialize(connection)
        if not connection.execute('SELECT pg_try_advisory_lock(217,8)').fetchone()[0]:
            raise RuntimeError('Another context worker is running')
        connection.execute("UPDATE photo_context SET status='retry' WHERE status='running'")
        last_seed=0;count=0
        while not max_jobs or count<max_jobs:
            if time.monotonic()-last_seed>300:
                with metrics.measure('context_queue'):seed(connection,state,model)
                last_seed=time.monotonic()
            metrics.jobs={status:n for status,n in connection.execute('SELECT status,count(*) FROM photo_context GROUP BY status').fetchall()}
            if process(connection,library,endpoint,model,metrics,first_photo=first_photo):count+=1
            elif max_jobs:break
            time.sleep(5)
