"""Convert the Project Gutenberg HTML of Equiano's Narrative to upload-ready Markdown.

    .venv/bin/python scripts/gutenberg_to_md.py texts/equiano.html \
        --out texts/equiano.md --footnotes texts/equiano-footnotes.json [--chapters 1-3]

Output: a "Front Matter" chapter (title page, epigraph, address to Parliament, list of
subscribers; the Gutenberg contents list and portrait are dropped), then `# Chapter I`…
`# Chapter XII`. Chapter summaries, letters and quotations become blockquotes; verse keeps
its lines and stanzas; <br> line breaks are kept; paragraphs are unwrapped onto one line.

Equiano's own footnotes are part of the book's apparatus, so they're taken *out* of the
text (to be loaded as footnote annotations instead) and written to the JSON file with the
plain text they were attached after.

Written for this one Gutenberg file's markup; other files will need adjusting.
"""

import argparse
import json
import re
from html.parser import HTMLParser

CHAPTER_H2 = re.compile(r'<h2 id="CHAP[^"]*">(.*?)</h2>', re.S)
FRONT = re.compile(r"(<h1>.*?)<hr[^>]*>\s*<h2>CONTENTS</h2>", re.S)

# Sentinels used while a block is being read.
I_ON, I_OFF, FN_ON, FN_OFF, BR = "\x01", "\x02", "\x03", "\x04", "\x05"
ITALIC = re.compile(f"{I_ON}(\\s*)(.*?)(\\s*){I_OFF}", re.S)
ANCHOR = re.compile(f"{FN_ON}(.*?){FN_OFF}")


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")


def finish_block(raw: str, quote: bool = False) -> tuple[str, str, list[tuple[str, str]]]:
    """(markdown, plain, [(footnote label, plain text before its anchor)]) for one block.

    A single <br> becomes a Markdown hard line break; two or more start a new paragraph.
    `quote` prefixes every line with "> ".
    """
    text = re.sub(r"[ \t\r\n\xa0]+", " ", raw)
    text = re.sub(f" ?{BR} ?", BR, text).strip(f" {BR}")

    plain = ITALIC.sub(lambda m: m[1] + m[2] + m[3], text)
    plain = re.sub(r"\\(.)", r"\1", plain)
    plain = re.sub(f"{BR}+", "\n", plain)
    anchors = []
    while (m := ANCHOR.search(plain)) is not None:
        anchors.append((m[1], plain[: m.start()].rstrip()))
        plain = plain[: m.start()] + plain[m.end():]

    markdown = ITALIC.sub(lambda m: f"{m[1]}*{m[2]}*{m[3]}" if m[2] else m[1] + m[3], text)
    markdown = ANCHOR.sub("", markdown)
    paragraphs = []
    for para in re.split(f"{BR}{{2,}}", markdown):
        lines = [protect(line.strip()) for line in para.split(BR) if line.strip()]
        if lines:
            paragraphs.append(lines)
    prefix = "> " if quote else ""
    joiner = f"\n{prefix.rstrip()}\n" if quote else "\n\n"
    markdown = joiner.join("  \n".join(prefix + line for line in lines) for lines in paragraphs)
    return markdown, plain, anchors


def protect(line: str) -> str:
    """Escape line starts that Markdown would read as structure."""
    line = re.sub(r"^(\d+)\. ", r"\1\\. ", line)  # not an ordered list
    return re.sub(r"^([#>+-]) ", r"\\\1 ", line)


class BookParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []          # markdown blocks
        self.footnotes: dict[str, str] = {}
        self.anchors: list[tuple[str, str]] = []
        self.buf: list[str] | None = None    # text of the block being read
        self.heading = False                 # block is a div.h4/h5 heading
        self.verse: list[list[str]] | None = None  # stanzas of lines being read
        self.divs: list[str] = []            # stack of div classes
        self.skipping: str | None = None     # tag whose text we drop (footnote labels, h3)
        self.label: str | None = None        # current footnote's label
        self.in_anchor = False               # inside a footnote reference like [K]

    def inside(self, cls: str) -> bool:
        return any(cls in d.split() for d in self.divs)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "div":
            self.divs.append(cls)
            if cls == "poem":
                self.verse = []
            elif cls == "stanza" and self.verse is not None:
                self.verse.append([])
            elif {"h4", "h5"} & set(cls.split()):
                self.buf, self.heading = [], True
        elif tag in ("p", "h1"):
            self.buf = []
        elif tag == "span" and self.verse is not None and not self.buf:
            self.buf = []
        elif self.buf is None:
            return
        elif tag == "br":
            self.buf.append(BR)
        elif tag == "i":
            self.buf.append(I_ON)
        elif tag == "a" and cls == "fnanchor":
            self.buf.append(FN_ON)
            self.in_anchor = True

        if tag == "span" and cls == "label" or tag == "h3":
            self.skipping = tag

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "div":
            cls = self.divs.pop()
            if cls == "poem":
                stanzas = ["  \n".join(f"> {line}" for line in s) for s in self.verse if s]
                self.blocks.append("\n>\n".join(stanzas))
                self.verse = None
            elif self.heading:
                self.emit(f"## {finish_block(''.join(self.buf))[0]}")
                self.heading = False
        elif tag in ("p", "h1") and self.buf is not None:
            quote = self.inside("blockquot")
            markdown, plain, anchors = finish_block("".join(self.buf), quote=quote)
            self.buf = None
            if self.inside("footnote"):
                self.footnotes[self.label] = plain
            elif markdown:
                self.emit(markdown)
                self.anchors.extend(anchors)
        elif tag == "span" and self.verse is not None and self.buf is not None:
            markdown, _, anchors = finish_block("".join(self.buf))
            self.buf = None
            if markdown:
                self.verse[-1].append(markdown)
                self.anchors.extend(anchors)
        elif self.buf is None:
            pass
        elif tag == "i":
            self.buf.append(I_OFF)
        elif tag == "a" and self.in_anchor:
            self.buf.append(FN_OFF)
            self.in_anchor = False

        if tag == self.skipping:
            self.skipping = None

    def emit(self, block: str):
        self.blocks.append(block)

    def handle_data(self, data):
        if self.skipping == "span" and self.inside("footnote"):
            self.label = data.strip("[]")
            return
        if self.skipping or self.buf is None:
            return
        self.buf.append(data.strip("[]") if self.in_anchor else escape(data))


def parse(fragment: str) -> BookParser:
    parser = BookParser()
    parser.feed(fragment)
    parser.close()
    return parser


def convert(html: str, first: int | None, last: int | None):
    html = re.sub(r"</p>([.,;:])", r"\1</p>", html)  # stray punctuation after a paragraph
    heads = list(CHAPTER_H2.finditer(html))
    first, last = first or 1, last or len(heads)
    sections = []
    if first == 1:
        sections.append(("Front Matter", FRONT.search(html)[1]))
    for i in range(first - 1, last):
        end = heads[i + 1].start() if i + 1 < len(heads) else html.index("Transcriber’s Notes")
        numeral = re.search(r"([IVXLC]+)\.?\s*$", heads[i][1].strip())[1]
        sections.append((f"Chapter {numeral}", html[heads[i].end():end]))

    chapters, footnotes = [], []
    for title, fragment in sections:
        parser = parse(fragment)
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
    ap.add_argument("--chapters", help="e.g. 1-3 (default: everything, with front matter)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--footnotes", required=True)
    args = ap.parse_args()
    first, last = map(int, args.chapters.split("-")) if args.chapters else (None, None)
    markdown, footnotes = convert(open(args.html, encoding="utf-8").read(), first, last)
    open(args.out, "w", encoding="utf-8").write(markdown)
    json.dump(footnotes, open(args.footnotes, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    chapters = len(re.findall(r"^# ", markdown, re.M))
    print(f"{args.out}: {chapters} chapters; {args.footnotes}: {len(footnotes)} footnotes")


if __name__ == "__main__":
    main()
