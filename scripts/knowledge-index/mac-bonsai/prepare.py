"""Install checksum-pinned PrismML Metal binaries and Bonsai vision weights into user storage."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path.home() / "Library/Application Support/knowledge-index-bonsai"
TAG = "prism-b10828-a153697"
REV = "f10afb355f104535e3e3e98cf7ab7795c72bd292"
ASSET = f"llama-{TAG}-bin-macos-arm64.tar.gz"
BASE = f"https://huggingface.co/prism-ml/Bonsai-27B-gguf/resolve/{REV}/"
FILES = [
    (
        ASSET,
        f"https://github.com/PrismML-Eng/llama.cpp/releases/download/{TAG}/{ASSET}",
        "5c6238a1e7d5c2540ad3d47438388df198433981074290e9397eb4db3d786135",
    ),
    (
        "Bonsai-27B-Q1_0.gguf",
        BASE + "Bonsai-27B-Q1_0.gguf",
        "17ef842e47450caeb8eaa3ebfbbab5d2f2278b62b79be107985fb69a2f819aa0",
    ),
    (
        "Bonsai-27B-mmproj-Q8_0.gguf",
        BASE + "Bonsai-27B-mmproj-Q8_0.gguf",
        "eb561d41a7bbeb0fcf04883c8af11078ef6cae0a66862a0b68443cfca495269d",
    ),
]


def fetch(entry):
    name, url, expected = entry
    dst = ROOT / name
    path = dst if dst.exists() else dst.with_suffix(".partial")
    if path != dst:
        subprocess.run(
            [
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--retry",
                "2",
                "--continue-at",
                "-",
                "--max-time",
                "1200",
                "--output",
                str(path),
                url,
            ],
            check=True,
        )
    with path.open("rb") as f:
        if hashlib.file_digest(f, "sha256").hexdigest() != expected:
            raise ValueError("Digest mismatch: " + name)
    path.replace(dst)
    print("Verified", name, flush=True)


if __name__ == "__main__":
    os.umask(0o077)
    ROOT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(fetch, FILES))
    # A reinstall cannot overwrite an executable or library mapped by a running server.
    release = ROOT / TAG
    if not release.is_dir():
        with TemporaryDirectory(dir=ROOT) as tmp, tarfile.open(ROOT / ASSET) as tar:
            stage = Path(tmp) / "release"
            tar.extractall(stage, filter="data")
            stage.rename(release)
