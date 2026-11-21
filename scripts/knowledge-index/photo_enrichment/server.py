"""Small same-origin photo review UI; bind to loopback unless explicitly configured."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import secrets
import urllib.parse

from .faces import FaceEngine, frigate_candidate
from .telemetry import get_telemetry

STATIC = Path(__file__).parent / "static"


def make_server(store, models: Path, bind: str, port: int, public_origin: str | None = None):
    """Serve previews and annotation commands without arbitrary filesystem or SQL access."""
    token = secrets.token_urlsafe(32)
    engine = None
    root_store=store
    if hasattr(store,'enable_pooling'):store.enable_pooling()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def log_message(self, fmt, *args):
            logging.info("HTTP %s", args[1] if len(args) > 1 else "request")

        def send(self, body, status=200, content_type="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body, default=str).encode()
            # Prepare under the DB lock, but never hold it while writing a socket.
            self.pending_response=(body,status,content_type)

        def write_response(self):
            body,status,content_type=self.pending_response
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header('X-Trace-ID',self.request_record['trace_id'])
            self.send_header("Cache-Control", "no-store")
            if status==503:self.send_header('Retry-After','3')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def safe_host(self):
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}", f"{bind}:{self.server.server_port}"}
            if public_origin:
                allowed.add(urllib.parse.urlsplit(public_origin).netloc)
            if host not in allowed:
                raise PermissionError("Unrecognized host")

        def dispatch(self):
            nonlocal engine
            store=getattr(self,'request_store',root_store)
            self.safe_host()
            parsed = urllib.parse.urlsplit(self.path)
            query = {k: values[0] for k, values in urllib.parse.parse_qs(parsed.query).items()}
            if self.command == "GET":
                if parsed.path == '/healthz':
                    return self.send({'status':'alive'})
                if parsed.path == '/api/diagnostics':
                    return self.send(get_telemetry().diagnostics())
                if parsed.path in ("/", "/app.js", "/style.css"):
                    name, kind = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}[parsed.path]
                    return self.send((STATIC / name).read_bytes(), content_type=kind)
                if parsed.path == "/api/config":
                    import os
                    return self.send({"csrf": token, "frigate": bool(os.environ.get("PHOTO_FRIGATE_URL")), "background_only": getattr(store,"background_only",False), "auto_accept": hasattr(store,'auto_accept_pass'), "search_index": hasattr(store,'search')})
                if parsed.path == "/api/auto-accept":
                    return self.send(store.auto_accept_settings())
                if parsed.path == "/api/status":
                    return self.send(store.status() if hasattr(store,"status") else {"backend":"local"})
                if parsed.path == "/api/faces":
                    return self.send(store.face_library(query.get("person",""),query.get("status","unreviewed"),int(query.get("offset",0)),
                        grouped=query.get("grouped","true")=="true",group=query.get("group",""),scope=query.get("scope","repeated")))
                if parsed.path == "/api/faces/group-selection":
                    return self.send(store.group_selection(query.get("group",""),query.get("generation","")))
                if parsed.path == "/api/faces/selection":
                    return self.send(store.suggested_selection(float(query.get("threshold",".9")),query.get("person","")))
                if parsed.path == "/api/dates":
                    return self.send(store.dates(query.get("timezone", "UTC")))
                if parsed.path == "/api/photos":
                    return self.send(store.photos(query["date"], query.get("timezone", "UTC"), int(query.get("offset", 0))))
                if parsed.path == '/api/search':
                    return self.send(store.search(query.get('q',''),query.get('timezone','UTC'),int(query.get('offset',0))))
                if parsed.path == "/api/photo":
                    return self.send(store.detail(query["path"]))
                if parsed.path == "/api/thumbnail":
                    return self.send(store.thumbnail(query["path"], query.get("face")), content_type="image/jpeg")
                if parsed.path == "/api/groups":
                    return self.send(store.groups())
                if parsed.path == "/api/group":
                    return self.send(store.group(query["id"]))
                if parsed.path == "/api/suggestions":
                    return self.send(store.suggestions(query["face"], float(query.get("threshold", 0.363))))
                return self.send({"error": "Not found"}, 404)
            if not hmac.compare_digest(self.headers.get("X-Photo-Token", ""), token):
                raise PermissionError("Invalid request token; reload the page")
            origin = self.headers.get("Origin")
            allowed_origins = {f"http://{self.headers.get('Host')}"}
            if public_origin:
                allowed_origins.add(public_origin.rstrip("/"))
            if origin and origin not in allowed_origins:
                raise PermissionError("Cross-origin writes are disabled")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 512_000:
                raise ValueError("Request too large or empty")
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Expected JSON")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("Expected JSON object")
            if parsed.path == '/api/group-suggestions':
                return self.send(store.group_suggestions(body.get('paths'),body.get('timezone','UTC')))
            if parsed.path == "/api/groups/save":
                return self.send(store.save_group(body))
            if parsed.path == "/api/groups/delete":
                store.delete_group(body["id"])
                return self.send({"deleted": True})
            if parsed.path == "/api/extract":
                if getattr(store,"background_only",False):
                    raise ValueError("Extraction runs in the background worker")
                paths = body.get("paths", [])
                if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
                    raise ValueError("Expected photo paths")
                # One CPU extraction at a time; the read-only catalog remains unchanged.
                with store.lock:
                    if body.get("faces") and engine is None:
                        engine = FaceEngine(models)
                    return self.send(store.extract(paths, body.get("timezone", "UTC"), engine if body.get("faces") else None))
            if parsed.path == "/api/faces/label":
                store.label_face(body["id"], body.get("person", ""), body.get("revision"))
                return self.send({"saved": True})
            if parsed.path == "/api/faces/labels":
                store.label_faces(body.get("faces",[]),body.get("person"))
                return self.send({"saved": True})
            if parsed.path == "/api/auto-accept":
                return self.send(store.configure_auto_accept(body.get('enabled'),body.get('threshold')))
            if parsed.path == "/api/faces/reject":
                store.reject(body["id"], body["reference_id"])
                return self.send({"rejected": True})
            if parsed.path == "/api/faces/frigate":
                with store.lock, store.metrics.measure("frigate"):
                    face = store.face(body["id"])
                    return self.send(frigate_candidate(store.thumbnail(face["path"], face["id"])))
            if parsed.path == "/api/export":
                return self.send(store.export())
            self.send({"error": "Not found"}, 404)

        def dispatch_safely(self):
            try:
                route=urllib.parse.urlsplit(self.path).path
                if route.startswith('/api/') and route not in ('/api/config','/api/diagnostics') and hasattr(store,'request_session'):
                    with store.request_session(readonly=self.command=='GET' or route=='/api/group-suggestions') as reader:
                        self.request_store=reader
                        self.dispatch()
                elif self.command=='GET' and (route in ('/','/app.js','/style.css','/healthz','/api/config','/api/diagnostics')
                    or getattr(store,'background_only',False)):
                    # PostgreSQL reads take short per-query locks internally;
                    # independent DuckDB queries and image I/O need no GUI lock.
                    self.dispatch()
                else:
                    with get_telemetry().stage('lock.wait'):
                        if not store.lock.acquire(timeout=getattr(self.server,'lock_timeout',3)):
                            raise TimeoutError('Photo database is busy; retry shortly')
                    try:self.dispatch()
                    finally:store.lock.release()
            except TimeoutError as exc:
                self.send({'error':str(exc)},503)
            except PermissionError as exc:
                self.send({"error": str(exc)}, 403)
            except (ValueError, KeyError, OSError) as exc:
                logging.warning("Photo request failed: %s", type(exc).__name__)
                self.send({"error": str(exc)[:250]}, 400)
            except Exception as exc:
                get_telemetry().emit('request.error',error_type=type(exc).__name__,trace_id=self.request_record['trace_id'])
                if type(exc).__name__ in ('PoolTimeout','TooManyRequests'):
                    self.send({'error':'Photo database connection pool is busy; retry shortly'},503)
                elif type(exc).__name__ in ('QueryCanceled','LockNotAvailable'):
                    self.send({'error':'Photo query timed out; retry shortly'},503)
                else:self.send({"error": "Operation failed; check the server log"}, 500)
            self.request_record['status']=self.pending_response[1]
            try:
                with get_telemetry().stage('response.write'):self.write_response()
            except (BrokenPipeError,ConnectionResetError,TimeoutError):
                logging.info('Photo client disconnected before response completed')

        def handle_request(self):
            with get_telemetry().request(self.command,urllib.parse.urlsplit(self.path).path,self.headers) as record:
                self.request_record=record
                self.dispatch_safely()

        do_GET = handle_request
        do_POST = handle_request

    return ThreadingHTTPServer((bind, port), Handler)
