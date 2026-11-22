#!/usr/bin/env python3
"""Restricted SSH entry point: reconcile a bounded ConfigMap bundle on the host.

Only this worker's allow-listed files and service can change. Back up first and
restore files/overrides on failed startup. No shell commands from the payload.
"""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path('/opt/knowledge-index')
UNIT = 'knowledge-index-enrich.service'
UNIT_PATH = Path('/etc/systemd/system') / UNIT
FILES = {
    'media_summary.py': ROOT / 'enrichers/media_summary.py',
    'pipeline_metrics.py': ROOT / 'enrichers/pipeline_metrics.py',
    'summary_cache.py': ROOT / 'enrichers/summary_cache.py',
    'run.py': ROOT / 'caption-gitops/run.py',
    'config.json': ROOT / 'caption-gitops/config.json',
    'dispatch-policy.json': ROOT / 'caption-gitops/dispatch-policy.json',
    'knowledge-index-enrich.service': UNIT_PATH,
}
METRICS = Path('/var/lib/prometheus/node-exporter/knowledge_index_pipeline.prom')


def command(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Execute fixed argument lists, never a shell supplied in the bundle."""
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=60)


def validate(bundle: dict) -> dict:
    """Reject incomplete bundles, unexpected destinations and malformed settings."""
    if set(bundle) != set(FILES) or any(not isinstance(v, str) for v in bundle.values()):
        raise ValueError('Unexpected or missing worker files')
    for name, content in bundle.items():
        if name.endswith('.py'):
            compile(content, name, 'exec')
    config = json.loads(bundle['config.json'])
    if type(config['enabled']) is not bool or type(config['mac_assist']) is not bool:
        raise ValueError('Expected boolean settings')
    if config['index'] != '/local-3TB-backup/knowledge-index' or config['library'] != '/local-3TB-backup/gphotos/library':
        raise ValueError('Refusing a different library or index')
    if config['enricher'] != 'gemma4-e2b-p1':
        raise ValueError('Refusing to reset the existing completed-work identity')
    if config['model'] != 'bonsai-27b' or config['api'] != 'ollama':
        raise ValueError('Unexpected model or API')
    for name, maximum in [('parallel', 4), ('batch_size', 200), ('min_free_mib', 65536)]:
        if type(config[name]) is not int or not 1 <= config[name] <= maximum:
            raise ValueError('Invalid numeric setting: ' + name)
    policy = json.loads(bundle['dispatch-policy.json'])
    if (policy['mode'] not in ('batch', 'continuous') or policy['mac_routing'] not in ('fifo', 'photo-first')
            or policy['queue_order'] not in ('newest', 'photos-first') or type(policy['page_size']) is not int
            or not 0 <= policy['page_size'] <= 512):
        raise ValueError('Invalid dispatch policy')
    return config


def replace(path: Path, content: bytes) -> None:
    """Publish one complete file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.gitops-tmp')
    temp.write_bytes(content)
    temp.chmod(0o644)
    temp.replace(path)


def preflight(config: dict) -> None:
    """Require the existing runtime and data before mutating service files."""
    if not (ROOT / 'venv/bin/python').exists() or not Path('/etc/default/knowledge-index').exists():
        raise RuntimeError('Existing Python environment and Ollama endpoint are required')
    if not Path(config['index'], 'knowledge.duckdb').is_file() or not Path(config['library']).is_dir():
        raise RuntimeError('Existing data mounts are required')


def reconcile(bundle: dict) -> dict:
    """Apply desired files; only restart when execution settings or code changed."""
    config = validate(bundle)
    preflight(config)
    # Retire only this worker's legacy transient/model overrides, after a backup.
    overrides = [p for base in ('/etc/systemd/system', '/run/systemd/system')
                 for p in (Path(base) / (UNIT + '.d')).glob('*.conf')]
    transient = Path('/run/systemd/transient') / UNIT
    changed = {name: content.encode() for name, content in bundle.items()
               if not FILES[name].exists() or FILES[name].read_bytes() != content.encode()}
    restart = bool(set(changed) - {'dispatch-policy.json'} or overrides or transient.exists())
    was_active = command('systemctl', 'is-active', '--quiet', UNIT, check=False).returncode == 0
    was_enabled = command('systemctl', 'is-enabled', '--quiet', UNIT, check=False).returncode == 0
    originals = {path: path.read_bytes() if path.exists() else None for path in [*FILES.values(), *overrides]}
    if changed or overrides or transient.exists():
        backup = ROOT / 'backups' / ('caption-gitops-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        backup.mkdir(parents=True, mode=0o700)
        for path, content in originals.items():
            if content is not None:
                dest = backup / str(path).lstrip('/')
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
        print('Backup: ' + str(backup), flush=True)
    try:
        if (restart or not config['enabled']) and was_active:
            command('systemctl', 'stop', UNIT)
        # Stopping collects the legacy transient unit. Never delete completed output.
        for path in overrides:
            path.unlink()
        for name, content in changed.items():
            replace(FILES[name], content)
        command('systemd-analyze', 'verify', str(FILES['knowledge-index-enrich.service']))
        command('systemctl', 'daemon-reload')
        if not config['enabled']:
            command('systemctl', 'disable', '--now', UNIT)
        else:
            command('systemctl', 'enable', UNIT)
            started = time.time()
            command('systemctl', 'start', UNIT)
            for _ in range(45):
                if METRICS.exists() and METRICS.stat().st_mtime >= started - (60 if was_active and not restart else 0):
                    if command('systemctl', 'is-active', '--quiet', UNIT, check=False).returncode == 0:
                        break
                time.sleep(1)
            else:
                raise RuntimeError('Worker did not publish a fresh heartbeat')
    except Exception:
        command('systemctl', 'stop', UNIT, check=False)
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                replace(path, content)
        command('systemctl', 'daemon-reload', check=False)
        if not was_enabled:
            command('systemctl', 'disable', UNIT, check=False)
        if was_active:
            command('systemctl', 'start', UNIT, check=False)
        raise
    digest = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()
    state = {'bundle_sha256': digest, 'enabled': config['enabled'], 'changed_files': sorted(changed),
             'restarted': restart, 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    replace(ROOT / 'caption-gitops/applied.json', json.dumps(state, indent=2).encode())
    return state


def main() -> None:
    """Serialize installer Jobs and reject oversized input before decoding."""
    os.umask(0o077)
    with open('/run/lock/knowledge-index-caption-deploy.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        raw = sys.stdin.buffer.read(900_001)
        if len(raw) > 900_000:
            raise ValueError('Worker bundle too large')
        print(json.dumps(reconcile(json.loads(raw))))


if __name__ == '__main__':
    main()
