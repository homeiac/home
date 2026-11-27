"""Checks shared by the local blog build and the live deployment audit."""

import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

MANIFEST = "blog-publication.json"


class Links(HTMLParser):
    """Collect navigation targets without depending on HTML formatting."""

    def __init__(self, html: str) -> None:
        super().__init__()
        self.targets: set[str] = set()
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.targets.update(value for key, value in attrs if key == "href" and value)


def blog_paths(root: Path) -> list[str]:
    """Discover every post, including posts added in nested blog directories."""
    folder = root / "docs/blog"
    posts = [
        "blog/" + path.relative_to(folder).with_suffix(".html").as_posix()
        for path in sorted(folder.rglob("*.md"))
    ]
    posts.extend(
        "md/" + path.with_suffix(".html").name
        for path in sorted((root / "docs/source/md").glob("blog-*.md"))
    )
    if not posts:
        raise ValueError("No blog posts found")
    return posts


def digest(data: bytes) -> str:
    """Return the digest used to detect stale or incorrect published content."""
    return hashlib.sha256(data).hexdigest()


def verify_build(root: Path, output: Path, revision: str) -> dict:
    """Validate every post and write an exact-content publication manifest."""
    posts = blog_paths(root)
    index_links = Links((output / "blog.html").read_text(encoding="utf-8")).targets
    files = {}
    for name in ["index.html", "blog.html", *posts]:
        path = output / name
        if not path.is_file():
            raise ValueError(f"Missing rendered page: {name}")
        data = path.read_bytes()
        if b"<html" not in data.lower():
            raise ValueError(f"Not an HTML page: {name}")
        if name in posts and name not in index_links:
            raise ValueError(f"Blog index does not link to: {name}")
        files[name] = digest(data)
    if not (output / ".nojekyll").is_file():
        raise ValueError("Missing .nojekyll for GitHub Pages")
    if "blog.html" not in Links((output / "index.html").read_text(encoding="utf-8")).targets:
        raise ValueError("Home page does not link to the blog")
    manifest = {"revision": revision, "files": files}
    (output / MANIFEST).write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
