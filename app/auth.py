"""Who is making this request.

Admin: one instructor, password from the ADMIN_PASSWORD env var, remembered in a signed
session cookie.
"""

import hmac
import os

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
