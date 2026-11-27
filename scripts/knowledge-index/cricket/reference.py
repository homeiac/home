"""Read the selected person's existing Immich portrait into private local storage."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from .importer import select_person


def main() -> None:
    """Keep the face reference local; never print its bytes or the API credential."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", required=True, type=Path)
    parser.add_argument("--name", default="Adil")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    people = json.loads(args.people.read_text())
    person = select_person([{"id": k, "name": v} for k, v in people.items()], args.name)
    source = """
import fs from 'node:fs/promises';
const key=(await fs.readFile('/credentials/api-key','utf8')).trim();
const base=process.env.IMMICH_URL||'http://immich-server:2283/api';
const response=await fetch(base+'/people/'+encodeURIComponent(person)+'/thumbnail',{headers:{'x-api-key':key},signal:AbortSignal.timeout(30000)});
if(!response.ok)throw Error('Portrait HTTP '+response.status);
process.stdout.write(Buffer.from(await response.arrayBuffer()));
"""
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
        input=("const person=" + json.dumps(person) + ";" + source).encode(),
        capture_output=True,
        timeout=60,
        check=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(response.stdout)


if __name__ == "__main__":
    main()
