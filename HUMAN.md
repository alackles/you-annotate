# For Acacia

Running to-do list and handoff notes for the human side of the project.

## Status (2026-10-28)

**Live at https://you-annotate.fly.dev/**, with the whole Equiano text uploaded at https://you-annotate.fly.dev/t/equiano (student passcode `equiano`; change it at `/admin`). Admin login uses the password from your local `.env`; your annotations show as "Acacia Ackles". There are no footnotes on the live text yet.

## To do

- [x] **Try it locally.**
- [ ] **Hands-on check on the live site** of what the automated tests can't judge:
  - Does it *feel* right to read? Typography, highlight colors, how quiet the footnotes and margin markers are.
  - Selecting text on a **real phone or tablet**. Touch selection is the least-tested path.
  - Two browsers side by side (e.g. one normal, one private window) with different names: notes appear live in both.
- [ ] **Footnotes.** Next Claude task: a loader script that adds Equiano's 26 notes (`texts/equiano-footnotes.json`) and your Oxford index (Chapters I–VI, all 90 entries locatable in page order) to the live text. In your draft, the headings for Chapters IV and V look shifted: notes on pp. 53–57 fall in Chapter III, and pp. 59–72 in Chapter IV.
- [ ] **Decide whether `texts/` gets committed.** Gutenberg is public domain; the notes index is your call.
- [ ] **Confirm the student passcode** before class (currently `equiano`).

## Deploying updates

`fly deploy --ha=false` from the repo root. `--ha=false` matters: the app must run on exactly one machine (in-memory live updates, SQLite on one volume). The app is `you-annotate` (org: personal); its volume `data` (1 GB, ord) is mounted at `/data`. Secrets: `ADMIN_PASSWORD`, `ADMIN_NAME`, `SECRET_KEY` (`fly secrets list --app you-annotate`).

## Good to know

- **Backups:** the database is one file on the Fly volume. Fly takes automatic daily volume snapshots (check with `fly volumes snapshots list`). There's no export feature yet; SPEC defers it.
- **Lost edit rights:** a student who switches devices or clears cookies can't edit their old notes. You can, as admin.
- **Names aren't unique:** two people can both join as "Sam". They can't edit each other's notes, but they'll look alike.
