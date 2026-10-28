from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.importer import build_chapters

SAMPLE_PATH = Path(__file__).parent.parent / "fixtures" / "sample.md"
CHAPTER_I = build_chapters(SAMPLE_PATH.read_text())[1]["plain"]  # chapter id 2 once uploaded


def span(word: str, chapter_id: int = 2) -> dict:
    start = CHAPTER_I.index(word)  # sample is all BMP, so Python index == UTF-16 offset
    return {"chapter_id": chapter_id, "start": start, "end": start + len(word), "quote": word}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "pw")
    monkeypatch.setenv("ADMIN_NAME", "Prof")
    from app.main import app

    with TestClient(app) as admin:
        admin.post("/api/admin/login", json={"password": "pw"}).raise_for_status()
        admin.post(
            "/api/admin/texts",
            files={"file": ("sample.md", SAMPLE_PATH.read_bytes())},
            data={"title": "Sample", "slug": "sample", "passcode": "Fish"},
        ).raise_for_status()
        yield app


@pytest.fixture
def admin(app):
    with TestClient(app) as c:
        c.post("/api/admin/login", json={"password": "pw"}).raise_for_status()
        yield c


def student(app, name):
    c = TestClient(app)
    c.post("/api/texts/sample/join", json={"name": name, "passcode": "fish"}).raise_for_status()
    return c


def annotate(client, word="industrious", layer="vocab", body="?"):
    return client.post("/api/texts/sample/annotations", json={**span(word), "layer": layer, "body": body})


def test_wrong_passcode_rejected(app):
    res = TestClient(app).post("/api/texts/sample/join", json={"name": "Eve", "passcode": "nope"})
    assert res.status_code == 403


def test_visitor_can_read_but_not_write(app):
    visitor = TestClient(app)
    assert visitor.get("/api/texts/sample/annotations").status_code == 200
    assert visitor.get("/api/texts/sample").json()["me"]["can_write"] is False
    assert annotate(visitor).status_code == 403


def test_students_edit_and_delete_only_their_own(app):
    alice, bob = student(app, "Alice"), student(app, "Bob")
    ann_id = annotate(alice).json()["id"]

    assert bob.patch(f"/api/annotations/{ann_id}", json={"body": "hijack"}).status_code == 403
    assert bob.delete(f"/api/annotations/{ann_id}").status_code == 403
    assert alice.patch(f"/api/annotations/{ann_id}", json={"body": "hard-working"}).status_code == 200

    # Bob can reply to Alice's thread, but Alice can't edit Bob's reply.
    reply_id = bob.post(f"/api/annotations/{ann_id}/replies", json={"body": "diligent"}).json()["id"]
    assert alice.patch(f"/api/replies/{reply_id}", json={"body": "x"}).status_code == 403

    listing = alice.get("/api/texts/sample/annotations").json()["annotations"][0]
    assert listing["can_edit"] is True and listing["replies"][0]["can_edit"] is False
    assert alice.delete(f"/api/annotations/{ann_id}").status_code == 200


def test_same_name_in_another_browser_is_not_the_same_author(app):
    alice = student(app, "Alice")
    impostor = student(app, "Alice")
    ann_id = annotate(alice).json()["id"]
    assert impostor.delete(f"/api/annotations/{ann_id}").status_code == 403


def test_admin_can_edit_and_delete_anything(app, admin):
    alice = student(app, "Alice")
    ann_id = annotate(alice, layer="commentary", body="nice").json()["id"]
    link = {"anchor": span("The market and its customs"), "dest": span("The market was held")}
    link_id = alice.post("/api/texts/sample/links", json=link).json()["id"]

    assert admin.patch(f"/api/annotations/{ann_id}", json={"body": "edited"}).status_code == 200
    assert admin.delete(f"/api/links/{link_id}").status_code == 200
    assert admin.delete(f"/api/annotations/{ann_id}").status_code == 200


def test_footnotes_are_admin_only_and_threadless(app, admin):
    alice = student(app, "Alice")
    assert annotate(alice, "strand", "footnote", "A beach.").status_code == 403
    fn_id = annotate(admin, "strand", "footnote", "A beach.").json()["id"]
    assert alice.post(f"/api/annotations/{fn_id}/replies", json={"body": "hi"}).status_code == 400
    by_admin = alice.get("/api/texts/sample/annotations").json()["annotations"][0]
    assert by_admin["author_name"] == "Prof"


def test_mismatched_quote_rejected(app):
    alice = student(app, "Alice")
    bad = {**span("industrious"), "quote": "industrial", "layer": "vocab", "body": ""}
    assert alice.post("/api/texts/sample/annotations", json=bad).status_code == 422
    out_of_range = {**span("industrious"), "end": 10**6, "layer": "vocab", "body": ""}
    assert alice.post("/api/texts/sample/annotations", json=out_of_range).status_code == 422


def test_commentary_needs_a_comment_but_vocab_does_not(app):
    alice = student(app, "Alice")
    assert annotate(alice, layer="vocab", body="").status_code == 200
    assert annotate(alice, layer="commentary", body="  ").status_code == 422


def test_listing_never_exposes_tokens(app):
    alice = student(app, "Alice")
    annotate(alice)
    assert "token" not in TestClient(app).get("/api/texts/sample/annotations").text


def test_footnote_voice_set_on_create_and_edit(app, admin):
    fn_id = admin.post("/api/texts/sample/annotations",
                       json={**span("strand"), "layer": "footnote", "body": "A beach.", "voice": "author"}).json()["id"]
    listing = lambda: {a["id"]: a for a in admin.get("/api/texts/sample/annotations").json()["annotations"]}
    assert listing()[fn_id]["voice"] == "author"
    assert admin.patch(f"/api/annotations/{fn_id}", json={"body": "A shore.", "voice": "editor"}).status_code == 200
    assert listing()[fn_id]["voice"] == "editor"
    vocab_id = annotate(admin).json()["id"]
    assert admin.patch(f"/api/annotations/{vocab_id}", json={"body": "x", "voice": "author"}).status_code == 422


def test_old_database_gains_voice_column(tmp_path, monkeypatch):
    import sqlite3
    from app import db
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA.replace("    voice         TEXT NOT NULL DEFAULT 'editor',  -- footnotes: 'author' (the book's own) or 'editor'\n", ""))
    old.close()
    monkeypatch.setenv("DB_PATH", str(path))
    db.init()
    columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(annotations)")}
    assert "voice" in columns
