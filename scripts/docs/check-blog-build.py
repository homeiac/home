#!/usr/bin/env python3
"""Fail deployment if any blog post is missing from HTML or the blog index."""

import argparse
import logging
from pathlib import Path

from blog_publication import verify_build


def main() -> None:
    """Verify both blog source locations and GitHub Pages output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", default="local")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifest = verify_build(root, root / "docs/build/html", args.revision)
    logging.info("Verified %d blog posts and wrote publication manifest", len(manifest["files"]) - 2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
