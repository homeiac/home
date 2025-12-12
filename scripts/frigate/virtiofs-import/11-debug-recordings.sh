#!/bin/bash
#
# 11-debug-recordings.sh
#
# Debug why old recordings aren't showing in Frigate UI
#

set -euo pipefail

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
NAMESPACE="frigate"

echo "========================================="
echo "Debug Frigate Recordings"
echo "========================================="
echo ""

POD=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n "$NAMESPACE" -l app=frigate -o jsonpath='{.items[0].metadata.name}')
echo "Pod: $POD"
echo ""

KUBECONFIG="$KUBECONFIG" kubectl exec -n "$NAMESPACE" "$POD" -- python3 << 'PYTHON'
import os
import sqlite3

conn = sqlite3.connect('/config/frigate.db')

print("=== Database Summary ===")
total = conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0]
print(f"Total recordings: {total}")

print()
print("=== Sample Old Recording (May 2025) ===")
row = conn.execute("""
    SELECT id, camera, path, start_time, end_time, duration, segment_size
    FROM recordings
    WHERE start_time < 1720000000
    ORDER BY start_time
    LIMIT 1
""").fetchone()
if row:
    print(f"ID: {row[0]}")
    print(f"Camera: {row[1]}")
    print(f"Path: {row[2]}")
    print(f"Start: {row[3]}")
    print(f"End: {row[4]}")
    print(f"Duration: {row[5]}")
    print(f"Size: {row[6]}")
    print()
    print(f"File exists: {os.path.exists(row[2])}")
    if os.path.exists(row[2]):
        print(f"File size: {os.path.getsize(row[2])} bytes")
else:
    print("No old recordings found in DB")

print()
print("=== Symlink Status ===")
rec_dir = '/media/frigate/recordings'
for date in ['2025-05-31', '2025-08-02', '2025-12-12']:
    path = os.path.join(rec_dir, date)
    if os.path.exists(path) or os.path.islink(path):
        is_link = os.path.islink(path)
        if is_link:
            target = os.readlink(path)
            target_exists = os.path.exists(path)
            print(f"{date}: SYMLINK -> {target} (target exists: {target_exists})")
        else:
            print(f"{date}: DIRECTORY")
    else:
        print(f"{date}: MISSING")

print()
print("=== Check Actual File ===")
test_path = '/media/frigate/recordings/2025-05-31/09/old_ip_camera/40.25.mp4'
print(f"Test path: {test_path}")
print(f"Exists: {os.path.exists(test_path)}")
print(f"Is link: {os.path.islink(test_path)}")

# Walk down the path
parts = test_path.split('/')
current = ''
for part in parts[1:]:
    current = current + '/' + part
    exists = os.path.exists(current)
    is_link = os.path.islink(current)
    status = 'OK' if exists else 'MISSING'
    if is_link:
        target = os.readlink(current)
        status = f'SYMLINK->{target} (exists:{os.path.exists(current)})'
    print(f"  {current}: {status}")

print()
print("=== Frigate API Test ===")
import urllib.request
import json
try:
    # Get recordings summary from API
    req = urllib.request.urlopen('http://localhost:5000/api/recordings/summary', timeout=5)
    data = json.loads(req.read())
    print(f"API recordings summary keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    if isinstance(data, dict):
        for cam, dates in list(data.items())[:2]:
            print(f"  {cam}: {len(dates)} date entries")
            if dates:
                print(f"    First dates: {list(dates.keys())[:3]}")
except Exception as e:
    print(f"API error: {e}")

print()
print("=== Check Recording Retention ===")
# Check if old recordings might be filtered by retention
row = conn.execute("SELECT MIN(start_time), MAX(start_time) FROM recordings").fetchone()
from datetime import datetime
if row[0]:
    min_dt = datetime.utcfromtimestamp(row[0])
    max_dt = datetime.utcfromtimestamp(row[1])
    print(f"DB date range: {min_dt} to {max_dt}")

conn.close()
PYTHON

echo ""
echo "========================================="
