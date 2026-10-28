"""Who is making this request.

Admin: one instructor, password from the ADMIN_PASSWORD env var, remembered in a signed
session cookie. Students: see "Participants" below. Visitors: neither; read-only.
"""

import hmac
import os
import secrets
import sqlite3

from fastapi import HTTPException, Request


def is_admin(request: Request) -> bool:
    return request.session.get("admin") is True


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(403, "Admin login required")


def check_admin_password(password: str) -> bool:
    expected = os.environ.get("ADMIN_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(password.encode(), expected.encode())


def admin_name() -> str:
    return os.environ.get("ADMIN_NAME", "Instructor")


# --- Participants (students) -----------------------------------------------------------
#
# Joining with name + passcode gives the browser a random token cookie. Each annotation
# stores its author's token; only that token (or the admin) can edit or delete it.

TOKEN_COOKIE = "ya_token"
TOKEN_MAX_AGE = 60 * 60 * 24 * 365


def identity(request: Request, conn: sqlite3.Connection, text_id: int) -> dict | None:
    """{name, token, admin} for whoever may write to this text, or None for a visitor."""
    if is_admin(request):
        return {"name": admin_name(), "token": "admin", "admin": True}
    token = request.cookies.get(TOKEN_COOKIE)
    if not token:
        return None
    row = conn.execute(
        "SELECT name FROM participants WHERE token = ? AND text_id = ?", (token, text_id)
    ).fetchone()
    return {"name": row["name"], "token": token, "admin": False} if row else None


def require_identity(request: Request, conn: sqlite3.Connection, text_id: int) -> dict:
    ident = identity(request, conn, text_id)
    if ident is None:
        raise HTTPException(403, "Join with the class passcode to annotate")
    return ident


def can_modify(ident: dict | None, row) -> bool:
    return ident is not None and (ident["admin"] or row["author_token"] == ident["token"])


def passcode_matches(given: str, expected: str) -> bool:
    return hmac.compare_digest(given.strip().lower().encode(), expected.strip().lower().encode())


def new_token() -> str:
    return secrets.token_urlsafe(24)
