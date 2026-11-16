#!/usr/bin/env python3
"""Google Photos adapter for the knowledge index (issue #212).

Usage:
  gphotos.py emit <unit> <root> <out_dir> [--paths-from FILE] [--versions DIR]

  root       library root, read-only: the folder that holds "Google Photos/" (<dataset>/library)
  out_dir    the knowledge-index dataset; this adapter writes only below it:
               files/gphotos/<unit>.parquet             one row per file (common `files` schema)
               gphotos_sidecars/<unit>.parquet          one row per Takeout .json sidecar
               files/gphotos/<unit>.versions.parquet    only with --versions (rows under ".versions/")
  --paths-from FILE   index only these library-relative paths (one per line) instead of walking root
                      (the ingest hook passes the files an archive just delivered)
  --versions DIR      also index DIR (<dataset>/.versions); paths are stored as ".versions/<rel>"

Adapter contract (docs/runbooks/knowledge-index.md): emit(unit, root, out_dir) is idempotent (parquet is
written to <name>.tmp and renamed, so re-running a unit replaces its file), reads only from root, writes
only below out_dir, and prints one summary line: "rows=N bytes=B seconds=S".

Sidecar matching is NOT done here: a photo and its sidecar can come from different archives. This adapter
records, per sidecar, `target_name` (the media file name it describes, with the "(n)" duplicate suffix
re-inserted before the extension, as gphotos-quota-list.py does) and knowledge.sql joins across the library.
"""
import datetime
import json
import os
import re
import sys
import time

MEDIA_EXTS = {"jpg", "jpeg", "heic", "png", "gif", "webp", "mp4", "mov", "3gp", "avi", "mpg", "m4v"}
DUP = re.compile(r"\((\d+)\)\.json$")

FILES_SCHEMA = (
    "source VARCHAR, unit VARCHAR, path VARCHAR, name VARCHAR, ext VARCHAR, size_bytes BIGINT, "
    "mtime TIMESTAMP, kind VARCHAR, hash_algo VARCHAR, hash VARCHAR, origin_id VARCHAR, ingested_at TIMESTAMP"
)
SIDECAR_SCHEMA = (
    "path VARCHAR, title VARCHAR, target_name VARCHAR, description VARCHAR, upload_ts BIGINT, taken_ts BIGINT, "
    "geo_lat DOUBLE, geo_lon DOUBLE, geo_alt DOUBLE, url VARCHAR, device_type VARCHAR, device_folder VARCHAR, "
    "app_package VARCHAR, views INTEGER, favorited BOOLEAN, people VARCHAR[], parse_error VARCHAR"
)


def sidecar_target(jname, title):
    """Media file name a sidecar describes (same rule as gphotos-quota-list.py)."""
    m = DUP.search(jname)
    if m and title:
        stem, ext = os.path.splitext(title)
        return "%s(%s)%s" % (stem, m.group(1), ext)
    return title


def file_kind(name):
    ext = os.path.splitext(name)[1][1:].lower()
    if ext == "json":
        return "sidecar"
    return "media" if ext in MEDIA_EXTS else "other"


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_sidecar(abs_path, rel_path):
    """One gphotos_sidecars row (tuple in SIDECAR_SCHEMA order); unparseable -> NULLs + parse_error."""
    jname = os.path.basename(rel_path)
    try:
        with open(abs_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        if not isinstance(meta, dict):
            raise ValueError("top level is not an object")
    except (OSError, ValueError) as exc:
        return (rel_path,) + (None,) * 15 + ("%s: %s" % (type(exc).__name__, exc),)
    title = meta.get("title")
    geo = meta.get("geoData") or {}
    origin = (meta.get("googlePhotosOrigin") or {}).get("mobileUpload") or {}
    people = [p.get("name") for p in (meta.get("people") or []) if isinstance(p, dict) and p.get("name")]
    fav = meta.get("favorited")
    return (
        rel_path, title, sidecar_target(jname, title), meta.get("description"),
        _int((meta.get("creationTime") or {}).get("timestamp")),
        _int((meta.get("photoTakenTime") or {}).get("timestamp")),
        _float(geo.get("latitude")), _float(geo.get("longitude")), _float(geo.get("altitude")),
        meta.get("url"), origin.get("deviceType"), (origin.get("deviceFolder") or {}).get("localFolderName"),
        (meta.get("appSource") or {}).get("androidPackageName"),
        _int(meta.get("imageViews")), fav if isinstance(fav, bool) else None, people, None,
    )


def _walk(base):
    for d, _, files in os.walk(base):
        for f in files:
            yield os.path.relpath(os.path.join(d, f), base)


def _file_row(source, unit, rel, abs_path, now):
    st = os.stat(abs_path)
    name = os.path.basename(rel)
    return (source, unit, rel, name, os.path.splitext(name)[1][1:].lower(), st.st_size,
            datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc).replace(tzinfo=None),
            file_kind(name), None, None, None, now)


def _write_parquet(con, schema, rows, target):
    """Write rows to <target>.tmp as Parquet, then atomically rename (idempotent re-runs)."""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".tmp"
    con.execute("DROP TABLE IF EXISTS t")
    con.execute("CREATE TEMP TABLE t (%s)" % schema)
    if rows:
        ph = ",".join("?" * (schema.count(",") + 1))
        con.executemany("INSERT INTO t VALUES (%s)" % ph, rows)
    con.execute("COPY t TO '%s' (FORMAT parquet, COMPRESSION zstd)" % tmp.replace("'", "''"))
    os.replace(tmp, target)


def emit(unit, root, out_dir, paths=None, versions=None):
    """Index `root` (or only `paths`, library-relative) as `unit`. Returns (rows, bytes)."""
    import duckdb
    t0 = time.time()
    root = root.rstrip("/")
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    rels = sorted(set(paths)) if paths is not None else sorted(_walk(root))
    files, sidecars = [], []
    for rel in rels:
        ap = os.path.join(root, rel)
        if not os.path.isfile(ap):
            continue  # listed but gone (replaced later): skip, never fail the unit
        files.append(_file_row("gphotos", unit, rel, ap, now))
        if rel.endswith(".json"):
            sidecars.append(parse_sidecar(ap, rel))
    con = duckdb.connect()
    _write_parquet(con, FILES_SCHEMA, files, os.path.join(out_dir, "files", "gphotos", unit + ".parquet"))
    _write_parquet(con, SIDECAR_SCHEMA, sidecars, os.path.join(out_dir, "gphotos_sidecars", unit + ".parquet"))
    nrows, nbytes = len(files), sum(r[5] for r in files)
    if versions:
        vers = [_file_row("gphotos", unit, ".versions/" + rel, os.path.join(versions, rel), now)
                for rel in sorted(_walk(versions.rstrip("/")))]
        _write_parquet(con, FILES_SCHEMA, vers, os.path.join(out_dir, "files", "gphotos", unit + ".versions.parquet"))
        nrows += len(vers)
        nbytes += sum(r[5] for r in vers)
    print("rows=%d bytes=%d seconds=%.1f" % (nrows, nbytes, time.time() - t0))
    return nrows, nbytes


def main(argv):
    if len(argv) < 5 or argv[1] != "emit":
        sys.exit(__doc__)
    unit, root, out_dir = argv[2:5]
    opts = argv[5:]
    paths = versions = None
    if "--paths-from" in opts:
        with open(opts[opts.index("--paths-from") + 1], encoding="utf-8") as fh:
            paths = [ln.rstrip("\n") for ln in fh if ln.strip()]
    if "--versions" in opts:
        versions = opts[opts.index("--versions") + 1]
    emit(unit, root, out_dir, paths, versions)


if __name__ == "__main__":
    main(sys.argv)
