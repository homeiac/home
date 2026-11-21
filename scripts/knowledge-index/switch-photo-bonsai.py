#!/usr/bin/env python3
"""Switch the two Proxmox photo workers to the private Flux-managed Bonsai service."""
import argparse
import ast
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


ENDPOINT = 'http://127.0.0.1:18082'
MODEL = 'bonsai-27b'
UNITS = ('knowledge-index-enrich.service', 'photo-enrichment-context.service')
BACKUP = Path('/opt/knowledge-index/backups/photo-bonsai-v1')
CONTEXT = Path('/opt/photo-enrichment/context')
BRIDGE = Path('/opt/knowledge-index/photo-bonsai-bridge.py')
BRIDGE_UNIT = Path('/etc/systemd/system/photo-bonsai-bridge.service')
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


def restart_worker(unit):
    systemctl('daemon-reload')
    systemctl('restart', unit)
    time.sleep(3)
    systemctl('is-active', '--quiet', unit)


def prepare_bridge(source):
    compile(source, str(BRIDGE), 'exec')
    replace(BRIDGE, source.encode())
    replace(BRIDGE_UNIT, f'''[Unit]
Description=Loopback bridge to photo Bonsai in VM 105
After=pve-cluster.service

[Service]
ExecStart=/usr/bin/python3 {BRIDGE}
Restart=on-failure

[Install]
WantedBy=multi-user.target
'''.encode())
    systemctl('daemon-reload')
    systemctl('enable', '--now', BRIDGE_UNIT.name)


def jpeg_source(source):
    node = next(node for node in ast.parse(source).body if getattr(node, 'name', '') == 'jpeg_frame')
    return ast.get_source_segment(source, node)


def install_heic(source, unit):
    root = Path('/opt/knowledge-index') if unit == UNITS[0] else CONTEXT
    path = (root / 'enrichers/media_summary.py').resolve(strict=True)
    before = path.read_text()
    old, new = jpeg_source(before), jpeg_source(source)
    if old == new:
        print(f'{unit} already has the HEIC decoder.')
        return
    expected = 'e5f88dd2b9add7b6b4324f7f621bb5df7166f04ea405685e3a06d33668beac24'
    if hashlib.sha256(old.encode()).hexdigest() != expected or before.count(old) != 1:
        raise RuntimeError('Unexpected installed image decoder')
    if unit == UNITS[0]:
        subprocess.run(['/usr/bin/python3', '-m', 'pip', '--python', str(root / 'venv/bin/python'),
                        'install', '--only-binary=:all:', '--disable-pip-version-check', '--quiet',
                        'Pillow==12.0.0', 'pillow-heif==1.1.1'], check=True, timeout=120)
    subprocess.run([str(root / 'venv/bin/python'), '-c', 'import PIL, pillow_heif'], check=True, timeout=15)
    updated = before.replace(old, new)
    compile(updated, str(path), 'exec')
    backup = BACKUP / unit / 'media_summary-before-heic.py'
    if backup.exists():
        raise RuntimeError('HEIC decoder backup already exists')
    replace(backup, before.encode())
    try:
        replace(path, updated.encode())
        restart_worker(unit)
    except Exception:
        replace(path, before.encode())
        restart_worker(unit)
        raise
    print(f'{unit} restarted with the HEIC decoder.')


def restore(unit):
    inventory = json.loads((BACKUP / unit / 'inventory.json').read_text())
    for name, original in inventory.items():
        path = Path(name)
        if original is None:
            path.unlink(missing_ok=True)
        else:
            replace(path, base64.b64decode(original))
    restart_worker(unit)


def switch(files, unit):
    with urllib.request.urlopen(ENDPOINT + '/health', timeout=12) as response:
        if json.load(response).get('status') != 'ok':
            raise RuntimeError('Bonsai readiness endpoint is not healthy')
    argv = command(unit)
    old_model = argv[argv.index('--model') + 1]
    if old_model == MODEL:
        print(f'{unit} already uses Bonsai.')
        return
    updates = {}
    set_option(argv, '--endpoint', ENDPOINT)
    set_option(argv, '--model', MODEL)
    set_option(argv, '--api', 'openai')
    if unit == UNITS[0]:
        metrics = Path('/opt/knowledge-index/enrichers/pipeline_metrics.py')
        original = metrics.read_bytes()
        if original.count(b'"inference": "Ollama request"') != 1:
            raise RuntimeError('Unexpected installed summary metric label')
        updates[metrics] = original.replace(b'"inference": "Ollama request"', b'"inference": "Model request"')
        # Keep the existing enricher key and checkpoint more often during rollout.
        set_option(argv, '--batch-size', '16')
        set_option(argv, '--extra-json', json.dumps({
            'chat_template_kwargs': {'enable_thinking': False}, 'max_tokens': 384}))
    else:
        for relative, digest in CONTEXT_SOURCES.items():
            path = (CONTEXT / relative).resolve(strict=True)
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f'Unexpected installed version of {relative}')
            compile(files[relative], str(path), 'exec')
            updates[path] = files[relative].encode()
        set_option(argv, '--seed-model', old_model)
    updates[dropin(unit)] = exec_start(argv)

    BACKUP.mkdir(mode=0o700, exist_ok=True)
    backup = BACKUP / unit
    backup.mkdir(mode=0o700)
    originals = {str(path): base64.b64encode(path.read_bytes()).decode() if path.exists() else None
                 for path in updates}
    (backup / 'inventory.json').write_text(json.dumps(originals))
    try:
        for path, data in updates.items():
            replace(path, data)
        restart_worker(unit)
        if MODEL not in command(unit):
            raise RuntimeError(f'{unit} did not start with Bonsai')
    except Exception:
        restore(unit)
        raise
    print(f'{unit} is running with Bonsai. Previous settings were backed up.')


def switch_to_ollama(unit):
    config = Path('/etc/default/knowledge-index').read_text()
    endpoint = next(line.partition('=')[2].strip().strip('"\'') for line in config.splitlines()
                    if line.startswith('KI_OLLAMA_URL='))
    request = urllib.request.Request(endpoint.rstrip('/') + '/api/show',
                                     json.dumps({'model': MODEL}).encode(), {'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        if 'vision' not in json.load(response).get('capabilities', []):
            raise RuntimeError('The existing Ollama endpoint does not advertise Bonsai vision')
    argv = command(unit)
    if argv[argv.index('--model') + 1] != MODEL:
        raise RuntimeError(f'{unit} must already be using Bonsai')
    if argv[argv.index('--api') + 1] == 'ollama':
        return
    if argv[argv.index('--endpoint') + 1] != ENDPOINT:
        raise RuntimeError(f'{unit} is not using the expected standalone endpoint')
    set_option(argv, '--endpoint', endpoint)
    set_option(argv, '--api', 'ollama')
    if unit == UNITS[0]:
        set_option(argv, '--extra-json', json.dumps({'think': False, 'options': {
            'num_ctx': 8192, 'num_predict': 384, 'temperature': 0.2}}))
    path = dropin(unit)
    original = path.read_bytes()
    backup = BACKUP / unit / 'standalone-service.conf'
    if not backup.exists():
        replace(backup, original)
    try:
        replace(path, exec_start(argv))
        restart_worker(unit)
        if command(unit)[argv.index('--api') + 1] != 'ollama':
            raise RuntimeError(f'{unit} did not start with native Ollama')
    except Exception:
        replace(path, original)
        restart_worker(unit)
        raise
    print(f'{unit} is running with Bonsai through Ollama.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'switch-summary', 'switch-context', 'restore-summary',
                                           'restore-context', 'fix-heic-summary', 'fix-heic-context',
                                           'ollama-summary', 'ollama-context'])
    args = parser.parse_args()
    if os.environ.get('KI_BONSAI_REMOTE') == '1':
        os.umask(0o077)
        if args.action == 'prepare':
            prepare_bridge(sys.stdin.read())
        elif args.action.startswith('switch-'):
            switch(json.load(sys.stdin), UNITS[args.action.endswith('-context')])
        elif args.action.startswith('fix-heic-'):
            install_heic(sys.stdin.read(), UNITS[args.action.endswith('-context')])
        elif args.action.startswith('ollama-'):
            switch_to_ollama(UNITS[args.action.endswith('-context')])
        else:
            restore(UNITS[args.action.endswith('-context')])
        return
    root = Path(__file__).parent
    if args.action == 'prepare':
        data = (root / 'host/photo-bonsai-bridge.py').read_text()
    elif args.action.startswith('fix-heic-'):
        data = (root / 'enrichers/media_summary.py').read_text()
    else:
        data = json.dumps({relative: (root / relative).read_text() for relative in CONTEXT_SOURCES})
    remote = 'KI_BONSAI_REMOTE=1 python3 -c ' + shlex.quote(Path(__file__).read_text()) + ' ' + args.action
    subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', os.environ['CB_HOST'], remote],
                   input=data, text=True, check=True)


if __name__ == '__main__':
    main()
