"""Turn an uploaded Markdown (or plain text) file into chapters.

Each top-level `# Heading` starts a chapter. Anything before the first heading becomes a
"Front matter" chapter if it has content.

Annotations are anchored by character offsets into each chapter's `plain` text, which must
equal what the browser's `textContent` returns for the chapter HTML. Browsers count string
positions in UTF-16 code units, so offsets here do too (see `utf16_slice`).
"""

import re
from html.parser import HTMLParser

import markdown

HEADING = re.compile(r"^#[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")


def split_chapters(source: str) -> list[tuple[str, str]]:
    """Return [(title, markdown_body)], in order."""
    chapters: list[tuple[str, str]] = []
    title: str | None = None
    lines: list[str] = []
    for line in source.lstrip("﻿").splitlines():
        match = HEADING.match(line)
        if not match:
            lines.append(line)
            continue
        _append(chapters, title, lines)
        title, lines = match.group(1), []
    _append(chapters, title, lines)
    return chapters


def _append(chapters, title, lines):
    body = "\n".join(lines).strip()
    if title is not None or body:
        chapters.append((title or "Front matter", body))


class _TextCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(html: str) -> str:
    """The DOM textContent of `html`: every text node, entities decoded, no comments."""
    collector = _TextCollector()
    collector.feed(html)
    collector.close()
    return "".join(collector.parts)


def build_chapters(source: str) -> list[dict]:
    chapters = []
    for ord_, (title, body) in enumerate(split_chapters(source), start=1):
        html = markdown.markdown(body)
        chapters.append({"ord": ord_, "title": title, "html": html, "plain": plain_text(html)})
    return chapters


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def utf16_slice(s: str, start: int, end: int) -> str | None:
    """s[start:end] in UTF-16 units, or None if a bound splits a surrogate pair."""
    try:
        return s.encode("utf-16-le")[2 * start : 2 * end].decode("utf-16-le")
    except UnicodeDecodeError:
        return None
