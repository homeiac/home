#!/usr/bin/env python3
"""Run the existing worker with GitOps settings and the host-local Ollama endpoint."""
import json
import os
from pathlib import Path
import sys


def main() -> None:
    """Keep model identity stable; endpoint and Mac authentication remain host-local."""
    root = Path('/opt/knowledge-index')
    config = json.loads((root / 'caption-gitops/config.json').read_text())
    endpoint = os.environ['KI_OLLAMA_URL']
    if config.get('priority_manifest'):
        os.environ['KI_SUMMARY_PRIORITY_MANIFEST'] = config['priority_manifest']
    args = [str(root / 'venv/bin/python'), str(root / 'enrichers/media_summary.py'), 'run']
    for name in ('index', 'library', 'model', 'enricher', 'api', 'parallel', 'batch_size', 'min_free_mib'):
        args.extend(['--' + name.replace('_', '-'), str(config[name])])
    args.extend(['--endpoint', endpoint, '--extra-json', json.dumps(config['extra'])])
    for name in ('frames', 'video_edge', 'video_prompt', 'video_tokens', 'mac_video_parallel', 'video_decode_threads'):
        if name in config:
            args.extend(['--' + name.replace('_', '-'), str(config[name])])
    if config['mac_assist']:
        args.append('--mac-assist')
    os.execv(args[0], args)


if __name__ == '__main__':
    main()
