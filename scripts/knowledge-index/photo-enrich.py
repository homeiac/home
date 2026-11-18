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
    extract = commands.add_parser("extract")
    extract.add_argument("--limit", type=int, default=50)
    extract.add_argument("--date", help="Capture date YYYY-MM-DD or unknown; omit for a bounded library pass")
    extract.add_argument("--timezone", default="UTC")
    extract.add_argument("--faces", action="store_true")
    extract.add_argument("--force", action="store_true", help="Re-read metadata; confirmed face labels are retained")
    commands.add_parser("export", help="Export Parquet snapshots of enrichment and annotation tables")
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
    metrics = Metrics(args.prom)
    store = Store(args.index, args.library, args.state, metrics)
    metrics.__enter__()
    try:
        store.refresh_metrics()
        if args.command == "serve":
            server = make_server(store, models, args.bind, args.port, args.public_origin)
            logging.info("Photo enrichment: http://%s:%s", args.bind, server.server_port)
            try:
                server.serve_forever()
            finally:
                server.server_close()
        elif args.command == "extract":
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


if __name__ == "__main__":
    main()
