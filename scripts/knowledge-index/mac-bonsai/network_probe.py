"""Time sized synthetic POSTs from Piglet to Mac, using the production SSH direction."""

import argparse
import concurrent.futures
import http.server
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

PORT = 19477


class Sink(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        size = int(self.headers["Content-Length"])
        if self.path != "/probe" or size > 16 * 1024 * 1024:
            self.send_error(400)
            return
        received = self.rfile.read(size)
        self.send_response(200 if len(received) == size else 400)
        self.end_headers()

    def log_message(self, *_):
        pass


def client(jobs):
    def send(job):
        label, size = job
        body = os.urandom(size)
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/probe", data=body)
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=30) as response:
            response.read()
        return dict(kind=label, size_bytes=size, seconds=time.monotonic() - start)

    rows = []
    for repeat in range(3):
        for concurrency in (1, 2, 8):
            workload = list(jobs)
            random.Random(217 + repeat).shuffle(workload)
            with concurrent.futures.ThreadPoolExecutor(concurrency) as pool:
                rows.extend(dict(repeat=repeat, offered=concurrency, **r) for r in pool.map(send, workload))
    return rows


def run(inputs, output):
    items = json.loads((inputs / "manifest.json").read_text())["items"]
    jobs = []
    for item in items:
        # Base64 size including padding, plus the image URL envelope and short prompt.
        size = sum(4 * ((((inputs / f).stat().st_size) + 2) // 3) + 72 for f in item["files"]) + 512
        jobs.append((item["kind"], size))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Sink)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        import shlex

        script = Path(__file__).read_text()
        cmd = [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "Compression=no",
            "-o",
            "ExitOnForwardFailure=yes",
            "-R",
            f"127.0.0.1:{PORT}:127.0.0.1:{PORT}",
            os.environ["CB_HOST"],
            "python3 -c " + shlex.quote(script) + " --client",
        ]
        result = subprocess.run(
            cmd, input=json.dumps(jobs), capture_output=True, text=True, check=True, timeout=240
        )
        rows = json.loads(result.stdout)
        output.write_text(json.dumps(rows))
        for offered in (1, 2, 8):
            for kind in ("photo", "video"):
                subset = [r for r in rows if r["offered"] == offered and r["kind"] == kind]
                print(
                    offered,
                    kind,
                    len(subset),
                    "median KiB",
                    round(statistics.median(r["size_bytes"] for r in subset) / 1024),
                    "median ms",
                    round(1000 * statistics.median(r["seconds"] for r in subset)),
                    "max ms",
                    round(1000 * max(r["seconds"] for r in subset)),
                )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


if __name__ == "__main__":
    if sys.argv[1:] == ["--client"]:
        print(json.dumps(client(json.load(sys.stdin))))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("inputs", type=Path)
        parser.add_argument("output", type=Path)
        args = parser.parse_args()
        run(args.inputs, args.output)
