"""SQLite storage. Plain sqlite3, one connection per request, explicit commits."""

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS texts (
    id          INTEGER PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    passcode    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chapters (
    id       INTEGER PRIMARY KEY,
    text_id  INTEGER NOT NULL REFERENCES texts(id) ON DELETE CASCADE,
    ord      INTEGER NOT NULL,
    title    TEXT NOT NULL,
    html     TEXT NOT NULL,
    plain    TEXT NOT NULL,  -- textContent of html; offsets index into this (UTF-16 units)
    UNIQUE (text_id, ord)
);

-- One row per browser per text. The token is the browser's cookie; it is what owns annotations.
CREATE TABLE IF NOT EXISTS participants (
    token      TEXT NOT NULL,
    text_id    INTEGER NOT NULL REFERENCES texts(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    joined_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (token, text_id)
);

CREATE TABLE IF NOT EXISTS annotations (
    id            INTEGER PRIMARY KEY,
    text_id       INTEGER NOT NULL REFERENCES texts(id) ON DELETE CASCADE,
    chapter_id    INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    layer         TEXT NOT NULL CHECK (layer IN ('vocab', 'commentary', 'footnote')),
    start_offset  INTEGER NOT NULL,
    end_offset    INTEGER NOT NULL,
    quote         TEXT NOT NULL,
    body          TEXT NOT NULL DEFAULT '',
    author_name   TEXT NOT NULL,
    author_token  TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS annotations_by_text ON annotations(text_id);

CREATE TABLE IF NOT EXISTS replies (
    id             INTEGER PRIMARY KEY,
    annotation_id  INTEGER NOT NULL REFERENCES annotations(id) ON DELETE CASCADE,
    body           TEXT NOT NULL,
    author_name    TEXT NOT NULL,
    author_token   TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TEXT
);

-- Structural annotations: a bidirectional link between two passages.
CREATE TABLE IF NOT EXISTS links (
    id                 INTEGER PRIMARY KEY,
    text_id            INTEGER NOT NULL REFERENCES texts(id) ON DELETE CASCADE,
    anchor_chapter_id  INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    anchor_start       INTEGER NOT NULL,
    anchor_end         INTEGER NOT NULL,
    anchor_quote       TEXT NOT NULL,
    dest_chapter_id    INTEGER NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    dest_start         INTEGER NOT NULL,
    dest_end           INTEGER NOT NULL,
    dest_quote         TEXT NOT NULL,
    author_name        TEXT NOT NULL,
    author_token       TEXT NOT NULL,
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS links_by_text ON links(text_id);
"""


def db_path() -> str:
    return os.environ.get("DB_PATH", "annotate.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


async def get_conn():
    """FastAPI dependency. Async so the connection lives on the event-loop thread."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
