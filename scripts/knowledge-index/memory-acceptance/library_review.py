"""Page the private library checkpoint and reuse the album's face/action/OCR renderer."""

import argparse
from contextlib import closing
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import parse_qs, urlencode, urlsplit

from library_backfill import HERE
from openlabel_album import ocr_regions, stable_id
from review_openlabel import atomic_page, render_review

PAGE_SIZE = 24


def photo_card(db, row):
    asset, path, day, tags, reviewed = row
    thumb = "https://photos.app.home.panderosystems.com/api/thumbnail?" + urlencode(
        {"path": path}
    )
    result = (
        json.loads(reviewed)
        if reviewed
        else dict(
            asset=asset,
            date=day or "Unknown",
            width=1,
            height=1,
            faces={},
            claims=[],
            individual=[],
            mentions=[],
            media_type="Photo",
            original="https://immich.app.home.panderosystems.com/photos/" + asset,
        )
    )
    result.update(
        image=thumb, ocr=ocr_regions({"tags": json.loads(tags)}), library=True
    )
    faces = db.execute(
        "SELECT asset,person,name,input,status,outcome FROM jobs WHERE photo=? ORDER BY asset",
        (asset,),
    )
    for fid, person, name, raw, state, value in faces:
        value = json.loads(value or "{}")
        uid = stable_id(asset, "immich", fid)
        # Reviewed cards can use a local ID for an independently verified alternate face.
        if reviewed:
            uid = next(
                (
                    k
                    for k, f in result["faces"].items()
                    if f.get("immich_face_id") == fid
                ),
                uid,
            )
        x, y, right, bottom = [max(0, min(1, v)) for v in json.loads(raw)["box"]]
        face = result["faces"].setdefault(
            uid,
            dict(
                face_namespace="immich",
                face_id=fid,
                box=[
                    (x + right) / 2 * result["width"],
                    (y + bottom) / 2 * result["height"],
                    (right - x) * result["width"],
                    (bottom - y) * result["height"],
                ],
            ),
        )
        face.update(
            name=name or "Unnamed person", unnamed=not bool(name), person_id=person
        )
        spans = [{"face": uid}]
        stage = value.get("stage")
        if stage:
            spans.append({"text": " · " + stage.replace("_", " ")})
        if value.get("verb"):
            verb = value["verb"]
            spans.extend(
                [
                    {"text": " · "},
                    {
                        "verb": verb,
                        "id": stable_id(fid, "bonsai", verb),
                        "code": value["code"],
                        "roles": {"actor": uid},
                    },
                    {"text": value["action"][len(verb) :]},
                ]
            )
        elif value.get("parts"):
            # Reuse stored subject placeholders so a later name edit changes the reading.
            words = [
                {"face": uid} if isinstance(p, dict) else {"text": p}
                for p in value["parts"]
                if p
            ]
            spans = (
                [*words, {"text": " · " + stage.replace("_", " ")}] if stage else words
            )
        elif not reviewed or not value.get("reviewed_action"):
            spans.append(
                {
                    "text": " · "
                    + (
                        {"pending": "Queued", "running": "Processing"}.get(state)
                        or value.get("reason", "Action unclear")
                    )
                }
            )
        if not reviewed or len(spans) > 1:
            result["individual"].append({"subject": uid, "spans": spans})
    return result


def page(db, query):
    q = query.get("q", [""])[0].strip()[:200]
    view = query.get("view", ["ocr"])[0]
    clauses = {
        "ocr": "p.region_count>0",
        "faces": "EXISTS (SELECT 1 FROM jobs j WHERE j.photo=p.id)",
        "results": "EXISTS (SELECT 1 FROM jobs j WHERE j.photo=p.id AND j.status='complete')",
        "all": "1",
    }
    if view not in clauses:
        view = "ocr"
    try:
        number = max(1, int(query.get("page", ["1"])[0]))
    except ValueError:
        number = 1
    where = clauses[view]
    values = []
    if q:
        where += " AND p.id IN (SELECT photo FROM words WHERE words MATCH ?)"
        values.append(
            " AND ".join('"' + word.replace('"', '""') + '"' for word in q.split())
        )
    count = db.execute(
        "SELECT count(*) FROM photos p WHERE " + where, values
    ).fetchone()[0]
    pages = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
    number = min(number, pages)
    rows = db.execute(
        """SELECT p.id,p.path,p.day,p.tags,r.card FROM photos p LEFT JOIN reviewed r ON r.photo=p.id WHERE """
        + where
        + " ORDER BY p.day DESC,p.id LIMIT ? OFFSET ?",
        [*values, PAGE_SIZE, (number - 1) * PAGE_SIZE],
    )
    cards = [photo_card(db, row) for row in rows]
    template = (
        (HERE / "openlabel_review.html")
        .read_text()
        .replace("SHARED_CARD_STYLES", (HERE / "album_card_links.css").read_text())
    )
    template = template.replace(
        "ALBUM_CARD_RENDERER", (HERE / "album_cards.js").read_text()
    )
    html = render_review(
        template,
        cards,
        "Photo library",
        f"{count:,} photos · Page {number:,} of {pages:,}",
    )
    labels = {
        "ocr": "With image text",
        "results": "New face results",
        "faces": "With faces",
        "all": "All photos",
    }
    options = "".join(
        f'<option value="{k}" {"selected" if k==view else ""}>{label}</option>'
        for k, label in labels.items()
    )
    controls = f'<form><label>Show <select name="view">{options}</select></label> <label>Image text or name <input name="q" value="{escape(q,quote=True)}"></label> <button>Search</button></form>'
    for label, n in (("Previous", number - 1), ("Next", number + 1)):
        if 1 <= n <= pages:
            controls += (
                ' <a href="?'
                + escape(urlencode(dict(view=view, q=q, page=n)), quote=True)
                + '">'
                + label
                + "</a>"
            )
    return html.replace(
        '<a id="catalogue-link"', controls + '<a id="catalogue-link"', 1
    )


def serve(root, port):
    address = f"127.0.0.1:{port}"
    # A local private file grants access to this user's catalogue; never put the key in a URL.
    keyfile = root / "reader.key"
    if not keyfile.exists():
        atomic_page(keyfile, secrets.token_urlsafe(32))
    key = keyfile.read_text()
    launcher = f"""<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>Open private photo library</title>
<form method="post" action="http://{address}/open"><input type="hidden" name="access" value="{escape(key)}"><button>Open private photo library</button></form>
<script>document.forms[0].submit()</script>"""
    atomic_page(root / "Photo library.html", launcher)

    class Reader(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.headers.get("Host") != address or self.path != "/open":
                return self.send_error(404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.send_error(400)
            if not 0 < length < 256:
                return self.send_error(400)
            given = parse_qs(
                self.rfile.read(length).decode("ascii", errors="replace")
            ).get("access", [""])[0]
            if not secrets.compare_digest(given.encode(), key.encode()):
                return self.send_error(403)
            self.send_response(303)
            self.send_header(
                "Set-Cookie", f"library={key}; HttpOnly; SameSite=Lax; Path=/"
            )
            self.send_header("Location", "/")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def do_GET(self):
            url = urlsplit(self.path)
            if self.headers.get("Host") != address or url.path != "/":
                return self.send_error(404)
            cookie = SimpleCookie(self.headers.get("Cookie", "")).get("library")
            if not cookie or not secrets.compare_digest(
                cookie.value.encode(), key.encode()
            ):
                return self.send_error(403)
            with closing(
                sqlite3.connect(
                    (root / "library.sqlite3").as_uri() + "?mode=ro", uri=True
                )
            ) as db:
                db.execute("BEGIN")
                content = page(db, parse_qs(url.query)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    ThreadingHTTPServer(("127.0.0.1", port), Reader).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path)
    ap.add_argument("--port", type=int, default=19482)
    args = ap.parse_args()
    os.umask(0o077)
    serve(args.root.resolve(), args.port)
