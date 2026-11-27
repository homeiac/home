"""Inspect existing private review code and bridge health before an additive rollout."""

import argparse
import json
import logging
import shlex
import subprocess
from pathlib import Path

from .prepare import save_private

REMOTE = r"""
import json,hashlib,subprocess,urllib.request
from pathlib import Path
root=Path('/opt/photo-enrichment/gui').resolve()
names=['photo-enrich.py','photo_enrichment/server.py','photo_enrichment/static/index.html','photo_enrichment/static/app.js']
files={name:(root/name).read_text() for name in names if (root/name).exists()}
unit=Path('/etc/systemd/system/photo-enrichment-gui.service').read_text()
health={}
try:
    request=urllib.request.Request('http://127.0.0.1:19476/v1/models',headers={'Authorization':'Bearer '+Path('/opt/knowledge-index/mac-bonsai.key').read_text().strip()})
    with urllib.request.urlopen(request,timeout=10) as response:health['mac_models']=[m['id'] for m in json.load(response)['data']]
except (OSError,ValueError,KeyError) as error:health['mac']=type(error).__name__
for name in ('photo-enrichment-gui','knowledge-index-enrich','knowledge-index-audio-story'):
    health[name]=subprocess.run(['systemctl','is-active',name],capture_output=True,text=True).stdout.strip()
print(json.dumps({'release':str(root),'files':files,'hashes':{n:hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()},'unit':unit,'health':health}))
"""


def main() -> None:
    """Keep deployment contents private; print only service readiness."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            args.host,
            "python3 -c " + shlex.quote(REMOTE),
        ],
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )
    value = json.loads(result.stdout)
    save_private(args.output, value)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(
        "%s", json.dumps({"release": value["release"], "health": value["health"]})
    )


if __name__ == "__main__":
    main()
