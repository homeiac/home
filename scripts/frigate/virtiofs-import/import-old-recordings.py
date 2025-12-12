#!/usr/bin/env python3
"""
Import old Frigate recordings into the database.

This script scans /import/recordings/ for .mp4 files and creates
database entries in /config/frigate.db so they appear in the UI.

Path format expected: /import/recordings/YYYY-MM-DD/HH/camera_name/MM.SS.mp4
Example: /import/recordings/2025-12-09/17/reolink_doorbell/35.57.mp4
"""

import os
import re
import sqlite3
import string
import random
from datetime import datetime, timezone
from pathlib import Path

# Configuration
RECORDINGS_PATH = "/import/recordings"
DB_PATH = "/config/frigate.db"
DEFAULT_DURATION = 10.0  # Frigate default segment length in seconds


def generate_id(timestamp: float) -> str:
    """Generate a Frigate-style recording ID.

    Format: {unix_timestamp}.0-{6_random_chars}
    Example: 1765141851.0-odqxgy
    """
    chars = string.ascii_lowercase + string.digits
    random_suffix = ''.join(random.choices(chars, k=6))
    return f"{int(timestamp)}.0-{random_suffix}"


def parse_recording_path(path: str) -> dict:
    """Parse a recording path to extract metadata.

    Path format: /import/recordings/YYYY-MM-DD/HH/camera_name/MM.SS.mp4
    Returns dict with: camera, start_time, path
    """
    # Pattern: recordings/YYYY-MM-DD/HH/camera/MM.SS.mp4
    pattern = r'/recordings/(\d{4}-\d{2}-\d{2})/(\d{2})/([^/]+)/(\d{2})\.(\d{2})\.mp4$'
    match = re.search(pattern, path)

    if not match:
        return None

    date_str, hour, camera, minute, second = match.groups()

    # Parse date and time
    dt = datetime.strptime(f"{date_str} {hour}:{minute}:{second}", "%Y-%m-%d %H:%M:%S")
    # Assume UTC timezone for consistency
    dt = dt.replace(tzinfo=timezone.utc)
    start_time = dt.timestamp()

    return {
        'camera': camera,
        'start_time': start_time,
        'path': path,
    }


def scan_recordings(base_path: str) -> list:
    """Scan directory for all .mp4 recording files."""
    recordings = []

    for root, dirs, files in os.walk(base_path):
        for filename in files:
            if filename.endswith('.mp4'):
                full_path = os.path.join(root, filename)
                recordings.append(full_path)

    return recordings


def get_existing_paths(conn: sqlite3.Connection) -> set:
    """Get set of paths already in the database."""
    cursor = conn.execute("SELECT path FROM recordings")
    return {row[0] for row in cursor.fetchall()}


def insert_recording(conn: sqlite3.Connection, recording: dict) -> bool:
    """Insert a single recording into the database."""
    try:
        conn.execute("""
            INSERT INTO recordings (id, camera, path, start_time, end_time,
                                    duration, objects, motion, segment_size, dBFS, regions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            recording['id'],
            recording['camera'],
            recording['path'],
            recording['start_time'],
            recording['end_time'],
            recording['duration'],
            recording.get('objects', 0),
            recording.get('motion', 0),
            recording['segment_size'],
            recording.get('dBFS', 0),
            recording.get('regions', 0),
        ))
        return True
    except sqlite3.IntegrityError as e:
        # Duplicate ID or path - skip
        return False


def main():
    print(f"Frigate Old Recordings Import")
    print(f"==============================")
    print(f"Recordings path: {RECORDINGS_PATH}")
    print(f"Database path: {DB_PATH}")
    print()

    # Check paths exist
    if not os.path.exists(RECORDINGS_PATH):
        print(f"ERROR: Recordings path not found: {RECORDINGS_PATH}")
        return 1

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found: {DB_PATH}")
        return 1

    # Connect to database
    conn = sqlite3.connect(DB_PATH)

    # Get existing paths to avoid duplicates
    existing_paths = get_existing_paths(conn)
    print(f"Existing recordings in DB: {len(existing_paths)}")

    # Scan for recordings
    print(f"Scanning {RECORDINGS_PATH}...")
    all_files = scan_recordings(RECORDINGS_PATH)
    print(f"Found {len(all_files)} .mp4 files")

    # Process each file
    imported = 0
    skipped_exists = 0
    skipped_parse = 0

    for filepath in all_files:
        # Check if already in DB
        if filepath in existing_paths:
            skipped_exists += 1
            continue

        # Parse path
        parsed = parse_recording_path(filepath)
        if not parsed:
            skipped_parse += 1
            continue

        # Get file size
        try:
            file_size = os.path.getsize(filepath)
            segment_size_mb = file_size / (1024 * 1024)
        except OSError:
            segment_size_mb = 0.5  # Default estimate

        # Build recording entry
        start_time = parsed['start_time']
        recording = {
            'id': generate_id(start_time),
            'camera': parsed['camera'],
            'path': filepath,
            'start_time': start_time,
            'end_time': start_time + DEFAULT_DURATION,
            'duration': DEFAULT_DURATION,
            'segment_size': segment_size_mb,
            'objects': 0,
            'motion': 0,
            'dBFS': 0,
            'regions': 0,
        }

        # Insert
        if insert_recording(conn, recording):
            imported += 1
            if imported % 1000 == 0:
                print(f"  Imported {imported} recordings...")
                conn.commit()

    # Final commit
    conn.commit()
    conn.close()

    print()
    print(f"Import complete!")
    print(f"  Imported: {imported}")
    print(f"  Skipped (already exists): {skipped_exists}")
    print(f"  Skipped (parse error): {skipped_parse}")

    return 0


if __name__ == "__main__":
    exit(main())
