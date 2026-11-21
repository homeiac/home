"""Run the pinned Metal model with one full context per slot, bound to Mac loopback."""

from pathlib import Path
import os
import subprocess

ROOT = Path.home() / "Library/Application Support/knowledge-index-bonsai"


def start(slots, port, log, key_file=None, offered=None):
    if not 1 <= slots <= 20:
        raise ValueError("Expected 1 to 20 measured slots")
    release = ROOT / "prism-b10828-a153697"
    binary = next(release.rglob("llama-server"))
    args = [
        str(binary),
        "-m",
        str(ROOT / "Bonsai-27B-Q1_0.gguf"),
        "--mmproj",
        str(ROOT / "Bonsai-27B-mmproj-Q8_0.gguf"),
        "--alias",
        "bonsai-27b-metal",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "-ngl",
        "99",
        "-np",
        str(slots),
        "-c",
        str(slots * 8192),
        "-b",
        "512",
        "-ub",
        "512",
        "--flash-attn",
        "on",
        "--jinja",
    ]
    if key_file:
        if type(offered) is not int or not 1 <= offered <= 20:
            raise ValueError("Expected 1 to 20 offered requests")
        args.extend(["--api-key-file", str(key_file), "--no-webui", "--tags", f"backfill-parallel={offered}"])
    return subprocess.Popen(
        args, stdout=log, stderr=log, env=dict(os.environ, DYLD_LIBRARY_PATH=str(binary.parent))
    )
