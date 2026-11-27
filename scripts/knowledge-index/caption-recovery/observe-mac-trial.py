"""Measure the original Mac server while additive-mac-trial.py runs beside it."""
import argparse
import json
from pathlib import Path
import sqlite3
import time
import urllib.request

from process import PRIVATE


def busy_slots(port: int, key: str) -> list | None:
    """Return anonymous slot/task pairs only. An unavailable server is a missing sample."""
    request = urllib.request.Request(f'http://127.0.0.1:{port}/slots', headers={'Authorization': 'Bearer ' + key})
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            return [[s['id'], s['id_task']] for s in json.load(response) if s['is_processing']]
    except (ValueError, OSError):
        return None


def observe(folder: Path, ledger: Path, seconds: int) -> None:
    key = (PRIVATE / 'knowledge-index-bonsai/server.key').read_text().strip()
    with sqlite3.connect(ledger.resolve().as_uri() + '?mode=ro', uri=True) as db, (folder/'samples.jsonl').open('x') as output:
        for _ in range(seconds):
            start = time.monotonic()
            state = dict(db.execute('SELECT state,count(*) FROM work GROUP BY state'))
            sample = dict(t=time.time(), base=busy_slots(19476, key), extra=busy_slots(19582, key), state=state)
            print(json.dumps(sample), file=output, flush=True)
            time.sleep(max(0, 1 + start - time.monotonic()))


def window(samples: list[dict], start: float, end: float) -> dict:
    rows = [s for s in samples if start <= s['t'] < end]
    if len(rows) < 2:
        raise ValueError('Too few observations for this interval')
    turnovers = missing = occupancy = 0
    peak_extra = max(len(s.get('extra') or []) for s in rows)
    previous = None
    for sample in rows:
        if sample['base'] is None:
            missing += 1
            previous = None
            continue
        active = set(map(tuple, sample['base']))
        if previous is not None:
            turnovers += len(previous - active)
        occupancy += len(active)
        previous = active
    elapsed = rows[-1]['t'] - rows[0]['t']
    return dict(seconds=round(elapsed, 1), samples=len(rows), missing=missing, peak_extra_busy=peak_extra,
                baseline_turnovers=turnovers, baseline_per_min=round(turnovers * 60 / elapsed, 2),
                mean_busy_slots=round(occupancy / max(1, len(rows) - missing), 2),
                verified_delta=rows[-1]['state'].get('verified', 0) - rows[0]['state'].get('verified', 0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('observe', 'report'))
    parser.add_argument('folder', type=Path)
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--seconds', type=int, default=1800)
    parser.add_argument('--baseline-seconds', type=int, default=90)
    parser.add_argument('--repeat-baseline-after', type=int, metavar='EXTRA_SLOTS',
                        help='Report another baseline window after this trial server stops')
    args = parser.parse_args()
    if args.mode == 'observe':
        if not args.ledger or args.seconds < 2:
            parser.error('Supply a read-only ledger and at least two seconds')
        observe(args.folder, args.ledger, args.seconds)
        return
    samples = [json.loads(line) for line in (args.folder/'samples.jsonl').read_text().splitlines()]
    begin = samples[0]['t']
    print('Baseline', json.dumps(window(samples, begin, begin + args.baseline_seconds)))
    for path in sorted(args.folder.glob('extra-*-result.json')):
        trial = json.loads(path.read_text())
        if args.repeat_baseline_after == trial['slots']:
            control = next(s['t'] for s in samples if s['t'] > trial['end'] and s['extra'] is None)
            end = control + args.baseline_seconds
            if samples[-1]['t'] < end or any(s['extra'] is not None for s in samples if control <= s['t'] < end):
                parser.error('Requested repeat baseline interval is incomplete or overlaps an extra server')
            print('Repeat baseline', json.dumps(window(samples, control, end)))
        print(f"Extra {trial['slots']}", json.dumps(window(samples, trial['start'], trial['end'])), json.dumps(trial))


if __name__ == '__main__':
    main()
