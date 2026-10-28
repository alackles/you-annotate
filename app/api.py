"""JSON API."""

import re
import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from . import auth
from .db import get_conn
from .importer import build_chapters

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
    return {
        "id": text["id"],
        "slug": text["slug"],
        "title": text["title"],
        "chapters": [dict(c) for c in chapters],
        "me": {"admin": auth.is_admin(request)},
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
    return {"ok": True}
