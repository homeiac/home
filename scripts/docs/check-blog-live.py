#!/usr/bin/env python3
"""Fail unless the live Pages site serves the exact validated build."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

from blog_publication import MANIFEST, digest


def fetch(base_url: str, path: str, revision: str) -> bytes:
    """Read a public page with bounded networking and a revision cache key."""
    url = base_url.rstrip("/") + "/" + quote(path) + "?revision=" + quote(revision)
    request = Request(url, headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=20) as response:
        return response.read()


def verify_live(base_url: str, expected: dict) -> None:
    """Reject an old deployment, missing pages, or stale HTML content."""
    revision = expected["revision"]
    actual = json.loads(fetch(base_url, MANIFEST, revision))
    if actual != expected:
        raise ValueError("Live publication manifest does not match this build")

    def check(item: tuple[str, str]) -> None:
        path, checksum = item
        if digest(fetch(base_url, path, revision)) != checksum:
            raise ValueError(f"Live page differs from the validated build: {path}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(check, expected["files"].items()))


def main() -> None:
    """Allow CDN propagation briefly, then fail the workflow on any mismatch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--delay", type=float, default=10)
    args = parser.parse_args()
    if args.attempts < 1 or args.delay < 0:
        parser.error("attempts must be positive and delay must be nonnegative")
    expected = json.loads(args.manifest.read_text(encoding="utf-8"))
    for attempt in range(1, args.attempts + 1):
        try:
            verify_live(args.url, expected)
        except (OSError, ValueError) as error:
            logging.error("Live verification %d/%d failed: %s", attempt, args.attempts, error)
            if attempt == args.attempts:
                raise SystemExit(1) from error
            time.sleep(args.delay)
        else:
            logging.info("Verified revision %s and all %d live pages", expected["revision"], len(expected["files"]))
            return


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
