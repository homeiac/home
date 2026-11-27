"""Read serving capacity and save an explicit high-to-low trial policy privately."""

import argparse
import json
import logging
import shlex
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .prepare import save_private

REMOTE = r"""
import json,urllib.request
from pathlib import Path
lines=Path('/etc/default/knowledge-index').read_text().splitlines()
endpoint=next(s.split('=',1)[1].strip().strip('"').strip("'") for s in lines if s.startswith('KI_OLLAMA_URL='))
with urllib.request.urlopen(endpoint.rstrip('/')+'/api/ps',timeout=15) as response:models=json.load(response)
print(json.dumps({'endpoint':endpoint,'models':models,'parallel':json.loads(Path('/opt/knowledge-index/caption-gitops/config.json').read_text())['parallel']}))
"""


def main() -> None:
    """Reuse only reachable existing servers; never start or resize a backend here."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu-host", required=True)
    parser.add_argument("--cpu-host", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    backends = {}
    status = {}
    key_file = (
        Path.home() / "Library/Application Support/knowledge-index-bonsai/server.key"
    )
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:19476/props",
            headers={"Authorization": "Bearer " + key_file.read_text().strip()},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            props = json.load(response)
        slots = int(props["total_slots"])
        if not 1 <= slots <= 20:
            raise ValueError("Unexpected Metal slot count")
        backends["mac"] = {
            "transport": "http",
            "api": "openai",
            "endpoint": "http://127.0.0.1:19476",
            "model": "bonsai-27b-metal",
            "key_file": str(key_file),
            "max_workers": slots,
            "workers": slots,
        }
        status["mac"] = {"state": "ready", "max_workers": slots}
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        status["mac"] = {"state": "standby", "reason": type(error).__name__}
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                args.gpu_host,
                "python3 -c " + shlex.quote(REMOTE),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        info = json.loads(result.stdout)
        parsed = urlsplit(info["endpoint"])
        if parsed.username or parsed.password:
            raise ValueError("Endpoint contains credentials")
        if not any(
            m.get("name", "").startswith("bonsai-27b")
            for m in info["models"].get("models", [])
        ):
            raise ValueError("Bonsai is not loaded")
        bound = int(info["parallel"])
        backends["rtx"] = {
            "transport": "ssh",
            "host": args.gpu_host,
            "api": "ollama",
            "endpoint": info["endpoint"],
            "model": "bonsai-27b",
            "max_workers": bound,
            "workers": bound,
        }
        status["rtx"] = {"state": "ready", "max_workers": bound}
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        status["rtx"] = {"state": "standby", "reason": type(error).__name__}
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                args.cpu_host,
                "qm guest exec 108 --timeout 20 -- curl -fsS --max-time 15 http://127.0.0.1:19479/props",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        report = json.loads(result.stdout)
        if report.get("exitcode") or not report.get("exited"):
            raise ValueError("CPU backend not ready")
        props = json.loads(report["out-data"])
        slots = int(props["total_slots"])
        if not 1 <= slots <= 20:
            raise ValueError("Unexpected CPU slot count")
        backends["cpu"] = {
            "transport": "qga",
            "host": args.cpu_host,
            "api": "openai",
            "endpoint": "http://127.0.0.1:19479",
            "model": "bonsai-27b-cpu",
            "max_workers": slots,
            "workers": slots,
        }
        status["cpu"] = {"state": "ready", "max_workers": slots}
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        status["cpu"] = {"state": "standby", "reason": type(error).__name__}
    save_private(
        args.output, {"enabled": False, "backends": backends, "status": status}
    )
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger(__name__).info("%s", json.dumps(status))


if __name__ == "__main__":
    main()
