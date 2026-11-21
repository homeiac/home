"""Install the pinned runtime and the Git-policy-controlled user launch agent."""

import os
from pathlib import Path
import plistlib
import secrets
import shutil
import subprocess
import sys

from runtime import ROOT

HERE = Path(__file__).resolve().parent
LABEL = "com.panderosystems.knowledge-index-bonsai"


def main():
    os.umask(0o077)
    target = os.environ["CB_HOST"]
    subprocess.run([sys.executable, str(HERE / "prepare.py")], check=True)
    key = ROOT / "server.key"
    if not key.exists():
        with key.open("x") as file:
            file.write(secrets.token_urlsafe(48) + "\n")
    subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            target,
            "set -eu; umask 077; f=$(mktemp /opt/knowledge-index/mac-bonsai.key.XXXXXX); "
            'cat > "$f"; mv "$f" /opt/knowledge-index/mac-bonsai.key',
        ],
        input=key.read_bytes(),
        check=True,
    )
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
    for name in ("runtime.py", "supervisor.py"):
        tmp = ROOT / (name + ".new")
        shutil.copyfile(HERE / name, tmp)
        tmp.replace(ROOT / name)
    plist = Path.home() / "Library/LaunchAgents" / (LABEL + ".plist")
    plist.parent.mkdir(exist_ok=True)
    doc = dict(
        Label=LABEL,
        ProgramArguments=[sys.executable, str(ROOT / "supervisor.py")],
        RunAtLoad=True,
        KeepAlive=True,
        ThrottleInterval=30,
        WorkingDirectory=str(ROOT),
        StandardErrorPath=str(ROOT / "supervisor.log"),
        EnvironmentVariables=dict(CB_HOST=target),
    )
    tmp = plist.with_suffix(".new")
    tmp.write_bytes(plistlib.dumps(doc))
    tmp.replace(plist)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)


if __name__ == "__main__":
    main()
