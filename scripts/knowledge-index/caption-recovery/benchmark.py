"""Replay verified photo previews privately without updating Immich or the recovery ledger."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

import process


SAMPLE_SQL = """
WITH photos AS (
    SELECT id, size, answer, ntile(6) OVER (ORDER BY size, id) AS bucket
    FROM cohort JOIN work USING (id)
    WHERE media_type = 'IMAGE' AND state = 'verified' AND answer IS NOT NULL
), ranked AS (
    SELECT *, row_number() OVER (PARTITION BY bucket ORDER BY id) AS position
    FROM photos
)
SELECT id, answer FROM ranked WHERE position = 1 ORDER BY bucket
"""

PREVIEWS = """
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const sharp = createRequire('/usr/src/app/server/package.json')('sharp');
const key = (await fs.readFile('/credentials/api-key', 'utf8')).trim();
const api = process.env.IMMICH_URL || 'http://immich-server:2283/api';
for (const id of ids) {
    const response = await fetch(api + '/assets/' + id + '/thumbnail?size=preview', {
        headers: {'x-api-key': key}
    });
    if (!response.ok) throw Error('Preview HTTP ' + response.status);
    const image = await sharp(Buffer.from(await response.arrayBuffer())).rotate()
        .resize({width: 768, height: 768, fit: 'inside', withoutEnlargement: true})
        .jpeg({quality: 88}).toBuffer();
    console.log(image.toString('base64'));
}
"""


def prepare(ledger: Path, folder: Path) -> None:
    """Get one previously verified photo per size bucket, retaining captions for review."""
    with sqlite3.connect(ledger.resolve().as_uri() + '?mode=ro', uri=True) as db:
        rows = db.execute(SAMPLE_SQL).fetchall()
    if len(rows) != 6:
        raise ValueError('Six verified photos are required')
    ids = [row[0] for row in rows]
    frames = process.kubectl_output(
        process.KUBE + ['deploy/immich-sync', '--', 'node', '--input-type=module', '-'],
        'const ids = ' + json.dumps(ids) + ';' + PREVIEWS, 120,
    ).splitlines()
    if len(frames) != len(rows):
        raise ValueError('Incomplete preview set')
    for index, (frame, row) in enumerate(zip(frames, rows)):
        (folder / f'{index}.jpg').write_bytes(base64.b64decode(frame, validate=True))
        (folder / f'{index}.reference').write_text(json.loads(row[1])['summary'])


def cpu(frame: str, host: str) -> dict:
    """Use the same scene prompt on the temporary VM's loopback-only CPU server."""
    context = dict(album=None, taken_ts=None, people=[], has_geo=False)
    prompt = process.build_prompt(context, False, 1, '')
    content = [
        {'type': 'text', 'text': prompt},
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + frame}},
    ]
    body = dict(model='bonsai-27b-cpu', temperature=0.2, max_tokens=256,
                chat_template_kwargs={'enable_thinking': False}, response_format={'type': 'json_object'},
                messages=[{'role': 'user', 'content': content}])
    command = ("qm guest exec 108 --timeout 600 --pass-stdin 1 -- curl -fsS --max-time 560 "
               "-H 'Content-Type: application/json' --data-binary @- "
               "http://127.0.0.1:19479/v1/chat/completions")
    reply = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', '--', host, command],
                                    input=json.dumps(body), text=True, timeout=620)
    report = json.loads(reply)
    if not report.get('exited') or report.get('exitcode') or report.get('out-truncated'):
        raise RuntimeError('CPU guest request failed: ' + report.get('err-data', '')[:150])
    result = json.loads(report['out-data'])
    summary, tags = process.parse_answer(result['choices'][0]['message']['content'])
    if len(summary.split()) < 4:
        raise ValueError('CPU response has no usable scene description')
    return dict(summary=summary, tags=tags, timings=result.get('timings', {}))


def main() -> None:
    """Record trial results locally, counting only successful captions in the measured rate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'mac', 'rtx', 'cpu'))
    parser.add_argument('folder', type=Path)
    parser.add_argument('--ledger', type=Path, help='Private recovery SQLite database')
    parser.add_argument('--host', help='Inventory SSH destination for the Proxmox host of VM 108')
    parser.add_argument('--rtx', help='Existing RTX Ollama endpoint')
    parser.add_argument('--slots', type=int, choices=range(1, 9), default=1)
    parser.add_argument('--count', type=int, choices=range(1, 7), default=6)
    args = parser.parse_args()
    required = {'cpu': 'host', 'rtx': 'rtx', 'prepare': 'ledger'}.get(args.action)
    if required and not getattr(args, required):
        parser.error(f'{args.action} requires --{required}')
    os.umask(0o077)
    args.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.folder.stat().st_mode & 0o077:
        parser.error('Use a private folder (mode 0700) for the actual photos and captions')
    if args.action == 'prepare':
        prepare(args.ledger, args.folder)
        return
    key = None
    if args.action == 'mac':
        key = (process.PRIVATE / 'knowledge-index-bonsai/server.key').read_text().strip()

    def run_sample(index: int) -> bool:
        start = time.monotonic()
        frame = base64.b64encode((args.folder / f'{index}.jpg').read_bytes()).decode()
        try:
            if args.action == 'cpu':
                result = cpu(frame, args.host)
            else:
                row = dict(frames=[frame], duration=None, mtime=None)
                backend = process.LOCAL if args.action == 'mac' else args.rtx
                result = process.infer(row, backend, key)
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
            result = {'error': type(error).__name__}
        result['seconds'] = round(time.monotonic() - start, 2)
        (args.folder / f'{args.action}-{args.slots}-{index}.json').write_text(json.dumps(result))
        return 'summary' in result

    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.slots) as pool:
        accepted = sum(pool.map(run_sample, range(args.count)))
    elapsed = time.monotonic() - start
    print(json.dumps(dict(backend=args.action, slots=args.slots, attempted=args.count, accepted=accepted,
                          seconds=round(elapsed, 2), per_minute=round(60 * accepted / elapsed, 2))))


if __name__ == '__main__':
    main()
