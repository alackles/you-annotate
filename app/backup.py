"""Export a text's annotations as portable JSON, and restore them from that JSON.

The export stands on its own, without this app. It carries each chapter's `plain` text, so
any offset can be checked, and every span also keeps its quote plus a little of the text
around it (`prefix`/`suffix`, like the W3C Web Annotation TextQuoteSelector), so it can
be found again in another copy of the text even if the offsets drift.

Author tokens are never exported. Restored items get the token "", which no browser can
hold (see auth.ISSUED_TOKEN), so only the admin can edit or delete them.
"""

import sqlite3
from datetime import datetime, timezone

from .importer import utf16_len, utf16_slice

FORMAT = "you-annotate/export"
VERSION = 1
CONTEXT = 32  # characters of prefix/suffix kept around each quote
RESTORED_TOKEN = ""
LAYERS = {"vocab", "commentary", "footnote"}

ABOUT = (
    "Annotations on one text, exported from you-annotate. A span names its chapter by 'chapter', "
    "the chapter's 1-based position in 'chapters'. 'start' and 'end' are offsets in UTF-16 code "
    "units (as JavaScript counts) into that chapter's 'plain' text, which is the textContent of "
    "its 'html'; plain[start:end] == quote. 'prefix' and 'suffix' are the text just before and "
    "after the quote, for finding it again in another copy of the text. Layers: 'vocab' and "
    "'commentary' are highlights with comment threads ('replies'); 'footnote' is the text's "
    "editorial apparatus, with voice 'author' (the book's own note) or 'editor'. Each of 'links' "
    "joins an anchor passage (e.g. an outline line) to a destination passage. Timestamps are UTC."
)


def _py_index(s: str, u16: int) -> int:
    """UTF-16 offset -> Python string index."""
    return len(s.encode("utf-16-le")[: 2 * u16].decode("utf-16-le", errors="ignore"))


def _span(ch, start: int, end: int, quote: str) -> dict:
    plain = ch["plain"]
    s, e = _py_index(plain, start), _py_index(plain, end)
    return {"chapter": ch["ord"], "start": start, "end": end, "quote": quote,
            "prefix": plain[max(0, s - CONTEXT):s], "suffix": plain[e:e + CONTEXT]}


# --- Export ----------------------------------------------------------------------------


def export_text(conn: sqlite3.Connection, text) -> dict:
    chapters = {c["id"]: c for c in conn.execute(
        "SELECT id, ord, title, html, plain FROM chapters WHERE text_id = ? ORDER BY ord", (text["id"],)
    )}
    replies: dict[int, list] = {}
    for r in conn.execute(
        """SELECT r.* FROM replies r JOIN annotations a ON a.id = r.annotation_id
           WHERE a.text_id = ? ORDER BY r.id""",
        (text["id"],),
    ):
        replies.setdefault(r["annotation_id"], []).append({
            "body": r["body"], "author": r["author_name"],
            "created_at": r["created_at"], "updated_at": r["updated_at"],
        })

    annotations = []
    for a in conn.execute("SELECT * FROM annotations WHERE text_id = ? ORDER BY id", (text["id"],)):
        item = {"layer": a["layer"],
                **_span(chapters[a["chapter_id"]], a["start_offset"], a["end_offset"], a["quote"]),
                "body": a["body"]}
        if a["layer"] == "footnote":
            item["voice"] = a["voice"]
        item |= {"author": a["author_name"], "created_at": a["created_at"], "updated_at": a["updated_at"]}
        if a["layer"] != "footnote":
            item["replies"] = replies.get(a["id"], [])
        annotations.append(item)

    links = [{
        "anchor": _span(chapters[k["anchor_chapter_id"]], k["anchor_start"], k["anchor_end"], k["anchor_quote"]),
        "dest": _span(chapters[k["dest_chapter_id"]], k["dest_start"], k["dest_end"], k["dest_quote"]),
        "author": k["author_name"],
        "created_at": k["created_at"],
    } for k in conn.execute("SELECT * FROM links WHERE text_id = ? ORDER BY id", (text["id"],))]

    return {
        "format": FORMAT,
        "version": VERSION,
        "about": ABOUT,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "text": {"slug": text["slug"], "title": text["title"]},
        "chapters": [{"ord": c["ord"], "title": c["title"], "plain": c["plain"], "html": c["html"]}
                     for c in chapters.values()],
        "annotations": annotations,
        "links": links,
    }


# --- Restore ---------------------------------------------------------------------------
#
# Each span is placed on the target text's chapter at the same position, or the one with
# the same title if the title there differs, at its old offsets if the quote is still there; otherwise at the one
# place the quote occurs, using prefix/suffix to break ties. Anything that doesn't land on
# exactly one place is reported, never guessed at. Items already present are skipped, so
# restoring the same file twice adds nothing the second time.


def _short(quote: str) -> str:
    return quote if len(quote) <= 40 else f"{quote[:18]}…{quote[-18:]}"


def _occurrences(plain: str, quote: str) -> list[int]:
    hits, i = [], plain.find(quote)
    while i != -1:
        hits.append(i)
        i = plain.find(quote, i + 1)
    return hits


class _Placer:
    def __init__(self, conn, text_id: int, backup: dict):
        rows = conn.execute("SELECT id, ord, title, plain FROM chapters WHERE text_id = ?", (text_id,)).fetchall()
        self.by_ord = {c["ord"]: c for c in rows}
        self.by_title = {c["title"]: c for c in rows}
        self.old_titles = {c["ord"]: c["title"] for c in backup.get("chapters", [])}

    def place(self, span: dict) -> tuple[dict, str] | str:
        """({chapter_id, start, end, quote}, "exact" | "moved"), or a reason it can't be placed."""
        title = self.old_titles.get(span["chapter"])
        ch = self.by_ord.get(span["chapter"])
        if title is not None and (ch is None or ch["title"] != title):
            ch = self.by_title.get(title, ch)
        if ch is None:
            return f"no chapter {title or span['chapter']!r}"
        plain, quote = ch["plain"], span["quote"]
        if not quote:
            return "empty quote"
        start, end = int(span["start"]), int(span["end"])
        if 0 <= start < end <= utf16_len(plain) and utf16_slice(plain, start, end) == quote:
            return {"chapter_id": ch["id"], "start": start, "end": end, "quote": quote}, "exact"
        hits = _occurrences(plain, quote)
        if len(hits) > 1:
            prefix, suffix = span.get("prefix", ""), span.get("suffix", "")
            hits = [i for i in hits if plain[:i].endswith(prefix) and plain[i + len(quote):].startswith(suffix)]
        if len(hits) != 1:
            return f"quote found {len(hits)} times in {ch['title']!r}" if hits else f"quote not found in {ch['title']!r}"
        start = utf16_len(plain[:hits[0]])
        return {"chapter_id": ch["id"], "start": start, "end": start + utf16_len(quote), "quote": quote}, "moved"


def plan_restore(conn: sqlite3.Connection, text, backup: dict) -> dict:
    """What restoring `backup` onto `text` would add, and a report. Raises ValueError,
    KeyError or TypeError if `backup` isn't an export."""
    if backup.get("format") != FORMAT or backup.get("version") != VERSION:
        raise ValueError("not a you-annotate export")
    placer = _Placer(conn, text["id"], backup)
    existing_anns = {tuple(r) for r in conn.execute(
        """SELECT layer, chapter_id, start_offset, end_offset, body, author_name
           FROM annotations WHERE text_id = ?""", (text["id"],))}
    existing_links = {tuple(r) for r in conn.execute(
        """SELECT anchor_chapter_id, anchor_start, anchor_end, dest_chapter_id, dest_start, dest_end,
                  author_name FROM links WHERE text_id = ?""", (text["id"],))}

    counts = {k: 0 for k in ("exact", "moved", "duplicate", "unplaced")}
    report = {"annotations": dict(counts), "links": dict(counts), "replies": 0, "problems": []}
    annotations, links = [], []

    for a in backup.get("annotations", []):
        layer = a["layer"]
        where = placer.place(a) if layer in LAYERS else f"unknown layer {layer!r}"
        if isinstance(where, str):
            report["annotations"]["unplaced"] += 1
            n = len(a.get("replies", []))
            report["problems"].append(f"{layer} {_short(a['quote'])!r} by {a.get('author')}"
                                      f"{f' (+{n} replies)' if n else ''}: {where}")
            continue
        span, how = where
        row = {**span, "layer": layer, "body": a.get("body", ""),
               "voice": a.get("voice", "editor") if layer == "footnote" else "editor",
               "author": a.get("author") or "Unknown",
               "created_at": a.get("created_at"), "updated_at": a.get("updated_at"),
               "replies": [] if layer == "footnote" else a.get("replies", [])}
        key = (layer, span["chapter_id"], span["start"], span["end"], row["body"], row["author"])
        if key in existing_anns:
            report["annotations"]["duplicate"] += 1
            continue
        report["annotations"][how] += 1
        report["replies"] += len(row["replies"])
        annotations.append(row)

    for k in backup.get("links", []):
        ends = {"anchor": placer.place(k["anchor"]), "dest": placer.place(k["dest"])}
        bad = [f"{end} {why}" for end, why in ends.items() if isinstance(why, str)]
        if bad:
            report["links"]["unplaced"] += 1
            report["problems"].append(f"link {_short(k['anchor']['quote'])!r} → "
                                      f"{_short(k['dest']['quote'])!r}: {'; '.join(bad)}")
            continue
        (anchor, how_a), (dest, how_d) = ends["anchor"], ends["dest"]
        row = {"anchor": anchor, "dest": dest, "author": k.get("author") or "Unknown",
               "created_at": k.get("created_at")}
        key = (anchor["chapter_id"], anchor["start"], anchor["end"],
               dest["chapter_id"], dest["start"], dest["end"], row["author"])
        if key in existing_links:
            report["links"]["duplicate"] += 1
            continue
        report["links"]["exact" if how_a == how_d == "exact" else "moved"] += 1
        links.append(row)

    return {"annotations": annotations, "links": links, "report": report}


def apply_restore(conn: sqlite3.Connection, text_id: int, plan: dict) -> None:
    for a in plan["annotations"]:
        cur = conn.execute(
            """INSERT INTO annotations (text_id, chapter_id, layer, start_offset, end_offset, quote,
                                        body, voice, author_name, author_token, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)""",
            (text_id, a["chapter_id"], a["layer"], a["start"], a["end"], a["quote"], a["body"],
             a["voice"], a["author"], RESTORED_TOKEN, a["created_at"], a["updated_at"]),
        )
        conn.executemany(
            """INSERT INTO replies (annotation_id, body, author_name, author_token, created_at, updated_at)
               VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?)""",
            [(cur.lastrowid, r["body"], r.get("author") or "Unknown", RESTORED_TOKEN,
              r.get("created_at"), r.get("updated_at")) for r in a["replies"]],
        )
    for k in plan["links"]:
        a, d = k["anchor"], k["dest"]
        conn.execute(
            """INSERT INTO links (text_id, anchor_chapter_id, anchor_start, anchor_end, anchor_quote,
                                  dest_chapter_id, dest_start, dest_end, dest_quote,
                                  author_name, author_token, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            (text_id, a["chapter_id"], a["start"], a["end"], a["quote"],
             d["chapter_id"], d["start"], d["end"], d["quote"], k["author"], RESTORED_TOKEN, k["created_at"]),
        )
    conn.commit()
