"""Regression coverage for automatic discovery and failed publications."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from blog_publication import MANIFEST, blog_paths, verify_build

spec = importlib.util.spec_from_file_location("check_blog_live", SCRIPTS / "check-blog-live.py")
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class PublicationTests(unittest.TestCase):
    """Use small real artifacts and inject only the external HTTP boundary."""

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "docs/build/html"
        for name in ("docs/blog/new.md", "docs/blog/nested/future.md", "docs/source/md/blog-old.md"):
            self.write(name, "# A blog post\n")
        for name in blog_paths(self.root):
            self.write("docs/build/html/" + name, "<html><h1>A blog post</h1></html>")
        links = "".join(f'<a href="{name}">Post</a>' for name in blog_paths(self.root))
        self.write("docs/build/html/blog.html", "<html>" + links + "</html>")
        self.write("docs/build/html/index.html", '<html><a href="blog.html">Blog</a></html>')
        self.write("docs/build/html/.nojekyll", "")

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def manifest(self) -> dict:
        return verify_build(self.root, self.output, "test-commit")

    def test_discovers_both_locations_and_nested_posts(self) -> None:
        self.assertEqual(len(self.manifest()["files"]), 5)
        self.assertIn("blog/nested/future.html", blog_paths(self.root))

    def test_new_unbuilt_post_fails(self) -> None:
        self.write("docs/blog/tomorrow.md", "# Tomorrow\n")
        with self.assertRaisesRegex(ValueError, "Missing rendered page"):
            self.manifest()

    def test_unindexed_post_fails(self) -> None:
        self.write("docs/build/html/blog.html", "<html>No links</html>")
        with self.assertRaisesRegex(ValueError, "does not link"):
            self.manifest()

    def test_plain_text_output_fails(self) -> None:
        self.write("docs/build/html/blog/new.html", "Not rendered")
        with self.assertRaisesRegex(ValueError, "Not an HTML page"):
            self.manifest()

    def test_missing_nojekyll_fails(self) -> None:
        (self.output / ".nojekyll").unlink()
        with self.assertRaisesRegex(ValueError, "Missing .nojekyll"):
            self.manifest()

    def test_missing_home_navigation_fails(self) -> None:
        self.write("docs/build/html/index.html", "<html>No blog link</html>")
        with self.assertRaisesRegex(ValueError, "Home page does not link"):
            self.manifest()

    def test_empty_blog_fails(self) -> None:
        for path in (self.root / "docs").rglob("*.md"):
            path.unlink()
        with self.assertRaisesRegex(ValueError, "No blog posts"):
            self.manifest()

    def test_live_exact_build_passes(self) -> None:
        expected = self.manifest()
        with patch.object(live, "fetch", side_effect=lambda base, path, rev: (self.output / path).read_bytes()) as fetch:
            live.verify_live("https://example.test/", expected)
        self.assertEqual(fetch.call_count, 6)

    def test_live_old_revision_fails(self) -> None:
        expected = self.manifest()
        with patch.object(live, "fetch", return_value=json.dumps({**expected, "revision": "old"}).encode()):
            with self.assertRaisesRegex(ValueError, "manifest does not match"):
                live.verify_live("https://example.test/", expected)

    def test_live_stale_post_fails_even_with_correct_manifest(self) -> None:
        expected = self.manifest()
        self.write("docs/build/html/blog/new.html", "<html>Old content</html>")
        with patch.object(live, "fetch", side_effect=lambda base, path, rev: (self.output / path).read_bytes()):
            with self.assertRaisesRegex(ValueError, "differs from the validated build"):
                live.verify_live("https://example.test/", expected)

    def test_live_http_failure_exits_nonzero_after_bounded_retries(self) -> None:
        self.manifest()
        args = ["check-blog-live.py", "--url", "https://example.test/", "--manifest", str(self.output / MANIFEST), "--attempts", "2", "--delay", "0"]
        with patch.object(sys, "argv", args), patch.object(live, "fetch", side_effect=HTTPError("url", 404, "Missing", {}, None)) as fetch:
            with self.assertLogs(level="ERROR"), self.assertRaises(SystemExit) as error:
                live.main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(fetch.call_count, 2)

    def test_transient_cdn_delay_recovers(self) -> None:
        self.manifest()
        args = ["check-blog-live.py", "--url", "https://example.test/", "--manifest", str(self.output / MANIFEST), "--attempts", "2", "--delay", "0"]
        with patch.object(sys, "argv", args), patch.object(live, "verify_live", side_effect=[ValueError("stale"), None]) as verify:
            with self.assertLogs(level="ERROR"):
                live.main()
        self.assertEqual(verify.call_count, 2)

    def test_sphinx_automatically_adds_future_and_nested_posts(self) -> None:
        source = self.root / "docs/source"
        (source / "blog").symlink_to("../blog", target_is_directory=True)
        self.write("docs/source/conf.py", "extensions = ['myst_parser', 'sphinx.ext.githubpages']\nmaster_doc = 'index'\n")
        self.write("docs/source/index.rst", "Home\n====\n\n.. toctree::\n\n   blog\n")
        self.write("docs/source/blog.rst", (SCRIPTS.parents[1] / "docs/source/blog.rst").read_text())
        for filename in (None, "future/new-post.md"):
            if filename:
                self.write("docs/blog/" + filename, "# A future post\n\nNew content.\n")
            build = subprocess.run([sys.executable, "-m", "sphinx", "-W", "-b", "html", str(source), str(self.output)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            manifest = self.manifest()
        self.assertIn("blog/future/new-post.html", manifest["files"])


if __name__ == "__main__":
    unittest.main()
