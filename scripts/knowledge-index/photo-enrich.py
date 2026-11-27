#!/usr/bin/env python3
"""Browse, extract, annotate, and query photo enrichment in a separate store (#217)."""
import argparse
import json
import logging
import sys
from pathlib import Path

from photo_enrichment.faces import MODEL_ID, FaceEngine, download_models
from photo_enrichment.server import make_server
from photo_enrichment.store import Store
from photo_enrichment.metrics import Metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("duckdb", "postgres"), default="duckdb")
    parser.add_argument("--index", type=Path, help="Read-only knowledge-index directory")
    parser.add_argument("--library", type=Path, help="Read-only photo library root containing Google Photos/")
    parser.add_argument("--state", type=Path, required=True, help="Separate writable enrichment directory")
    parser.add_argument("--models", type=Path, help="Model directory (default STATE/models)")
    parser.add_argument("--prom", type=Path, help="Node-exporter textfile path for live value-stream telemetry")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("models", help="Download and checksum official YuNet + SFace CPU models")
    serve = commands.add_parser("serve")
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--public-origin", help="Exact internal Traefik HTTPS origin when deployed")
    serve.add_argument("--cricket-ledger", type=Path, help="Enable cricket review using this private ledger")
    serve.add_argument("--cricket-owner", help="Fixed library owner for cricket access; never supplied by the browser")
    extract = commands.add_parser("extract")
    extract.add_argument("--limit", type=int, default=50)
    extract.add_argument("--date", help="Capture date YYYY-MM-DD or unknown; omit for a bounded library pass")
    extract.add_argument("--timezone", default="UTC")
    extract.add_argument("--faces", action="store_true")
    extract.add_argument("--force", action="store_true", help="Re-read metadata; confirmed face labels are retained")
    commands.add_parser("migrate", help="Import a quiesced legacy DuckDB into PostgreSQL once")
    commands.add_parser("refresh-catalog", help="Refresh PostgreSQL catalog from existing Parquet-backed index")
    commands.add_parser("export", help="Export Parquet snapshots of enrichment and annotation tables")
    commands.add_parser("triage", help="Read-only bounded HTTP, DB wait and resource diagnostics")
    context = commands.add_parser("context-worker", help="Cached GPS lookup and local contextual captions")
    context.add_argument('--endpoint',required=True)
    context.add_argument('--model',required=True)
    context.add_argument('--api', choices=['ollama', 'openai'], default='ollama')
    context.add_argument('--seed-model', help='Keep the previous context fingerprint when changing inference backends')
    context.add_argument('--max-jobs',type=int,default=0)
    context.add_argument('--first-photo',default='',help='Prioritize one filename for rollout verification')
    worker = commands.add_parser("worker", help="Continuously extract pending photos and publish Parquet/telemetry")
    worker.add_argument("--batch-size", type=int, default=25)
    worker.add_argument("--timezone", default="UTC")
    worker.add_argument("--metadata-only", action="store_true")
    worker.add_argument("--pause-seconds", type=float, default=2)
    worker.add_argument("--idle-seconds", type=float, default=60)
    worker.add_argument("--max-batches", type=int, default=0, help="Stop after N batches; zero runs continuously")
    query = commands.add_parser("query", help="Read-only SQL over enriched_media and annotation tables")
    query.add_argument("sql")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    models = args.models or args.state / "models"
    if args.command == "models":
        download_models(models)
        logging.info("Verified models in %s", models)
        return
    if not args.index or not args.library:
        parser.error("--index and --library are required")
    from photo_enrichment.telemetry import get_telemetry
    telemetry=get_telemetry()
    if args.command in ('serve','triage','context-worker'):telemetry.start()
    if args.command=='triage':
        from photo_enrichment.triage import run as run_triage
        try:run_triage(args.state,args.prom)
        finally:telemetry.close()
        return
    metrics = Metrics(args.prom)
    if args.command=='context-worker':
        if args.backend!='postgres':parser.error('Context worker requires PostgreSQL')
        from photo_enrichment.context_worker import run
        metrics.prefix='photo_context'
        metrics.stages=('context_queue','location','context_llm','context_save')
        try:
            with metrics:
                run(args.state,args.library,args.endpoint,args.model,metrics,args.max_jobs,args.first_photo,
                    api=args.api,seed_model=args.seed_model)
        finally:telemetry.close()
        return
    if args.backend == "postgres" and args.command == "serve":
        metrics.prefix="photo_review"
        metrics.stages=("review","frigate","match","auto_accept")
    if args.command == "worker":
        from zoneinfo import ZoneInfo
        if args.backend == "postgres":
            from photo_enrichment.postgres import run_worker as run
        else:
            from photo_enrichment.worker import run
        ZoneInfo(args.timezone)
        if not 1 <= args.batch_size <= 1000 or args.max_batches < 0 or args.pause_seconds < 0 or args.idle_seconds < 1:
            parser.error("Invalid worker batch size, count or polling interval")
        with metrics:
            run(args.index, args.library, args.state, models, metrics, args.batch_size,
                args.timezone, not args.metadata_only, args.pause_seconds, args.idle_seconds, args.max_batches)
        return
    if args.command in ("migrate", "refresh-catalog"):
        from photo_enrichment.postgres import connect, migrate, refresh_catalog
        with connect() as connection:
            result = migrate(connection,args.index,args.state) if args.command == "migrate" else refresh_catalog(connection,args.index)
        logging.info("%s counts: %s",args.command,result)
        return
    if args.backend == "postgres" and args.command == "export":
        from photo_enrichment.snapshots import export_snapshot
        result = export_snapshot(args.state,args.prom)
        logging.info("Snapshot published: %s",result.get("generation","already running"))
        return
    if args.backend == "postgres" and args.command == "query":
        from photo_enrichment.snapshots import analytical_connection
        connection,manifest = analytical_connection(args.state)
        try:
            statements=connection.extract_statements(args.sql)
            if len(statements)!=1 or str(statements[0].type)!="StatementType.SELECT": parser.error("query accepts one SELECT")
            cursor=connection.execute(args.sql)
            print(json.dumps([dict(zip([c[0] for c in cursor.description],r)) for r in cursor.fetchall()],default=str,indent=2))
        finally: connection.close()
        return
    if args.backend == "postgres":
        from photo_enrichment.postgres import PostgresStore
        store = PostgresStore(args.index,args.library,args.state,metrics)
    else:
        store = Store(args.index, args.library, args.state, metrics)
    metrics.__enter__()
    try:
        store.refresh_metrics()
        if args.command == "serve":
            cricket = None
            if bool(args.cricket_ledger) != bool(args.cricket_owner):
                parser.error('--cricket-ledger and --cricket-owner must be supplied together')
            if args.cricket_ledger:
                from cricket.api import CricketAPI
                from cricket.ledger import Ledger
                cricket = CricketAPI(Ledger(args.cricket_ledger), args.cricket_owner, args.library)
            server = make_server(store, models, args.bind, args.port, args.public_origin, cricket=cricket)
            logging.info("Photo enrichment: http://%s:%s", args.bind, server.server_port)
            import threading
            stop=threading.Event()
            automatic=None
            automatic_store=None
            if args.backend=='postgres':
                from photo_enrichment.auto_accept import run as run_auto_accept
                automatic_store=PostgresStore(args.index,args.library,args.state,metrics)
                store.suggestion_source=automatic_store
                automatic=threading.Thread(target=run_auto_accept,args=(automatic_store,stop),daemon=True)
                automatic.start()
            try:
                server.serve_forever()
            finally:
                stop.set()
                if automatic:automatic.join()
                if automatic_store:automatic_store.close()
                server.server_close()
        elif args.command == "extract":
            if args.backend == "postgres": parser.error("PostgreSQL extraction runs through durable worker jobs")
            if not 1 <= args.limit <= 1000:
                parser.error("--limit must be between 1 and 1000")
            if args.date:
                # Fetch through the same date-group rules as the UI (including album duplicate exclusion).
                paths = []
                while len(paths) < args.limit:
                    page = store.photos(args.date, args.timezone, len(paths), min(200, args.limit-len(paths)))
                    paths.extend(p["path"] for p in page["photos"])
                    if len(paths) >= page["total"]:
                        break
            else:
                order = "(fs.path IS NOT NULL), " if args.faces else ""
                paths = [row["path"] for row in store.rows("""SELECT m.path FROM enriched_media m
                    LEFT JOIN extracted e ON e.path=m.path
                    LEFT JOIN face_scans fs ON fs.path=m.path AND fs.size_bytes=m.size_bytes AND fs.model=?
                    WHERE NOT EXISTS (SELECT 1 FROM catalog.gphotos_album_dup d WHERE d.path=m.path)
                    ORDER BY """ + order + "e.updated_at NULLS FIRST, m.path LIMIT ?", [MODEL_ID, args.limit])]
            result = store.extract(paths, args.timezone, FaceEngine(models) if args.faces else None, args.force) if paths else {"processed": 0}
            logging.info("Extraction: %s", json.dumps(result))
            store.export()
        elif args.command == "export":
            logging.info("Export: %s", json.dumps(store.export()))
        elif args.command == "query":
            statements = store.db.extract_statements(args.sql)
            if len(statements) != 1 or str(statements[0].type) != "StatementType.SELECT":
                parser.error("query accepts one SELECT statement only")
            print(json.dumps(store.rows(args.sql), default=str, indent=2))
    finally:
        metrics.__exit__(*sys.exc_info())
        store.close()
        if args.command=='serve':telemetry.close()


if __name__ == "__main__":
    main()
