#!/usr/bin/env python3
"""Read-only, aggregate Prometheus exporter for the pinned pet-tagger API.

No Immich credential, photo content, asset IDs or person IDs are exported.
Only GET requests are made. This runs separately so it cannot restart a scan.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import math
import os
import sys
import threading
import time
from typing import Callable
import urllib.request

PREFIX = 'immich_pet_tagger_'
STATES = {'none': 0, 'running': 1, 'idle': 2, 'stopped': 3, 'error': 4}
COUNTS = ('fetched', 'added', 'unknown', 'out_of_range', 'already_tagged', 'failed', 'no_thumb')
PATHS = ('/api/scan/result', '/api/poll-status', '/api/pets', '/api/negatives')


def number(value: object) -> float:
    """Reject malformed measurements rather than reporting them as zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Non-numeric measurement')
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError('Invalid measurement')
    return result


def timestamp(value: str) -> float:
    """Convert upstream UTC timestamps or photo dates to Unix seconds."""
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def sample(name: str, value: float, **labels: str) -> str:
    """Render only fixed metric names and controlled labels."""
    suffix = '{' + ','.join(f'{k}={json.dumps(v)}' for k, v in labels.items()) + '}' if labels else ''
    return f'{PREFIX}{name}{suffix} {value:.17g}'


def measurements(manual: dict, poll: dict, pets: dict, negatives: dict) -> list[str]:
    """Normalize upstream snapshots; mixed crop/asset outcomes remain separate."""
    lines = []
    for scope, result in [('manual', manual), ('latest_cycle', poll)]:
        status = result.get('status', 'none')
        lines.append(sample('scan_state', STATES.get(status, 5), scope=scope))
        for key in ('started_at', 'ran_at'):
            if result.get(key):
                lines.append(sample('scan_' + key + '_timestamp_seconds', timestamp(result[key]), scope=scope))
        if result.get('current_date'):
            lines.append(sample('photo_date_timestamp_seconds', timestamp(result['current_date']), scope=scope))
        # Missing fields during warmup or errors must not look like zero outcomes.
        counts = result.get('counts', {})
        for outcome in COUNTS:
            if outcome in counts:
                lines.append(sample('scan_items', number(counts[outcome]), scope=scope, outcome=outcome))
        # v1.10.0 /scan/result replaces live low_confidence with an empty review
        # list until completion. It is neither a live crop count nor a zero backlog.
        if scope == 'manual' and status == 'idle' and 'low_confidence' in counts:
            lines.append(sample('review_assets', number(counts['low_confidence'])))
    waffles = [pet for pet in pets['pets'] if pet['name'] == 'Waffles']
    if len(waffles) == 1:
        lines.append(sample('references', number(waffles[0]['ref_count'])))
    lines.append(sample('negatives', number(negatives['count'])))
    return lines


HELP = {
    'source_up': 'Whether all read-only API reads and schema validation succeeded.',
    'last_success_timestamp_seconds': 'Last successful API collection time.',
    'collection_timestamp_seconds': 'Most recent collection attempt time.',
    'scan_state': '0 no manual result, 1 running, 2 idle/completed, 3 stopped, 4 error, 5 unknown.',
    'scan_started_at_timestamp_seconds': 'Upstream scan start time when available.',
    'scan_ran_at_timestamp_seconds': 'Upstream final scan report time when available.',
    'photo_date_timestamp_seconds': 'Photo date currently visited; not a completion watermark.',
    'scan_items': 'Per-scan outcome gauges mixing crops and assets; never sum as processed photos.',
    'review_assets': 'Filtered review assets after a completed manual scan only.',
    'references': 'Enrolled Waffles reference count.',
    'negatives': 'Enrolled negative example count.',
}


class Collector:
    """Atomically publish a snapshot and remove measurements on collection failure."""

    def __init__(self, read: Callable[[str], dict], clock: Callable[[], float] = time.time) -> None:
        self.read = read
        self.clock = clock
        self.last_success = 0.0
        self.output = ''

    def collect(self) -> None:
        """Fetch small status endpoints, discarding private fields immediately."""
        now = self.clock()
        try:
            lines = measurements(*(self.read(path) for path in PATHS))
            self.last_success = now
            up = 1
        except Exception:
            # Exception text can include remote content: never log it.
            logging.warning('Pet-tagger status collection failed')
            lines, up = [], 0
        lines += [sample('source_up', up),
                  sample('last_success_timestamp_seconds', self.last_success),
                  sample('collection_timestamp_seconds', now)]
        headers = [f'# HELP {PREFIX}{name} {help_text}\n# TYPE {PREFIX}{name} gauge'
                   for name, help_text in HELP.items()]
        self.output = '\n'.join(headers + lines) + '\n'


def main() -> None:
    """Serve cached metrics while an independent thread collects every 15 seconds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='Read once and emit metrics for validation')
    args = parser.parse_args()
    base = os.environ.get('PET_TAGGER_URL', 'http://immich-pet-tagger.immich-pilot.svc.cluster.local:8000')

    def read(path: str) -> dict:
        with urllib.request.urlopen(base + path, timeout=5) as response:
            return json.load(response)

    collector = Collector(read)
    if args.once:
        collector.collect()
        sys.stdout.write(collector.output)
        return

    def loop() -> None:
        while True:
            collector.collect()
            time.sleep(15)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            """Expose process health independently of upstream reachability."""
            if self.path not in ('/metrics', '/healthz'):
                self.send_error(404)
                return
            body = collector.output if self.path == '/metrics' else 'ok\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, format: str, *args: object) -> None:
            """Keep routine scrape logs quiet."""

    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', 9198), Handler).serve_forever()


if __name__ == '__main__':
    main()
