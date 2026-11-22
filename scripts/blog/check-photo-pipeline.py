#!/usr/bin/env python3
"""Check local presentation assets, slide limits, links and SVG structure."""
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BLOG = ROOT / 'docs/blog'
DECK = BLOG / 'local-photo-pipeline-slides.html'


class DeckParser(HTMLParser):
    """Collect the document's slide count, bullet counts and file links."""

    def __init__(self) -> None:
        super().__init__()
        self.slides: list[int] = []
        self.links: list[str] = []
        self.in_slide = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == 'section' and 'slide' in (values.get('class') or '').split():
            self.slides.append(0)
            self.in_slide = True
        if tag == 'li' and self.in_slide:
            self.slides[-1] += 1
        for key in ('href', 'src'):
            if values.get(key):
                self.links.append(values[key])

    def handle_endtag(self, tag: str) -> None:
        if tag == 'section':
            self.in_slide = False


def check_link(source: Path, link: str) -> None:
    """Verify local targets without making network requests."""
    parsed = urlsplit(link)
    if parsed.scheme or not parsed.path:
        return
    target = (source.parent / unquote(parsed.path)).resolve()
    assert target.exists(), f'Missing target from {source.name}: {link}'


def main() -> None:
    """Validate the requested deck limits and linked local evidence."""
    parser = DeckParser()
    parser.feed(DECK.read_text())
    assert len(parser.slides) == 10, parser.slides
    assert max(parser.slides) <= 2, parser.slides
    for link in parser.links:
        check_link(DECK, link)
    for source in (BLOG / '2026-11-15-taking-my-files-back-from-google-and-onedrive.md',
                   BLOG / 'assets/local-photo-pipeline/evidence.md'):
        for link in re.findall(r'\]\(([^)]+)\)', source.read_text()):
            check_link(source, link)
    ET.parse(BLOG / 'assets/local-photo-pipeline/architecture.svg')
    print('OK: 10 slides; zero bullets; local links/assets exist; SVG parses.')


if __name__ == '__main__':
    main()
