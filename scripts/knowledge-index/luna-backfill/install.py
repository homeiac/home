"""Bootstrap the Luna worker and Piglet ledger from this checkout; subsequent scheduling policy comes from Git."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
LABEL='com.panderosystems.knowledge-index-luna'


def main():
    os.umask(0o077)
    target=os.environ['CB_HOST']
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',target]
    subprocess.run(ssh+['install -d -m 0700 /opt/knowledge-index/luna-backfill && install -m 0644 /dev/stdin /opt/knowledge-index/luna-backfill/reconciliation.py'],
                   input=(HERE/'reconciliation.py').read_bytes(),check=True)
    subprocess.run(ssh+["set -eu; d=/opt/knowledge-index/luna-backfill; install -d -m 700 \"$d\"; "
                        "p=$(mktemp \"$d/host.XXXXXX\"); cat > \"$p\"; "
                        "/opt/photo-enrichment/context/venv/bin/python -m py_compile \"$p\"; mv \"$p\" \"$d/host.py\""],
                   input=(HERE/'host.py').read_bytes(),check=True)
    # Count earlier Luna experiments conservatively toward the single campaign.
    subprocess.run(ssh+['/opt/photo-enrichment/context/venv/bin/python /opt/knowledge-index/luna-backfill/host.py'],
                   input=json.dumps({'op':'init','pilot_microdollars':1_000_000}),text=True,check=True)
    if '--prepare-only' in sys.argv:
        return
    path=Path.home()/'Library/Application Support/knowledge-index-luna'
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path/'worker.new'
    shutil.copyfile(HERE/'worker.py',tmp)
    tmp.replace(path/'worker.py')
    shutil.copyfile(HERE/'reconciliation.py',path/'reconciliation.py')
    plist=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')
    plist.parent.mkdir(exist_ok=True)
    codex=shutil.which('codex')
    if not codex:raise RuntimeError('Codex CLI missing')
    doc=dict(Label=LABEL,ProgramArguments=[sys.executable,str(path/'worker.py')],RunAtLoad=True,
             StartInterval=300,WorkingDirectory=str(path),StandardOutPath=str(path/'worker.log'),
             StandardErrorPath=str(path/'worker-errors.log'),
             EnvironmentVariables=dict(CB_HOST=target,PATH=str(Path(codex).parent)+':/opt/homebrew/bin:/usr/bin:/bin'))
    temporary=plist.with_suffix('.new')
    temporary.write_bytes(plistlib.dumps(doc))
    temporary.replace(plist)
    domain=f'gui/{os.getuid()}'
    subprocess.run(['launchctl','bootout',domain+'/'+LABEL],capture_output=True)
    subprocess.run(['launchctl','bootstrap',domain,str(plist)],check=True)


if __name__=='__main__':main()
