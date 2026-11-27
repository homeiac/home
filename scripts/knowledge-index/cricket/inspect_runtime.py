"""Read current host capacity and reuse existing audio evidence without changing workers."""

import argparse
import json
import logging
import os
import shlex
import subprocess
from pathlib import Path

REMOTE = r"""
import json,os,sqlite3,subprocess,sys
from pathlib import Path
from contextlib import closing
inventory=json.load(sys.stdin)
library=Path('/local-3TB-backup/gphotos/library')
result={'cpus':os.cpu_count(),'load':os.getloadavg(),'memory':{},'services':{},'audio':{},'sources':{}}
for line in Path('/proc/meminfo').read_text().splitlines():
    k,v=line.split(':',1)
    if k in ('MemAvailable','MemTotal','SwapFree','SwapTotal'):result['memory'][k]=v.strip()
for unit in ('photo-enrichment-gui','knowledge-index-enrich','knowledge-index-audio-story'):
    result['services'][unit]=subprocess.run(['systemctl','is-active',unit],capture_output=True,text=True).stdout.strip()
result['worker_args']={}
for unit in ('knowledge-index-enrich','photo-enrichment-gui'):
    pid=subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip()
    if pid.isdigit() and pid!='0':
        argv=Path('/proc',pid,'cmdline').read_bytes().decode().split('\0')
        result['worker_args'][unit]={flag:argv[argv.index(flag)+1] for flag in ('--endpoint','--model','--parallel','--port') if flag in argv}
result['gui_release']=str(Path('/opt/photo-enrichment/gui').resolve())
audio=Path('/local-3TB-backup/photo-enrichment/audio-story/ledger.sqlite3')
if audio.exists():
    with closing(sqlite3.connect(audio.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        wanted={a['originalPath'].removeprefix('/external/gphotos/'):a for a in inventory['assets']}
        for row in db.execute('SELECT path,aliases,size_bytes,visual_summary,duration_s,audio_state,transcript FROM jobs WHERE active=1'):
            matches=set([row['path'],*json.loads(row['aliases'] or '[]')]) & wanted.keys()
            for path in matches:
                asset=wanted[path]
                if row['size_bytes']==asset['exifInfo']['fileSizeInByte']:
                    result['audio'][asset['id']]=dict(row)
for asset in inventory['assets']:
    relative=asset['originalPath'].removeprefix('/external/gphotos/')
    path=(library/relative).resolve()
    if not path.is_relative_to(library) or not path.is_file():continue
    stat=path.stat()
    result['sources'][asset['id']]={'locator':relative,'fingerprint':f'stat:{stat.st_size}:{stat.st_mtime_ns}',
                                   'size':stat.st_size}
print(json.dumps(result))
"""


def main() -> None:
    """Save evidence privately and report only aggregate readiness."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--album-name", default="All cricket videos")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    albums = [
        a
        for a in json.loads(args.inventory.read_text())
        if a["name"] == args.album_name
    ]
    if len(albums) != 1:
        raise ValueError("Expected exactly one selected album")
    response = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            args.host,
            "python3 -c " + shlex.quote(REMOTE),
        ],
        input=json.dumps(albums[0]),
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    result = json.loads(response.stdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(result, output)
    counts = {}
    for row in result["audio"].values():
        counts[row["audio_state"]] = counts.get(row["audio_state"], 0) + 1
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info(
        "%s",
        json.dumps(
            {
                **{k: v for k, v in result.items() if k not in {"audio", "sources"}},
                "matched_sources": len(result["sources"]),
                "audio_states": counts,
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
