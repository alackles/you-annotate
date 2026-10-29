"""JSON API."""

import re
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import auth, db, events
from .db import get_conn
from .importer import build_chapters, utf16_len, utf16_slice

router = APIRouter(prefix="/api")

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def get_text(conn: sqlite3.Connection, slug: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM texts WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such text")
    return row


# --- Reading ---------------------------------------------------------------------------


@router.get("/texts")
async def list_texts(conn=Depends(get_conn)):
    rows = conn.execute("SELECT slug, title FROM texts ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


@router.get("/texts/{slug}")
async def text_info(slug: str, request: Request, conn=Depends(get_conn)):
    text = get_text(conn, slug)
    chapters = conn.execute(
        "SELECT id, ord, title FROM chapters WHERE text_id = ? ORDER BY ord", (text["id"],)
    ).fetchall()
    ident = auth.identity(request, conn, text["id"])
    return {
        "id": text["id"],
        "slug": text["slug"],
        "title": text["title"],
        "chapters": [dict(c) for c in chapters],
        "me": {
            "name": ident["name"] if ident else None,
            "can_write": ident is not None,
            "admin": bool(ident and ident["admin"]),
        },
    }


@router.get("/texts/{slug}/chapters/{chapter_id}")
async def chapter(slug: str, chapter_id: int, conn=Depends(get_conn)):
    text = get_text(conn, slug)
    row = conn.execute(
        "SELECT id, ord, title, html FROM chapters WHERE id = ? AND text_id = ?",
        (chapter_id, text["id"]),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "No such chapter")
    return dict(row)


# --- Joining ---------------------------------------------------------------------------


class Join(BaseModel):
    name: str
    passcode: str


@router.post("/texts/{slug}/join")
async def join(slug: str, body: Join, request: Request, response: Response, conn=Depends(get_conn)):
    text = get_text(conn, slug)
    name = " ".join(body.name.split())[:60]
    if not name:
        raise HTTPException(400, "Enter your name")
    if not auth.passcode_matches(body.passcode, text["passcode"]):
        raise HTTPException(403, "Wrong passcode")
    token = request.cookies.get(auth.TOKEN_COOKIE)
    if not auth.is_issued_token(token):
        token = auth.new_token()
    conn.execute(
        """INSERT INTO participants (token, text_id, name) VALUES (?, ?, ?)
           ON CONFLICT (token, text_id) DO UPDATE SET name = excluded.name""",
        (token, text["id"], name),
    )
    conn.commit()
    response.set_cookie(
        auth.TOKEN_COOKIE,
        token,
        max_age=auth.TOKEN_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return {"name": name, "can_write": True, "admin": False}


# --- Annotations -----------------------------------------------------------------------
#
# A span is (chapter, start, end, quote) with offsets in UTF-16 units into chapter.plain.
# Every write re-checks the quote against the stored text, so a bad anchor can't be saved.


class Span(BaseModel):
    chapter_id: int
    start: int
    end: int
    quote: str


def check_span(conn: sqlite3.Connection, text_id: int, span: Span) -> None:
    ch = conn.execute(
        "SELECT plain FROM chapters WHERE id = ? AND text_id = ?", (span.chapter_id, text_id)
    ).fetchone()
    if ch is None:
        raise HTTPException(422, "No such chapter in this text")
    in_bounds = 0 <= span.start < span.end <= utf16_len(ch["plain"])
    if not in_bounds or utf16_slice(ch["plain"], span.start, span.end) != span.quote:
        raise HTTPException(422, "Selection doesn't match the text")


def reply_json(row, ident) -> dict:
    return {
        "id": row["id"],
        "body": row["body"],
        "author_name": row["author_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "can_edit": auth.can_modify(ident, row),
    }


def annotation_json(row, replies, ident) -> dict:
    return {
        "id": row["id"],
        "chapter_id": row["chapter_id"],
        "layer": row["layer"],
        "start": row["start_offset"],
        "end": row["end_offset"],
        "quote": row["quote"],
        "body": row["body"],
        "voice": row["voice"],
        "author_name": row["author_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "can_edit": auth.can_modify(ident, row),
        "replies": [reply_json(r, ident) for r in replies],
    }


def link_json(row, ident) -> dict:
    return {
        "id": row["id"],
        "anchor": {
            "chapter_id": row["anchor_chapter_id"],
            "start": row["anchor_start"],
            "end": row["anchor_end"],
            "quote": row["anchor_quote"],
        },
        "dest": {
            "chapter_id": row["dest_chapter_id"],
            "start": row["dest_start"],
            "end": row["dest_end"],
            "quote": row["dest_quote"],
        },
        "author_name": row["author_name"],
        "created_at": row["created_at"],
        "can_edit": auth.can_modify(ident, row),
    }


@router.get("/texts/{slug}/annotations")
async def list_annotations(slug: str, request: Request, conn=Depends(get_conn)):
    """Everything for the whole text in one go; author tokens never leave the server."""
    text = get_text(conn, slug)
    ident = auth.identity(request, conn, text["id"])
    replies: dict[int, list] = {}
    for r in conn.execute(
        """SELECT r.* FROM replies r JOIN annotations a ON a.id = r.annotation_id
           WHERE a.text_id = ? ORDER BY r.id""",
        (text["id"],),
    ):
        replies.setdefault(r["annotation_id"], []).append(r)
    annotations = conn.execute(
        "SELECT * FROM annotations WHERE text_id = ? ORDER BY id", (text["id"],)
    ).fetchall()
    links = conn.execute("SELECT * FROM links WHERE text_id = ? ORDER BY id", (text["id"],)).fetchall()
    return {
        "annotations": [annotation_json(a, replies.get(a["id"], []), ident) for a in annotations],
        "links": [link_json(link, ident) for link in links],
    }


@router.get("/texts/{slug}/events")
async def live_events(slug: str, request: Request):
    # No get_conn dependency: it would hold a DB connection open for the stream's lifetime.
    conn = db.connect()
    try:
        text = get_text(conn, slug)
    finally:
        conn.close()
    return StreamingResponse(
        events.stream(request, text["id"]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


Voice = Literal["author", "editor"]


class NewAnnotation(Span):
    layer: Literal["vocab", "commentary", "footnote"]
    body: str = ""
    voice: Voice = "editor"  # footnotes only: the book's own note, or an editor's


def check_body(layer: str, body: str) -> str:
    body = body.strip()
    # A bare vocab highlight is a question in itself ("what does this word mean?").
    if not body and layer != "vocab":
        raise HTTPException(422, "Add a comment")
    return body


@router.post("/texts/{slug}/annotations")
async def create_annotation(slug: str, body: NewAnnotation, request: Request, conn=Depends(get_conn)):
    text = get_text(conn, slug)
    ident = auth.require_identity(request, conn, text["id"])
    if body.layer == "footnote" and not ident["admin"]:
        raise HTTPException(403, "Only the admin can add footnotes")
    check_span(conn, text["id"], body)
    comment = check_body(body.layer, body.body)
    voice = body.voice if body.layer == "footnote" else "editor"
    cur = conn.execute(
        """INSERT INTO annotations (text_id, chapter_id, layer, start_offset, end_offset, quote,
                                    body, voice, author_name, author_token)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (text["id"], body.chapter_id, body.layer, body.start, body.end, body.quote, comment,
         voice, ident["name"], ident["token"]),
    )
    conn.commit()
    events.publish(text["id"])
    return {"id": cur.lastrowid}


def get_owned(conn, request, table: str, item_id: int, text_id_sql: str):
    """Fetch a row and the requester's identity; 403 unless they may modify it."""
    row = conn.execute(
        f"SELECT x.*, {text_id_sql} AS owning_text_id FROM {table} x WHERE x.id = ?", (item_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Not found")
    ident = auth.identity(request, conn, row["owning_text_id"])
    if not auth.can_modify(ident, row):
        raise HTTPException(403, "You can only change your own annotations")
    return row


ANNOTATION_TEXT = "x.text_id"
REPLY_TEXT = "(SELECT a.text_id FROM annotations a WHERE a.id = x.annotation_id)"


class Body(BaseModel):
    body: str


class AnnotationEdit(Body):
    voice: Voice | None = None


@router.patch("/annotations/{ann_id}")
async def edit_annotation(ann_id: int, body: AnnotationEdit, request: Request, conn=Depends(get_conn)):
    row = get_owned(conn, request, "annotations", ann_id, ANNOTATION_TEXT)
    comment = check_body(row["layer"], body.body)
    if body.voice is not None and row["layer"] != "footnote":
        raise HTTPException(422, "Only footnotes have a voice")
    conn.execute(
        "UPDATE annotations SET body = ?, voice = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (comment, body.voice or row["voice"], ann_id),
    )
    conn.commit()
    events.publish(row["owning_text_id"])
    return {"ok": True}


@router.delete("/annotations/{ann_id}")
async def delete_annotation(ann_id: int, request: Request, conn=Depends(get_conn)):
    row = get_owned(conn, request, "annotations", ann_id, ANNOTATION_TEXT)
    conn.execute("DELETE FROM annotations WHERE id = ?", (ann_id,))
    conn.commit()
    events.publish(row["owning_text_id"])
    return {"ok": True}


# --- Replies ---------------------------------------------------------------------------


@router.post("/annotations/{ann_id}/replies")
async def create_reply(ann_id: int, body: Body, request: Request, conn=Depends(get_conn)):
    ann = conn.execute("SELECT * FROM annotations WHERE id = ?", (ann_id,)).fetchone()
    if ann is None:
        raise HTTPException(404, "Not found")
    ident = auth.require_identity(request, conn, ann["text_id"])
    if ann["layer"] == "footnote":
        raise HTTPException(400, "Footnotes don't have comment threads")
    text = body.body.strip()
    if not text:
        raise HTTPException(422, "Reply is empty")
    cur = conn.execute(
        "INSERT INTO replies (annotation_id, body, author_name, author_token) VALUES (?, ?, ?, ?)",
        (ann_id, text, ident["name"], ident["token"]),
    )
    conn.commit()
    events.publish(ann["text_id"])
    return {"id": cur.lastrowid}


@router.patch("/replies/{reply_id}")
async def edit_reply(reply_id: int, body: Body, request: Request, conn=Depends(get_conn)):
    row = get_owned(conn, request, "replies", reply_id, REPLY_TEXT)
    text = body.body.strip()
    if not text:
        raise HTTPException(422, "Reply is empty")
    conn.execute(
        "UPDATE replies SET body = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (text, reply_id)
    )
    conn.commit()
    events.publish(row["owning_text_id"])
    return {"ok": True}


@router.delete("/replies/{reply_id}")
async def delete_reply(reply_id: int, request: Request, conn=Depends(get_conn)):
    row = get_owned(conn, request, "replies", reply_id, REPLY_TEXT)
    conn.execute("DELETE FROM replies WHERE id = ?", (reply_id,))
    conn.commit()
    events.publish(row["owning_text_id"])
    return {"ok": True}


# --- Structural links ------------------------------------------------------------------


class NewLink(BaseModel):
    anchor: Span
    dest: Span


@router.post("/texts/{slug}/links")
async def create_link(slug: str, body: NewLink, request: Request, conn=Depends(get_conn)):
    text = get_text(conn, slug)
    ident = auth.require_identity(request, conn, text["id"])
    check_span(conn, text["id"], body.anchor)
    check_span(conn, text["id"], body.dest)
    a, d = body.anchor, body.dest
    cur = conn.execute(
        """INSERT INTO links (text_id, anchor_chapter_id, anchor_start, anchor_end, anchor_quote,
                              dest_chapter_id, dest_start, dest_end, dest_quote,
                              author_name, author_token)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (text["id"], a.chapter_id, a.start, a.end, a.quote, d.chapter_id, d.start, d.end, d.quote,
         ident["name"], ident["token"]),
    )
    conn.commit()
    events.publish(text["id"])
    return {"id": cur.lastrowid}


@router.delete("/links/{link_id}")
async def delete_link(link_id: int, request: Request, conn=Depends(get_conn)):
    row = get_owned(conn, request, "links", link_id, "x.text_id")
    conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
    conn.commit()
    events.publish(row["owning_text_id"])
    return {"ok": True}


# --- Admin -----------------------------------------------------------------------------


class Login(BaseModel):
    password: str


@router.post("/admin/login")
async def admin_login(body: Login, request: Request):
    if not auth.check_admin_password(body.password):
        raise HTTPException(403, "Wrong password")
    request.session["admin"] = True
    return {"admin": True}


@router.post("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return {"admin": False}


@router.get("/admin/me")
async def admin_me(request: Request):
    return {"admin": auth.is_admin(request), "name": auth.admin_name()}


@router.get("/admin/texts")
async def admin_texts(request: Request, conn=Depends(get_conn)):
    auth.require_admin(request)
    rows = conn.execute(
        """SELECT t.slug, t.title, t.passcode, t.created_at,
                  (SELECT COUNT(*) FROM chapters c WHERE c.text_id = t.id) AS chapters,
                  (SELECT COUNT(*) FROM annotations a WHERE a.text_id = t.id)
                + (SELECT COUNT(*) FROM links l WHERE l.text_id = t.id) AS annotations
           FROM texts t ORDER BY t.created_at"""
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/admin/texts")
async def upload_text(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    slug: str = Form(...),
    passcode: str = Form(...),
    conn=Depends(get_conn),
):
    auth.require_admin(request)
    slug, title, passcode = slug.strip().lower(), title.strip(), passcode.strip()
    if not SLUG.match(slug):
        raise HTTPException(400, "Slug must be lowercase letters, digits and dashes")
    if not title or not passcode:
        raise HTTPException(400, "Title and passcode are required")
    try:
        source = (await file.read()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 text (Markdown or plain text)")
    chapters = build_chapters(source)
    if not chapters:
        raise HTTPException(400, "File is empty")
    try:
        cur = conn.execute(
            "INSERT INTO texts (slug, title, passcode) VALUES (?, ?, ?)", (slug, title, passcode)
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"A text with slug '{slug}' already exists")
    conn.executemany(
        "INSERT INTO chapters (text_id, ord, title, html, plain) VALUES (?, ?, ?, ?, ?)",
        [(cur.lastrowid, c["ord"], c["title"], c["html"], c["plain"]) for c in chapters],
    )
    conn.commit()
    return {"slug": slug, "chapters": len(chapters)}


class TextUpdate(BaseModel):
    passcode: str


@router.patch("/admin/texts/{slug}")
async def update_text(slug: str, body: TextUpdate, request: Request, conn=Depends(get_conn)):
    auth.require_admin(request)
    text = get_text(conn, slug)
    if not body.passcode.strip():
        raise HTTPException(400, "Passcode can't be empty")
    conn.execute("UPDATE texts SET passcode = ? WHERE id = ?", (body.passcode.strip(), text["id"]))
    conn.commit()
    return {"ok": True}


@router.delete("/admin/texts/{slug}")
async def delete_text(slug: str, request: Request, conn=Depends(get_conn)):
    auth.require_admin(request)
    text = get_text(conn, slug)
    conn.execute("DELETE FROM texts WHERE id = ?", (text["id"],))
    conn.commit()
    events.publish(text["id"])
    return {"ok": True}
