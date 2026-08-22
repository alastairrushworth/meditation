#!/usr/bin/env python3
"""Post-build checks on the generated site.

Run after generate.py. Catches the failure modes that are invisible in a diff:
unbalanced markup, internal links pointing at pages that were never written,
sitemap entries with no file behind them, and structured data that will not
parse. Exits non-zero so CI fails rather than publishing a broken site.
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from render import BASE_PATH

VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
                 "link", "meta", "param", "source", "track", "wbr"}
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class TagBalance(HTMLParser):
    """Minimal well-formedness check: every non-void element is closed once."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID_ELEMENTS:
            return
        if not self.stack:
            self.errors.append(f"stray </{tag}>")
        elif self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append(f"unclosed <{self.stack.pop()}>")
            self.stack.pop()
        else:
            self.errors.append(f"stray </{tag}>")

    def problems(self):
        return self.errors + [f"unclosed <{tag}>" for tag in self.stack]


def target_for(url_path: str) -> Path:
    """Filesystem path a root-relative site URL should resolve to."""
    relative = url_path[len(BASE_PATH):] if url_path.startswith(BASE_PATH) \
        else url_path.lstrip("/")
    relative = unquote(relative.split("#")[0].split("?")[0])
    if relative in ("", "/") or relative.endswith("/"):
        return config.SITE_ROOT / relative / "index.html"
    return config.SITE_ROOT / relative


def site_pages() -> list:
    return sorted(p for p in config.SITE_ROOT.rglob("*.html")
                  if "scripts" not in p.parts and "assets" not in p.parts
                  and ".git" not in p.parts)


def main() -> int:
    failures = []
    pages = site_pages()
    if len(pages) < 10:
        failures.append(f"only {len(pages)} pages were generated")

    for page in pages:
        html = page.read_text(encoding="utf-8")
        name = page.relative_to(config.SITE_ROOT)

        balance = TagBalance()
        balance.feed(html)
        for problem in balance.problems()[:3]:
            failures.append(f"{name}: {problem}")

        for block in re.findall(
                r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try:
                json.loads(block.replace("<\\/", "</"))
            except ValueError as exc:
                failures.append(f"{name}: invalid JSON-LD ({exc})")

        if "<title>" not in html:
            failures.append(f"{name}: no <title>")
        if 'rel="canonical"' not in html:
            failures.append(f"{name}: no canonical link")

        for url in re.findall(r'(?:href|src)="([^"]+)"', html):
            if url.startswith(("http", "//", "mailto:", "#", "data:")):
                continue
            if not target_for(url).exists():
                failures.append(f"{name}: broken internal link {url}")

    sitemap = ElementTree.parse(config.SITE_ROOT / "sitemap.xml").getroot()
    locations = [element.text for element in sitemap.findall(".//s:loc", SITEMAP_NS)]
    if len(locations) != len(set(locations)):
        failures.append("sitemap contains duplicate URLs")
    for location in locations:
        if not target_for(urlsplit(location).path).exists():
            failures.append(f"sitemap lists {location} but no file was written")

    feed = ElementTree.parse(config.SITE_ROOT / "feed.xml").getroot()
    if not feed.findall(".//item"):
        failures.append("feed.xml has no items")

    index = json.loads((config.SITE_ROOT / "search-index.json").read_text("utf-8"))
    if index["count"] < 1:
        failures.append("search index is empty")

    unique = {failure for failure in failures}
    print(f"Checked {len(pages)} pages, {len(locations)} sitemap URLs, "
          f"{index['count']} indexed meditations.")
    if unique:
        print(f"\n{len(unique)} problem(s):")
        for failure in sorted(unique)[:40]:
            print(f"  - {failure}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
