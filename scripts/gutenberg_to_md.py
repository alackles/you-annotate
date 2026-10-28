"""Convert chapters of the Project Gutenberg HTML of Equiano's Narrative to upload-ready Markdown.

    .venv/bin/python scripts/gutenberg_to_md.py texts/equiano.html --chapters 1-3 \
        --out texts/equiano.md --footnotes texts/equiano-footnotes.json

Each chapter becomes `# Chapter N`, its summary becomes an italic blockquote, verse becomes
a blockquote with line breaks, and paragraphs are unwrapped onto one line. Equiano's own
footnotes are part of the book's apparatus, so they're taken *out* of the text (to be loaded
as footnote annotations instead) and written to the JSON file with enough context to
find the spot they were attached to.

Written for this one Gutenberg file's markup; other files will need adjusting.
"""

import argparse
import json
import re
from html.parser import HTMLParser

CHAPTER_H2 = re.compile(r'<h2 id="CHAP[^"]*">(.*?)</h2>', re.S)
ITALIC = re.compile(r"\x01(\s*)(.*?)(\s*)\x02", re.S)
ANCHOR = re.compile(r"\x03(.*?)\x04")


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")


def finish_block(raw: str) -> tuple[str, str, list[tuple[str, str]]]:
    """(markdown, plain, [(footnote label, plain text before the anchor)]) for one block."""
    text = re.sub(r"[ \t\r\n]+", " ", raw).strip()
    anchors = []
    plain = ITALIC.sub(lambda m: m[1] + m[2] + m[3], text)
    plain = re.sub(r"\\(.)", r"\1", plain)
    while (m := ANCHOR.search(plain)) is not None:
        anchors.append((m[1], plain[: m.start()].rstrip()))
        plain = plain[: m.start()] + plain[m.end():]
    markdown = ITALIC.sub(lambda m: f"{m[1]}*{m[2]}*{m[3]}" if m[2] else m[1] + m[3], text)
    markdown = ANCHOR.sub("", markdown)
    markdown = re.sub(r"^(\d+)\. ", r"\1\\. ", markdown)  # not an ordered list
    markdown = re.sub(r"^([#>+-]) ", r"\\\1 ", markdown)
    return markdown, plain, anchors


class ChapterParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []        # markdown blocks
        self.footnotes: dict[str, str] = {}
        self.anchors: list[tuple[str, str]] = []
        self.buf: list[str] | None = None  # text of the paragraph being read
        self.lines: list[str] | None = None  # verse lines being read
        self.context: list[str] = []       # stack of div classes
        self.skip = 0                      # inside an element whose text we drop
        self.label: str | None = None      # current footnote's label
        self.in_anchor = False             # inside a footnote reference like [K]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            self.context.append(a.get("class", ""))
            if a.get("class") == "poem":
                self.lines = []
        elif tag == "p":
            self.buf = []
        elif tag == "span" and self.lines is not None:
            self.buf = []
        elif tag == "i" and self.buf is not None:
            self.buf.append("\x01")
        elif tag == "a" and a.get("class") == "fnanchor":
            self.buf.append("\x03")
            self.in_anchor = True
        elif tag == "span" and a.get("class") == "label":
            self.skip += 1
        elif tag == "h3":
            self.skip += 1

    def handle_endtag(self, tag):
        if tag == "div":
            cls = self.context.pop()
            if cls == "poem":
                self.blocks.append("> " + "  \n> ".join(self.lines))
                self.lines = None
        elif tag == "p" and self.buf is not None:
            markdown, plain, anchors = finish_block("".join(self.buf))
            self.buf = None
            if "footnote" in self.context:
                self.footnotes[self.label] = plain
            elif "blockquot" in self.context:
                self.blocks.append(f"> {markdown}")
            elif markdown:
                self.blocks.append(markdown)
                self.anchors.extend(anchors)
        elif tag == "span" and self.lines is not None and self.buf is not None:
            self.lines.append(finish_block("".join(self.buf))[0])
            self.buf = None
        elif tag == "i" and self.buf is not None:
            self.buf.append("\x02")
        elif tag == "a" and self.in_anchor:
            self.buf.append("\x04")
            self.in_anchor = False
        elif tag == "span" and self.skip:
            self.skip -= 1
        elif tag == "h3":
            self.skip -= 1

    def handle_data(self, data):
        if "footnote" in self.context and self.skip and data.startswith("["):
            self.label = data.strip("[]")
            return
        if self.skip or self.buf is None:
            return
        self.buf.append(data.strip("[]") if self.in_anchor else escape(data))


def convert(html: str, first: int, last: int):
    heads = list(CHAPTER_H2.finditer(html))
    chapters, footnotes = [], []
    for i in range(first - 1, last):
        start = heads[i].end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(html)
        numeral = re.search(r"([IVXLC]+)\.?\s*$", heads[i][1].strip())[1]
        title = f"Chapter {numeral}"
        parser = ChapterParser()
        parser.feed(html[start:end])
        chapters.append(f"# {title}\n\n" + "\n\n".join(parser.blocks))
        for label, before in parser.anchors:
            footnotes.append({
                "chapter": title,
                "label": label,
                "attach_after": before[-80:],  # plain text just before the anchor
                "text": parser.footnotes[label],
            })
    return "\n\n".join(chapters) + "\n", footnotes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("html")
    ap.add_argument("--chapters", default="1-3", help="e.g. 1-3")
    ap.add_argument("--out", required=True)
    ap.add_argument("--footnotes", required=True)
    args = ap.parse_args()
    first, last = map(int, args.chapters.split("-"))
    markdown, footnotes = convert(open(args.html, encoding="utf-8").read(), first, last)
    open(args.out, "w", encoding="utf-8").write(markdown)
    json.dump(footnotes, open(args.footnotes, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"{args.out}: {markdown.count(chr(10) + '# ') + markdown.startswith('# ')} chapters; "
          f"{args.footnotes}: {len(footnotes)} footnotes")


if __name__ == "__main__":
    main()
