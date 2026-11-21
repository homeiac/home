#!/usr/bin/env python3
"""Reconcile searchable group tags from local and Luna caption evidence."""

import argparse
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

import duckdb

APP = "https://photos.app.home.panderosystems.com"
CATALOG = "/local-3TB-backup/knowledge-index/knowledge.duckdb"
LOCAL = "/local-3TB-backup/knowledge-index/summaries/gemma4-e2b-p1/*.parquet"
LUNA = "/local-3TB-backup/photo-enrichment/luna-backfill/luna_codex_captions/*.parquet"
GROUP_SIZE = 400


def api(path, body=None, csrf=None):
    headers = {"Content-Type": "application/json", "X-Photo-Token": csrf} if body is not None else {}
    req = urllib.request.Request(APP + path, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)


def candidates(terms):
    words = "(^|[^a-z0-9])(" + "|".join(re.escape(word) for word in terms) + ")([^a-z0-9]|$)"
    with duckdb.connect(CATALOG, read_only=True) as db:
        db.execute("SET threads=2")
        rows = db.execute("""WITH captions AS (
            SELECT path,size_bytes,summary,tags FROM read_parquet(?,union_by_name=true)
            WHERE status='ok' AND frames_sampled IS NULL
            UNION ALL
            SELECT source_path,size_bytes,summary,tags FROM read_parquet(?,union_by_name=true)
            WHERE state='ok' AND kind='photo'
        )
        SELECT DISTINCT c.path FROM captions c JOIN gphotos_media m USING(path,size_bytes)
        WHERE regexp_matches(lower(c.summary),?)
           OR list_has_any(list_transform(c.tags,t -> lower(t)),?)
        ORDER BY c.path""", [LOCAL, LUNA, words, terms]).fetchall()
    return [path for path, in rows]


def reconcile(tag, prefix, terms, apply):
    def detail(group_id):
        return api("/api/group?" + urllib.parse.urlencode({"id": group_id}))

    pattern = re.compile(re.escape(prefix) + r" ([1-9][0-9]*)")
    groups = []
    for group in api("/api/groups"):
        match = pattern.fullmatch(group.get("event") or "")
        if match and group.get("tags") == [tag]:
            groups.append((int(match[1]), detail(group["id"])))
    groups.sort(key=lambda item: item[0])
    seen = {path for _, group in groups for path in group["paths"]}
    pending = [path for path in candidates(terms) if path not in seen]
    print(f"Caption tags: {len(seen)} recorded photo paths, {len(pending)} new", flush=True)
    if not apply or not pending:
        return

    csrf = api("/api/config")["csrf"]

    def save(data):
        saved = api("/api/groups/save", data, csrf)
        stored = detail(saved["id"])
        if stored["tags"] != [tag] or set(stored["paths"]) != set(data["paths"]):
            raise RuntimeError("Group annotation readback did not match")

    index = 0
    if groups:
        index, last = groups[-1]
        capacity = max(0, GROUP_SIZE - len(last["paths"]))
        if capacity:
            update = {k: last[k] for k in ("id", "event", "location", "venue", "notes", "tags", "timezone")}
            update["paths"] = last["paths"] + pending[:capacity]
            save(update)
            pending = pending[capacity:]
    for i in range(0, len(pending), GROUP_SIZE):
        index += 1
        save(dict(event=f"{prefix} {index}", tags=[tag], paths=pending[i:i + GROUP_SIZE], timezone="America/Los_Angeles"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rule = json.loads(args.config.read_text())
    terms = rule["terms"]
    if not terms or any(not isinstance(term, str) or not re.fullmatch(r"[a-z0-9 ]+", term) for term in terms):
        parser.error("Supply at least one lowercase caption term")
    reconcile(rule["tag"], rule["group_prefix"], terms, args.apply)


if __name__ == "__main__":
    main()
