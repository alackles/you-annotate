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


def test_forged_admin_token_cookie_is_replaced_on_join(app, admin):
    fn_id = annotate(admin, "strand", "footnote", "A beach.").json()["id"]
    forger = TestClient(app)
    forger.cookies.set("ya_token", "admin")
    forger.post("/api/texts/sample/join", json={"name": "Mallory", "passcode": "fish"}).raise_for_status()
    assert forger.delete(f"/api/annotations/{fn_id}").status_code == 403


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


def second_copy(admin, slug="copy"):
    admin.post("/api/admin/texts", files={"file": ("sample.md", SAMPLE_PATH.read_bytes())},
               data={"title": "Copy", "slug": slug, "passcode": "fish"}).raise_for_status()


def comparable(client, slug):
    """A text's annotations and links with ids and permissions stripped."""
    data = client.get(f"/api/texts/{slug}/annotations").json()
    drop = lambda d: {k: v for k, v in d.items() if k not in ("id", "chapter_id", "can_edit")}
    anns = [{**drop(a), "replies": [drop(r) for r in a["replies"]]} for a in data["annotations"]]
    links = [{**drop(k), "anchor": drop(k["anchor"]), "dest": drop(k["dest"])} for k in data["links"]]
    return anns, links


def test_export_restores_onto_a_fresh_upload(app, admin):
    alice = student(app, "Alice")
    vocab_id = annotate(alice).json()["id"]
    student(app, "Bob").post(f"/api/annotations/{vocab_id}/replies", json={"body": "diligent"}).raise_for_status()
    annotate(alice, "strand", "commentary", "nice word")
    admin.post("/api/texts/sample/annotations",
               json={**span("strand"), "layer": "footnote", "body": "A beach.", "voice": "author"}).raise_for_status()
    alice.post("/api/texts/sample/links",
               json={"anchor": span("The market and its customs"), "dest": span("The market was held")}).raise_for_status()

    res = TestClient(app).get("/api/texts/sample/export")  # visitors can export
    assert "attachment" in res.headers["content-disposition"] and "token" not in res.text
    exported = res.json()

    second_copy(admin)
    preview = admin.post("/api/admin/texts/copy/restore", json=exported).json()
    assert preview["annotations"]["exact"] == 3 and preview["links"]["exact"] == 1 and preview["replies"] == 1
    assert preview["applied"] is False and admin.get("/api/texts/copy/annotations").json()["annotations"] == []

    admin.post("/api/admin/texts/copy/restore?apply=true", json=exported).raise_for_status()
    assert comparable(admin, "copy") == comparable(admin, "sample")  # incl. authors, voice, timestamps

    again = admin.post("/api/admin/texts/copy/restore?apply=true", json=exported).json()
    assert again["annotations"]["duplicate"] == 3 and again["links"]["duplicate"] == 1
    assert len(admin.get("/api/texts/copy/annotations").json()["annotations"]) == 3

    # Restored items belong to no browser: Alice can't edit hers in the copy, the admin can.
    alice.post("/api/texts/copy/join", json={"name": "Alice", "passcode": "fish"}).raise_for_status()
    copied = alice.get("/api/texts/copy/annotations").json()["annotations"]
    assert not any(a["can_edit"] for a in copied)
    assert admin.delete(f"/api/annotations/{copied[0]['id']}").status_code == 200


def test_restore_refinds_drifted_quotes_and_reports_lost_ones(app, admin):
    annotate(admin, "industrious")
    annotate(admin, "strand")
    exported = admin.get("/api/texts/sample/export").json()
    drifted, lost = exported["annotations"]
    drifted["start"] += 3
    drifted["end"] += 3
    lost["quote"] = "nowhere in the text"

    second_copy(admin)
    assert student(app, "Alice").post("/api/admin/texts/copy/restore", json=exported).status_code == 403
    assert admin.post("/api/admin/texts/copy/restore", json={"hello": 1}).status_code == 400
    report = admin.post("/api/admin/texts/copy/restore?apply=true", json=exported).json()
    assert report["annotations"]["moved"] == 1 and report["annotations"]["unplaced"] == 1
    assert "nowhere in the text" in report["problems"][0]
    [placed] = admin.get("/api/texts/copy/annotations").json()["annotations"]
    assert placed["quote"] == "industrious" and placed["start"] == span("industrious")["start"]


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
