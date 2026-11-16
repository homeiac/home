#!/usr/bin/env python3
"""Knowledge index maintenance (issue #212). Runs on the Proxmox host in /opt/knowledge-index/venv.

Usage:
  kidx.py rebuild <index_dir>             recreate <index_dir>/knowledge.duckdb (views only) from knowledge.sql
  kidx.py query   <index_dir> "<sql>"     run SQL read-only, print TSV (header first)
  kidx.py status  <index_dir>             parquet files / rows per table

<index_dir> is the knowledge-index dataset mount point (files/, gphotos_sidecars/, copies/ below it).
"""
import glob
import os
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
SQL = os.path.join(HERE, "knowledge.sql")
COPIES_SCHEMA = "source VARCHAR, path VARCHAR, location VARCHAR, size_bytes BIGINT, verified_at TIMESTAMP, verify_method VARCHAR"


def _split(sql):
    """Statements separated by ';' (whole-line comments stripped; knowledge.sql has no ';' inside strings)."""
    body = "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def rebuild(index):
    if not glob.glob(os.path.join(index, "files", "*", "*.parquet")) or \
       not glob.glob(os.path.join(index, "gphotos_sidecars", "*.parquet")):
        sys.exit("no parquet under %s/files or gphotos_sidecars: run an ingest or the backfill first" % index)
    if not glob.glob(os.path.join(index, "copies", "*.parquet")):   # Phase 2 fills copies; keep the view typed
        os.makedirs(os.path.join(index, "copies"), exist_ok=True)
        c = duckdb.connect()
        c.execute("CREATE TABLE c (%s)" % COPIES_SCHEMA)
        c.execute("COPY c TO '%s' (FORMAT parquet)" % os.path.join(index, "copies", "_empty.parquet"))
    target = os.path.join(index, "knowledge.duckdb")
    tmp = target + ".tmp"
    for p in (tmp, tmp + ".wal"):
        if os.path.exists(p):
            os.remove(p)
    con = duckdb.connect(tmp)
    sql = open(SQL, encoding="utf-8").read().replace("@INDEX@", index.rstrip("/").replace("'", "''"))
    for stmt in _split(sql):
        con.execute(stmt)
    con.close()
    os.replace(tmp, target)
    print("rebuilt %s" % target)


def _con(index):
    return duckdb.connect(os.path.join(index, "knowledge.duckdb"), read_only=True)


def query(index, sql):
    cur = _con(index).execute(sql)
    print("\t".join(d[0] for d in cur.description))
    for row in cur.fetchall():
        print("\t".join("" if v is None else str(v) for v in row))


def status(index):
    con = _con(index)
    for name in ("files", "gphotos_sidecars", "copies", "gphotos_files", "gphotos_versions", "gphotos_media",
                 "gphotos_album_dup", "gphotos_quota"):
        print("%-18s %d" % (name, con.execute("SELECT count(*) FROM %s" % name).fetchone()[0]))
    for d in ("files/*", "gphotos_sidecars", "copies"):
        print("parquet %-18s %d" % (d, len(glob.glob(os.path.join(index, d, "*.parquet")))))


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "rebuild":
        rebuild(a[1])
    elif len(a) == 3 and a[0] == "query":
        query(a[1], a[2])
    elif len(a) == 2 and a[0] == "status":
        status(a[1])
    else:
        sys.exit(__doc__)
