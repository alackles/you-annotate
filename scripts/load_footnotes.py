"""Load footnotes onto the uploaded Equiano text: Equiano's own notes plus the explanatory
notes index (texts/equiano_files/equiano_explanatory_notes_index.md).

    .venv/bin/python scripts/load_footnotes.py                 # dry run against the live site
    .venv/bin/python scripts/load_footnotes.py --apply         # actually add them
    .venv/bin/python scripts/load_footnotes.py --base http://localhost:8000 --apply

Posts through the normal API as admin (password from $ADMIN_PASSWORD or .env), so the
server re-checks every anchor. Safe to re-run: a footnote already present at the same
place with the same text is skipped.

Placement:
- Equiano's notes attach to the word just before where his [A], [B]… mark stood.
- Index entries are matched in page order through the whole book (the index's chapter
  headings aren't relied on). "start … end" lemmas cover the whole span from start to end.
  An entry not found in the main text but found in one of Equiano's notes (e.g. "Voyage")
  is appended to that note instead.
"""

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import httpx
from dotenv import dotenv_values

REPO = Path(__file__).resolve().parent.parent
EQUIANO_NOTES = REPO / "texts" / "equiano-footnotes.json"
INDEX = REPO / "texts" / "equiano_files" / "equiano_explanatory_notes_index.md"

# Index lemmas spelled differently from the Gutenberg text.
ALIASES = {"plaintains": "plantains", "red-wood": "redwood", "Gustavus Vasa": "Gustavus Vassa"}
MAX_GAP = 700        # longest stretch allowed between the two ends of a "start … end" lemma
MAX_LEAP = 60_000    # don't jump further ahead than this looking for the next entry
SEP = "\x00"         # between chapters in the concatenated book, so no match spans two


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(html: str) -> str:
    """Same rule as app/importer.py: the chapter's textContent."""
    p = _Text()
    p.feed(html)
    p.close()
    return "".join(p.parts)


def utf16(s: str, i: int) -> int:
    """Python index -> UTF-16 offset, which is what the server and browser count."""
    return len(s[:i].encode("utf-16-le")) // 2


def lemma_pattern(lemma: str) -> re.Pattern:
    for wrong, right in ALIASES.items():
        lemma = lemma.replace(wrong, right)
    parts = [re.sub("—+", "—+", re.escape(p.strip())) for p in lemma.split("…")]
    pattern = f"[^{SEP}]{{0,{MAX_GAP}}}?".join(parts)
    if re.match(r"\w", lemma.strip()[0]):
        pattern = r"\b" + pattern
    if re.match(r"\w", lemma.strip()[-1]):
        pattern += r"\b"
    return re.compile(pattern)


def read_index() -> list[dict]:
    entries = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        m = re.match(r'- \*\*(\d+), "(.+?)"\*\*: (.*)', line)
        if m:
            body = re.sub(r"\*([^*]+)\*", r"\1", m[3]).strip()  # drop Markdown italics
            entries.append({"page": int(m[1]), "lemma": m[2], "body": body})
    return entries


def plan(chapters: list[dict]) -> tuple[list[dict], list[str]]:
    """[(chapter_id, start, end, quote, body)] in UTF-16 offsets, plus problems found."""
    notes, problems = [], []
    by_title = {c["title"]: c for c in chapters}

    equiano = []
    for n in json.loads(EQUIANO_NOTES.read_text(encoding="utf-8")):
        ch = by_title[n["chapter"]]
        context = n["attach_after"][-40:]
        if ch["plain"].count(context) != 1:
            problems.append(f"Equiano [{n['label']}]: context found {ch['plain'].count(context)} times")
            continue
        anchor = ch["plain"].index(context) + len(context)
        word = re.search(r"(\w[\w'’-]*)\W*$", ch["plain"][:anchor])
        equiano.append({"ch": ch, "start": word.start(1), "end": word.end(1), "label": n["label"],
                        "body": f"Equiano's note: {n['text']}"})

    # Index entries annotate the narrative, so each chapter's opening summary is masked out
    # (same length, so offsets don't shift); otherwise "Brimstone-Hill … Montserrat" would
    # land in Chapter VI's summary instead of the passage.
    book, offsets = "", []
    for ch in chapters:
        offsets.append((len(book), ch))
        plain = ch["plain"]
        if ch["title"] != "Front Matter":
            summary_end = re.search(r"\S.*?\n", plain, re.S).end()
            plain = SEP * summary_end + plain[summary_end:]
        book += plain + SEP
    pos = next(o for o, ch in offsets if ch["title"] == "Chapter I")
    for e in read_index():
        m = lemma_pattern(e["lemma"]).search(book, pos)
        if m and m.start() - pos <= MAX_LEAP:
            pos = m.start() + 1
            base, ch = [(o, c) for o, c in offsets if o <= m.start()][-1]
            notes.append({"ch": ch, "start": m.start() - base, "end": m.end() - base,
                          "label": f"p.{e['page']}", "body": e["body"]})
            continue
        host = next((n for n in equiano if lemma_pattern(e["lemma"]).search(n["body"])), None)
        if host:
            host["body"] += f" [Editor: {e['body']}]"
            host["label"] += f" + p.{e['page']}"
        else:
            problems.append(f"index p.{e['page']} {e['lemma']!r}: not found")

    out = []
    for n in equiano + notes:
        plain = n["ch"]["plain"]
        out.append({
            "label": n["label"],
            "chapter": n["ch"]["title"],
            "chapter_id": n["ch"]["id"],
            "start": utf16(plain, n["start"]),
            "end": utf16(plain, n["end"]),
            "quote": plain[n["start"]:n["end"]],
            "body": n["body"],
        })
    return out, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="https://you-annotate.fly.dev")
    ap.add_argument("--slug", default="equiano")
    ap.add_argument("--apply", action="store_true", help="add the footnotes (default: dry run)")
    args = ap.parse_args()

    with httpx.Client(base_url=args.base, timeout=30) as c:
        info = c.get(f"/api/texts/{args.slug}").raise_for_status().json()
        chapters = []
        for meta in info["chapters"]:
            html = c.get(f"/api/texts/{args.slug}/chapters/{meta['id']}").raise_for_status().json()["html"]
            chapters.append({**meta, "plain": plain_text(html)})
        footnotes, problems = plan(chapters)

        existing = {
            (a["chapter_id"], a["start"], a["end"], a["body"])
            for a in c.get(f"/api/texts/{args.slug}/annotations").json()["annotations"]
            if a["layer"] == "footnote"
        }
        todo = [f for f in footnotes if (f["chapter_id"], f["start"], f["end"], f["body"]) not in existing]

        for f in footnotes:
            quote = f["quote"] if len(f["quote"]) <= 40 else f"{f['quote'][:18]}…{f['quote'][-18:]}"
            mark = "  " if f in todo else "= "
            print(f"{mark}{f['label']:<14} {f['chapter']:<12} {quote!r:<44} {f['body'][:60]}")
        print(f"\n{len(footnotes)} footnotes planned, {len(footnotes) - len(todo)} already present (=), "
              f"{len(todo)} to add.")
        for p in problems:
            print("PROBLEM:", p)

        if not args.apply:
            print("Dry run; nothing changed. Re-run with --apply to add them.")
            return
        password = os.environ.get("ADMIN_PASSWORD") or dotenv_values(REPO / ".env").get("ADMIN_PASSWORD")
        c.post("/api/admin/login", json={"password": password}).raise_for_status()
        failed = 0
        for f in todo:
            payload = {k: f[k] for k in ("chapter_id", "start", "end", "quote", "body")}
            r = c.post(f"/api/texts/{args.slug}/annotations", json={**payload, "layer": "footnote"})
            if r.status_code != 200:
                failed += 1
                print(f"FAILED {f['label']}: {r.status_code} {r.text}")
        c.post("/api/admin/logout")
        print(f"Added {len(todo) - failed}, failed {failed}.")


if __name__ == "__main__":
    main()
