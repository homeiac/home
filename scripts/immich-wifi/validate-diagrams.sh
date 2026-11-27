#!/usr/bin/env bash
# Render the Mermaid blocks in the current network docs to a temporary folder.
# Generated previews are not committed; mmdc reports invalid Mermaid syntax.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
output=${1:-/private/tmp/immich-wifi-diagrams}
# Reuse installed Chrome when mmdc's optional downloaded browser is absent.
chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
if [[ -z ${PUPPETEER_EXECUTABLE_PATH:-} && -x $chrome ]]; then
  export PUPPETEER_EXECUTABLE_PATH="$chrome"
fi
python3 - "$root" "$output" <<'PY'
import logging
from pathlib import Path
import re
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format='%(message)s')
root, output = map(Path, sys.argv[1:])
output.mkdir(parents=True, exist_ok=True)
paths = [
    'docs/blog/2026-11-15-taking-my-files-back-from-google-and-onedrive.md',
    'docs/reference/google-wifi-immich-architecture.md',
    'docs/source/md/homelab-network-topology.md',
    'docs/product/seamless-access/architecture-seamless-access.md',
    'docs/source/md/blog-immich-google-wifi-gitops.md',
]
total = 0
for relative in paths:
    source = root / relative
    for index, diagram in enumerate(re.findall(r'```mermaid\n(.*?)```', source.read_text(), re.S), 1):
        target = output / f'{source.stem}-{index}.mmd'
        target.write_text(diagram)
        subprocess.run(['mmdc', '-q', '-i', str(target), '-o', str(target.with_suffix('.png')), '-w', '1600'], check=True)
        total += 1
logging.info('Rendered and validated %d diagrams in %s', total, output)
PY
