import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from . import api, db  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "static"
# Fly sets FLY_APP_NAME; there the site is HTTPS-only, so cookies should be too.
ON_FLY = bool(os.environ.get("FLY_APP_NAME"))


@asynccontextmanager
async def lifespan(app):
    db.init()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware,
    # Without SECRET_KEY, admin sessions just don't survive a restart.
    secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    session_cookie="ya_admin",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=ON_FLY,
)
app.include_router(api.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/t/{slug}", include_in_schema=False)
async def reader(slug: str):
    return FileResponse(STATIC / "reader.html")


@app.get("/admin", include_in_schema=False)
async def admin():
    return FileResponse(STATIC / "admin.html")
