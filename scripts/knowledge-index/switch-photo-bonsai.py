#!/usr/bin/env python3
"""Switch the two Proxmox photo workers to the private Flux-managed Bonsai service."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request


ENDPOINT = 'https://photo-bonsai.app.home.panderosystems.com'
MODEL = 'bonsai-27b'
UNITS = ('knowledge-index-enrich.service', 'photo-enrichment-context.service')
BACKUP = Path('/opt/knowledge-index/backups/photo-bonsai-v1')
CONTEXT = Path('/opt/photo-enrichment/context')
CONTEXT_SOURCES = {
    'photo-enrich.py': 'eaaee8dbd2ddd6effb104c268e0121f0064aa6d462e9144c59ab4f54f90c0ac9',
    'photo_enrichment/context_worker.py': '1d75045363317006f882d53f1559ae4982fa541da87552357abd4dbc2d3ec93e',
}


def systemctl(*arguments, output=False):
    return subprocess.run(['systemctl', *arguments], check=True, text=True,
                          capture_output=output, timeout=55).stdout


def dropin(unit):
    return Path('/etc/systemd/system', unit + '.d', '95-photo-bonsai.conf')


def replace(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.bonsai-new')
    temporary.write_bytes(content)
    temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
    temporary.replace(path)


def command(unit):
    pid = systemctl('show', unit, '-p', 'MainPID', '--value', output=True).strip()
    if pid == '0':
        raise RuntimeError(f'{unit} is not running')
    return Path('/proc', pid, 'cmdline').read_bytes().decode().rstrip('\0').split('\0')


def set_option(argv, flag, value):
    if flag in argv:
        argv[argv.index(flag) + 1] = value
    else:
        argv.extend([flag, value])


def exec_start(argv):
    quoted = ' '.join(json.dumps(arg.replace('%', '%%').replace('$', '$$'), ensure_ascii=False) for arg in argv)
    return ('[Service]\nExecStart=\nExecStart=' + quoted + '\n').encode()


def restart_workers():
    systemctl('daemon-reload')
    systemctl('restart', *UNITS)
    time.sleep(5)
    for unit in UNITS:
        systemctl('is-active', '--quiet', unit)


def restore():
    inventory = json.loads((BACKUP / 'inventory.json').read_text())
    for name, original in inventory.items():
        path = Path(name)
        if original is None:
            path.unlink(missing_ok=True)
        else:
            replace(path, base64.b64decode(original))
    restart_workers()


def switch(files):
    with urllib.request.urlopen(ENDPOINT + '/health', timeout=12) as response:
        if json.load(response).get('status') != 'ok':
            raise RuntimeError('Bonsai readiness endpoint is not healthy')
    commands = [command(unit) for unit in UNITS]
    if all(args[args.index('--model') + 1] == MODEL for args in commands):
        print('Both photo workers already use Bonsai.')
        return
    updates = {}
    for relative, digest in CONTEXT_SOURCES.items():
        path = (CONTEXT / relative).resolve(strict=True)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Unexpected installed version of {relative}')
        compile(files[relative], str(path), 'exec')
        updates[path] = files[relative].encode()
    metrics = Path('/opt/knowledge-index/enrichers/pipeline_metrics.py')
    original = metrics.read_bytes()
    if original.count(b'"inference": "Ollama request"') != 1:
        raise RuntimeError('Unexpected installed summary metric label')
    updates[metrics] = original.replace(b'"inference": "Ollama request"', b'"inference": "Model request"')

    for unit, argv in zip(UNITS, commands):
        old_model = argv[argv.index('--model') + 1]
        set_option(argv, '--endpoint', ENDPOINT)
        set_option(argv, '--model', MODEL)
        set_option(argv, '--api', 'openai')
        if unit == UNITS[0]:
            # Keep the existing enricher key so previously saved summaries stay complete.
            set_option(argv, '--batch-size', '16')
            set_option(argv, '--extra-json', json.dumps({
                'chat_template_kwargs': {'enable_thinking': False}, 'max_tokens': 384}))
        else:
            set_option(argv, '--seed-model', old_model)
        updates[dropin(unit)] = exec_start(argv)

    BACKUP.mkdir(mode=0o700)
    originals = {str(path): base64.b64encode(path.read_bytes()).decode() if path.exists() else None
                 for path in updates}
    (BACKUP / 'inventory.json').write_text(json.dumps(originals))
    try:
        for path, data in updates.items():
            replace(path, data)
        restart_workers()
        for unit in UNITS:
            if MODEL not in command(unit):
                raise RuntimeError(f'{unit} did not start with Bonsai')
    except Exception:
        restore()
        raise
    print('Both photo workers are running with Bonsai. Previous settings were backed up.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['switch', 'restore'])
    args = parser.parse_args()
    if os.environ.get('KI_BONSAI_REMOTE') == '1':
        os.umask(0o077)
        switch(json.load(sys.stdin)) if args.action == 'switch' else restore()
        return
    root = Path(__file__).parent
    files = {relative: (root / relative).read_text() for relative in CONTEXT_SOURCES}
    remote = 'KI_BONSAI_REMOTE=1 python3 -c ' + shlex.quote(Path(__file__).read_text()) + ' ' + args.action
    subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', os.environ['CB_HOST'], remote],
                   input=json.dumps(files), text=True, check=True)


if __name__ == '__main__':
    main()
