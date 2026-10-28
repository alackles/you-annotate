# For Acacia

Running to-do list and handoff notes for the human side of the project.

## Status (2026-10-28)

All of SPEC.md is built and tested locally (see `plans/2026-10-28-first-build.md`). **Not deployed yet.** The Equiano text isn't loaded yet either.

## To do

- [x] **Try it locally.** One-time: `uv venv && uv pip install -r requirements-dev.txt`, then `cp .env.example .env` and set `ADMIN_PASSWORD`. Run `.venv/bin/uvicorn app.main:app --reload`, open http://localhost:8000/admin, and upload `fixtures/sample.md` (passcode anything).
- [ ] **Hands-on check of what the automated tests can't judge:**
  - Does it *feel* right to read? Typography, highlight colors, how quiet the footnotes and margin markers are.
  - Selecting text on a **real phone or tablet**. Touch selection is the least-tested path.
  - Two browsers side by side (e.g. one normal, one private window) with different names: notes appear live in both.
- [ ] **Equiano.** The whole book is converted: `texts/equiano.md` (Front Matter + Chapters I–XII, checked word-for-word against the Gutenberg HTML), made by `scripts/gutenberg_to_md.py`. Equiano's own 26 footnotes are in `texts/equiano-footnotes.json`. Upload it via `/admin` on the **deployed** site; a local upload only lives in your local database. Next: a footnote loader for Equiano's notes plus your Oxford index. All 90 index entries (Chapters I–VI) can be located in the text. In your draft, the headings for Chapters IV and V look shifted: notes on pp. 53–57 fall in Chapter III, and pp. 59–72 in Chapter IV. Decide whether `texts/` gets committed: Gutenberg is public domain, and the notes index is your call.
- [ ] **Deploy to Fly.io** (needs your go-ahead; Claude can run these if you say so). First time only:
  ```bash
  fly apps create you-annotate
  fly volumes create data --size 1 --region ord --app you-annotate
  fly secrets set --app you-annotate \
      ADMIN_PASSWORD='…' \
      ADMIN_NAME='…your name as students should see it…' \
      SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  fly deploy --ha=false
  ```
  After that, every update is just `fly deploy --ha=false`. `--ha=false` matters: the app must run on exactly one machine. The Docker image hasn't been built locally (no Docker permission here), so the first `fly deploy` is also its first build.
- [ ] **Decide the student passcode and your display name** (`ADMIN_NAME`) before class.

## Good to know

- **Backups:** the database is one file on the Fly volume. Fly takes automatic daily volume snapshots (check with `fly volumes snapshots list`). There's no export feature yet; SPEC defers it.
- **Lost edit rights:** a student who switches devices or clears cookies can't edit their old notes. You can, as admin.
- **Names aren't unique:** two people can both join as "Sam". They can't edit each other's notes, but they'll look alike.
