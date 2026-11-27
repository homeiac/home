#!/usr/bin/env python3
"""Fail deployment if any blog post is missing from HTML or the blog index."""

import logging
from pathlib import Path


def main() -> None:
    """Verify both blog source locations and GitHub Pages output."""
    root = Path(__file__).resolve().parents[2]
    output = root / "docs/build/html"
    index = (output / "blog.html").read_text(encoding="utf-8")
    posts = [
        Path("blog") / post.with_suffix(".html").name
        for post in sorted((root / "docs/blog").glob("*.md"))
    ] + [
        Path("md") / post.with_suffix(".html").name
        for post in sorted((root / "docs/source/md").glob("blog-*.md"))
    ]
    if not posts:
        raise SystemExit("No blog posts found")
    for post in posts:
        if not (output / post).is_file():
            raise SystemExit(f"Missing rendered blog post: {post}")
        if f'href="{post.as_posix()}"' not in index:
            raise SystemExit(f"Blog index does not link to: {post}")
    if not (output / ".nojekyll").is_file():
        raise SystemExit("Missing .nojekyll for GitHub Pages")
    home = (output / "index.html").read_text(encoding="utf-8")
    if 'href="blog.html"' not in home:
        raise SystemExit("Home page does not link to the blog")
    logging.info("Verified %d blog posts, blog navigation, and .nojekyll", len(posts))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
