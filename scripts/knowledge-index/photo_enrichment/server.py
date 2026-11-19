"""Small same-origin photo review UI; bind to loopback unless explicitly configured."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import secrets
import urllib.parse

from .faces import FaceEngine, frigate_candidate

STATIC = Path(__file__).parent / "static"


def make_server(store, models: Path, bind: str, port: int, public_origin: str | None = None):
    """Serve previews and annotation commands without arbitrary filesystem or SQL access."""
    token = secrets.token_urlsafe(32)
    engine = None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logging.info("HTTP %s", args[1] if len(args) > 1 else "request")

        def send(self, body, status=200, content_type="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
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
            self.safe_host()
            parsed = urllib.parse.urlsplit(self.path)
            query = {k: values[0] for k, values in urllib.parse.parse_qs(parsed.query).items()}
            if self.command == "GET":
                if parsed.path in ("/", "/app.js", "/style.css"):
                    name, kind = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}[parsed.path]
                    return self.send((STATIC / name).read_bytes(), content_type=kind)
                if parsed.path == "/api/config":
                    import os
                    return self.send({"csrf": token, "frigate": bool(os.environ.get("PHOTO_FRIGATE_URL")), "background_only": getattr(store,"background_only",False), "auto_accept": hasattr(store,'auto_accept_pass')})
                if parsed.path == "/api/auto-accept":
                    return self.send(store.auto_accept_settings())
                if parsed.path == "/api/status":
                    return self.send(store.status() if hasattr(store,"status") else {"backend":"local"})
                if parsed.path == "/api/faces":
                    return self.send(store.face_library(query.get("person",""),query.get("status","unreviewed"),int(query.get("offset",0))))
                if parsed.path == "/api/faces/selection":
                    return self.send(store.suggested_selection(float(query.get("threshold",".9")),query.get("person","")))
                if parsed.path == "/api/dates":
                    return self.send(store.dates(query.get("timezone", "UTC")))
                if parsed.path == "/api/photos":
                    return self.send(store.photos(query["date"], query.get("timezone", "UTC"), int(query.get("offset", 0))))
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

        def handle_request(self):
            try:
                # The GUI and optional background rule share one connection.
                # Serialize requests so they cannot join another task's transaction.
                with store.lock:
                    self.dispatch()
            except PermissionError as exc:
                self.send({"error": str(exc)}, 403)
            except (ValueError, KeyError, OSError) as exc:
                logging.warning("Photo request failed: %s", type(exc).__name__)
                self.send({"error": str(exc)[:250]}, 400)
            except Exception:
                logging.exception("Photo request failed")
                self.send({"error": "Operation failed; check the server log"}, 500)

        do_GET = handle_request
        do_POST = handle_request

    return ThreadingHTTPServer((bind, port), Handler)
