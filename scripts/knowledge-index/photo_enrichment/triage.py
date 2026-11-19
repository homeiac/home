"""Bounded, read-only incident diagnosis scheduled independently of the GUI."""
import json
import os
from pathlib import Path
import time
import urllib.request

from .telemetry import get_telemetry

DIAGNOSIS={
    'healthy':'HTTP and database-backed readiness probes succeeded.',
    'service_unreachable':'The independent HTTP liveness probe failed; check the GUI service and listener.',
    'postgres_blocked':'PostgreSQL reports lock waits or blocking sessions; inspect the database_waits evidence.',
    'slow_postgres_query':'An active PostgreSQL query is older than ten seconds; open the request trace and query fingerprint.',
    'slow_duckdb_query':'An unfinished request is in DuckDB; inspect the query span and CPU/memory pressure.',
    'slow_thumbnail':'An unfinished request is waiting for or decoding a thumbnail; compare thumbnail.queue/read_decode spans with memory and I/O pressure.',
    'application_lock':'Requests are waiting for the application connection lock; inspect the other active requests to find the holder.',
    'resource_pressure':'GUI cgroup pressure exceeds the diagnostic threshold; inspect the pressure resource and active request stages.',
    'slow_application_operation':'A request is unfinished after ten seconds; follow its trace ID and current stage.',
    'api_unavailable':'HTTP liveness succeeded but the database-backed API probe failed; inspect request errors and database connectivity.'}


def classify(probes,diagnostics,waits,pressure):
    if not probes.get('health',False):return 'service_unreachable'
    if any(row['blockers'] or row['wait_type']=='Lock' for row in waits):return 'postgres_blocked'
    if any(row['state']=='active' and row['age_seconds']>=10 for row in waits):return 'slow_postgres_query'
    if any(row['stage']=='duckdb.query' and row['age_seconds']>=10 for row in diagnostics.get('requests',[])):return 'slow_duckdb_query'
    if any(row['stage'].startswith('thumbnail.') and row['age_seconds']>=10 for row in diagnostics.get('requests',[])):return 'slow_thumbnail'
    if diagnostics.get('lock_waiters',0):return 'application_lock'
    if any(value>=20 for value in pressure.values()):return 'resource_pressure'
    if diagnostics.get('oldest_request',0)>=10:return 'slow_application_operation'
    if not probes.get('api',False):return 'api_unavailable'
    return 'healthy'


def collect():
    probes={};timings={};diagnostics={}
    for name,path in [('health','/healthz'),('api','/api/status'),('diagnostics','/api/diagnostics')]:
        started=time.monotonic()
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765'+path,timeout=3) as response:
                payload=json.loads(response.read(262144));probes[name]=response.status==200
                if name=='diagnostics':diagnostics=payload
        except Exception:probes[name]=False
        timings[name]=round(time.monotonic()-started,3)
    waits=[]
    if not probes.get('api') or diagnostics.get('oldest_request',0)>=10:
        try:
            import psycopg
            with psycopg.connect(service=os.environ.get('PHOTO_PG_SERVICE','photo_pipeline'),connect_timeout=2) as connection:
                connection.execute("SET statement_timeout='1500ms'")
                result=connection.execute("""SELECT state,coalesce(wait_event_type,'none') AS wait_type,
                    coalesce(wait_event,'none') AS wait_event,extract(epoch FROM now()-query_start)::double precision AS age_seconds,
                    cardinality(pg_blocking_pids(pid)) AS blockers FROM pg_stat_activity
                    WHERE datname=current_database() AND usename=current_user AND pid<>pg_backend_pid() LIMIT 30""")
                names=[c.name for c in result.description];waits=[dict(zip(names,row)) for row in result.fetchall()]
        except Exception as exc:diagnostics['database_error']=type(exc).__name__
    pressure={}
    for resource in ('cpu','memory','io'):
        try:
            line=Path('/sys/fs/cgroup/system.slice/photo-enrichment-gui.service',resource+'.pressure').read_text().splitlines()[0]
            pressure[resource]=float(next(item.split('=')[1] for item in line.split() if item.startswith('avg10=')))
        except (OSError,StopIteration,ValueError):pass
    category=classify(probes,diagnostics,waits,pressure)
    return dict(checked_at=time.time(),category=category,diagnosis=DIAGNOSIS[category],probes=probes,timings=timings,pressure=pressure,
        database_waits=waits,requests=diagnostics.get('requests',[]),database_error=diagnostics.get('database_error'))


def run(state: Path,prom: Path):
    """Publish evidence and health metrics; never restart services or alter data."""
    from .snapshots import atomic_json
    report=collect()
    directory=state/'observability';directory.mkdir(parents=True,exist_ok=True)
    atomic_json(directory/'triage-latest.json',report)
    rows=['# HELP photo_app_probe_success Independent photo HTTP probe success','# TYPE photo_app_probe_success gauge']
    rows.extend(['# HELP photo_app_edge_info Gallery snapshot and live review data flow',
        '# TYPE photo_app_edge_info gauge',
        'photo_app_edge_info{id="snapshot-gallery",source="photo_analytics",target="photo_gallery"} 1',
        'photo_app_edge_info{id="live-edits-gallery",source="photo_live_db",target="photo_gallery"} 1'])
    rows.extend(f'photo_app_probe_success{{probe="{name}"}} {int(success)}' for name,success in report['probes'].items())
    rows.extend(['# HELP photo_app_triage_timestamp_seconds Latest bounded automatic diagnostic run',
        '# TYPE photo_app_triage_timestamp_seconds gauge',f'photo_app_triage_timestamp_seconds {report["checked_at"]}',
        '# HELP photo_app_triage_incident Current diagnostic classification is unhealthy',
        '# TYPE photo_app_triage_incident gauge',f'photo_app_triage_incident {int(report["category"]!="healthy")}'])
    temporary=prom.with_suffix('.prom.tmp');temporary.write_text('\n'.join(rows)+'\n');temporary.chmod(0o644);temporary.replace(prom)
    get_telemetry().emit('triage.result',**report)
    return report
