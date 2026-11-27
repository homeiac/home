"""Start a temporary extra Metal server, benchmark it, and release only that process."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'mac-bonsai'))
from runtime import ROOT, start


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--slots', type=int, choices=range(1, 21), default=8)
    parser.add_argument('--count', type=int, choices=range(1, 65), default=16)
    args = parser.parse_args()
    folder = args.folder.resolve()
    if folder.stat().st_mode & 0o077 or any(not (folder / f'{i}.jpg').is_file() for i in range(args.count)):
        parser.error('Prepare the matched private photo folder before running')
    if args.count < args.slots:
        parser.error('At least one photo per slot is required')
    if (folder / f'extra-{args.slots}-result.json').exists():
        parser.error('This slot count already has a measured result. Use a new private folder for a repeat.')
    os.umask(0o077)
    port = 19582
    # Refuse a port collision instead of sending traffic to an existing server.
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', port))
    key_file = ROOT / 'server.key'
    key = key_file.read_text().strip()
    req = urllib.request.Request(f'http://127.0.0.1:{port}/props', headers={'Authorization': 'Bearer ' + key})
    def terminate(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    with (folder / f'extra-{args.slots}-server.log').open('w') as log:
        server = start(args.slots, port, log, key_file, offered=args.slots)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError(f'Trial server exited with status {server.returncode}')
                try:
                    with urllib.request.urlopen(req, timeout=2) as response:
                        config = json.load(response)
                    if config['total_slots'] != args.slots or config.get('model_alias') != 'bonsai-27b-metal':
                        raise RuntimeError('Trial server reported an unexpected configuration')
                    break
                except OSError:
                    time.sleep(1)
            else:
                raise TimeoutError('Trial server did not become ready')
            begin = time.time()
            output = subprocess.check_output([
                sys.executable, str(HERE / 'benchmark.py'), 'mac', str(folder),
                '--mac-port', str(port), '--slots', str(args.slots), '--count', str(args.count),
            ], text=True, timeout=1200)
            result = json.loads(output)
            result.update(start=begin, end=time.time(), confirmed_server_slots=config['total_slots'])
            (folder / f'extra-{args.slots}-result.json').write_text(json.dumps(result))
            print(json.dumps(result), flush=True)
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == '__main__':
    main()
