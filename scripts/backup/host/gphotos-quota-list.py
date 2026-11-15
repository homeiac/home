#!/usr/bin/env python3
"""List the Google Photos library files that count against Google storage quota.

Usage: gphotos-quota-list.py <cloud-backup root> [--cutoff YYYY-MM-DD] > files-from.txt

Reads <root>/gphotos/library/**, pairs every photo/video with its Takeout JSON sidecar, and prints
(relative to <root>, one per line, for `rclone --files-from`) the media files - and their sidecars -
that Google counts against quota: items UPLOADED on/after the cutoff (default 2021-06-01, when free
"High quality" storage ended). Upload time = sidecar "creationTime".

Rules:
  - media with no matching sidecar: included (unknown upload date; better too much than too little)
  - "<name>-edited.<ext>" shares the original's sidecar
  - Takeout copies each photo into "Photos from YYYY" AND every album folder: an album copy with the
    same file name and size as one in a "Photos from YYYY" folder is skipped (same bytes)
A summary (files and GB: total, selected, unmatched, album duplicates skipped) goes to stderr.
Sidecar names vary: <file>.json, <file>.supplemental-metadata.json (often truncated, e.g.
<file>.supplemental-me.json), and duplicates as <file>(1).json or <file>.supplemental-metadata(1).json.
"""
import datetime, json, os, re, sys

args = sys.argv[1:]
if not args or args[0].startswith("-"):
    sys.exit(__doc__)
root = args[0].rstrip("/")
cutoff = datetime.date(2021, 6, 1)
if "--cutoff" in args:
    cutoff = datetime.date.fromisoformat(args[args.index("--cutoff") + 1])
cut_ts = datetime.datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=datetime.timezone.utc).timestamp()
lib = os.path.join(root, "gphotos", "library")
if not os.path.isdir(lib):
    print("no library at %s - nothing to list" % lib, file=sys.stderr)
    sys.exit(0)

DUP = re.compile(r"\((\d+)\)\.json$")
YEAR_DIR = re.compile(r"^Photos from \d{4}$")

def sidecar_target(jname, title):
    """Media file name a sidecar describes."""
    m = DUP.search(jname)
    if m and title:
        stem, ext = os.path.splitext(title)
        return "%s(%s)%s" % (stem, m.group(1), ext)
    return title

entries = []          # (relpath, size, upload_ts or None, dirname, basename, sidecar relpath or None)
for d, _, files in os.walk(lib):
    media = [f for f in files if not f.endswith(".json")]
    upload, side = {}, {}
    for j in (f for f in files if f.endswith(".json")):
        try:
            meta = json.load(open(os.path.join(d, j), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        title = meta.get("title")
        ts = (meta.get("creationTime") or {}).get("timestamp")
        if not title or ts is None:
            continue
        name = sidecar_target(j, title)
        for cand in (name, "%s-edited%s" % os.path.splitext(name)):
            if cand in media and cand not in upload:
                upload[cand], side[cand] = float(ts), j
    for f in media:
        p = os.path.join(d, f)
        entries.append((os.path.relpath(p, root), os.path.getsize(p), upload.get(f), os.path.basename(d), f,
                        os.path.relpath(os.path.join(d, side[f]), root) if f in side else None))

in_year = {(f, s) for _, s, _, dn, f, _ in entries if YEAR_DIR.match(dn)}
gb = lambda b: b / 1e9
tot = sel = unm = dup = 0
n_tot = n_sel = n_unm = n_dup = 0
out = []
for rel, size, ts, dn, f, side in entries:
    tot += size; n_tot += 1
    if not YEAR_DIR.match(dn) and (f, size) in in_year:
        dup += size; n_dup += 1
        continue
    if ts is None:
        unm += size; n_unm += 1
    if ts is None or ts >= cut_ts:
        sel += size; n_sel += 1
        out.append(rel)
        if side:
            out.append(side)
for line in sorted(set(out)):
    print(line)
print("library: %d files %.1f GB | selected (uploaded >= %s or no sidecar): %d files %.1f GB "
      "| of which no sidecar: %d files %.1f GB | album duplicates skipped: %d files %.1f GB"
      % (n_tot, gb(tot), cutoff, n_sel, gb(sel), n_unm, gb(unm), n_dup, gb(dup)), file=sys.stderr)
