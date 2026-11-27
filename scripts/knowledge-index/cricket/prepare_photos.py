"""Recover undecodable photos from Immich's existing previews without changing originals."""

import argparse
import base64
import io
import json
import logging
import shlex
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

from .evidence import VERSION, audio_evidence, fingerprint
from .ledger import Ledger
from .prepare import save_preview, save_private

VERIFY = r"""
import json,sys
from pathlib import Path
root=Path('/local-3TB-backup/gphotos/library').resolve()
for asset in json.load(sys.stdin):
 source=(root/asset['locator']).resolve()
 if not source.is_relative_to(root):raise ValueError('Invalid source')
 stat=source.stat()
 if asset['fingerprint']!=f'stat:{stat.st_size}:{stat.st_mtime_ns}':raise ValueError('Source changed')
"""
FETCH = r"""
import fs from 'node:fs/promises';
const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
const base=process.env.IMMICH_URL||'http://immich-server:2283/api';
const response=await fetch(base+'/assets/'+encodeURIComponent(asset)+'/thumbnail?size=preview',{
 headers:{'x-api-key':key},signal:AbortSignal.timeout(60000)});
if(!response.ok)throw Error('Preview HTTP '+response.status);
process.stdout.write(Buffer.from(await response.arrayBuffer()));
"""


def prepared_photo(asset: dict, audio: dict | None, preview: bytes) -> dict:
    """Validate and resize the derived preview, recording its provenance explicitly."""
    with Image.open(io.BytesIO(preview)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((768, 768))
        output = io.BytesIO()
        image.save(output, "JPEG", quality=85)
    return {
        "version": VERSION,
        "asset": asset["id"],
        "cache_key": fingerprint({"asset": asset, "audio": audio}),
        "source": "immich-existing-preview",
        "windows": [
            {
                "start": 0,
                "end": 0,
                "positions": [None],
                "frames": [base64.b64encode(output.getvalue()).decode()],
                "audio": audio_evidence(audio, 0, 0),
                "context_summary": (audio or {}).get("visual_summary") or "",
            }
        ],
    }


def main() -> None:
    """Retry only missing photo evidence after verifying the original source identities."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--host", required=True)
    args = parser.parse_args()
    with Ledger(args.ledger, read_only=True).connect() as db:
        assets = [
            dict(row)
            for row in db.execute("SELECT * FROM assets WHERE kind='photo'")
            if not (args.folder / (row["id"] + ".json")).exists()
        ]
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", args.host, "python3 -c " + shlex.quote(VERIFY)],
        input=json.dumps(assets),
        text=True,
        check=True,
        timeout=60,
    )
    runtime = json.loads(args.runtime.read_text())
    for asset in assets:
        response = subprocess.run(
            [
                "kubectl",
                "--kubeconfig",
                str(Path.home() / "kubeconfig"),
                "-n",
                "immich-pilot",
                "exec",
                "-i",
                "deploy/immich-sync",
                "--",
                "node",
                "--input-type=module",
                "-",
            ],
            input=("const asset=" + json.dumps(asset["id"]) + ";" + FETCH).encode(),
            capture_output=True,
            check=True,
            timeout=90,
        )
        result = prepared_photo(
            asset, runtime["audio"].get(asset["id"]), response.stdout
        )
        save_private(args.folder / (asset["id"] + ".json"), result)
        save_preview(args.folder, asset, result)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("Recovered %s photo previews", len(assets))


if __name__ == "__main__":
    main()
