#!/bin/bash
# Size of the quota-counted Google Photos per "Photos from <year>" folder (what deleting a year would free)
#
# Usage: ./gphotos-quota-by-year.sh [target]          default target ssk; needs CB_HOST (e.g. root@<host ip>)
# Reads the latest mirror log of <target> (every file the quota pass copied is logged as "<path>: Copied (new)"),
# stats those files in the primary library on the host and sums MEDIA files (not .json sidecars, which Google does not count)
# per year. Read-only. Superseded by a SQL query once the knowledge index exists (issue #212).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/cloud-backup-common.sh"
T="${1:-ssk}"
cb_ssh "python3 - $T" <<'PY'
import glob, os, re, subprocess, sys
t = sys.argv[1]
log = sorted(glob.glob(f"/var/lib/cloud-backup/reports/mirror-logs/mirror-{t}-*.log"))[-1]
lib = subprocess.check_output(["zfs", "get", "-H", "-o", "value", "mountpoint", "local-3TB-backup/gphotos"], text=True).strip() + "/library"
pat = re.compile(r"INFO  : gphotos/library/(Google Photos/Photos from (\d{4})/.+?): Copied \(new\)$")
years, files, missing = {}, {}, 0
for line in open(log, errors="replace"):
    m = pat.search(line.rstrip("\n"))
    if not m or m.group(1).endswith(".json"): continue
    try: sz = os.path.getsize(os.path.join(lib, m.group(1)))
    except OSError: missing += 1; continue
    years[m.group(2)] = years.get(m.group(2), 0) + sz; files[m.group(2)] = files.get(m.group(2), 0) + 1
tot = sum(years.values()); cum = 0
print(f"{'year':6} {'files':>7} {'GB':>8} {'cumulative GB (oldest first)':>30}")
for y in sorted(years):
    cum += years[y]; print(f"{y:6} {files[y]:7d} {years[y]/1e9:8.2f} {cum/1e9:30.2f}")
print(f"total counted media: {tot/1e9:.2f} GB in {sum(files.values())} files ({missing} unreadable)   [Google says 70.47 GB]")
PY
