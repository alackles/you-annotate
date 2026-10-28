# For Acacia

Running to-do list and handoff notes for the human side of the project. Move items to done when they're checked off or stated as done.

## Status (2026-10-28)

**Live at https://you-annotate.fly.dev/**, with the whole Equiano text uploaded at https://you-annotate.fly.dev/t/equiano. Admin login uses the password from your local `.env`; your annotations show as "Acacia Ackles". The text has 115 footnotes: Equiano's 26 plus 89 from your notes index.

## To do


## Done

- Local run
- texts/ gitignored
- student passcode confirmed
- hands-on check done
- footnotes loaded (`scripts/load_footnotes.py`)

## Deploying updates

`fly deploy --ha=false` from the repo root. `--ha=false` matters: the app must run on exactly one machine (in-memory live updates, SQLite on one volume). The app is `you-annotate` (org: personal); its volume `data` (1 GB, ord) is mounted at `/data`. Secrets: `ADMIN_PASSWORD`, `ADMIN_NAME`, `SECRET_KEY` (`fly secrets list --app you-annotate`).

## Good to know

- **Adding more notes:** add entries to `texts/equiano_files/equiano_explanatory_notes_index.md` (Chapter VII onward), then run `.venv/bin/python scripts/load_footnotes.py` to preview and the same with `--apply` to add them. Notes already on the site are skipped. Changing an existing entry's text adds a new note rather than replacing the old one, so delete the old one in the reader (as admin, open the note and click "edit"). Your draft's Chapter IV/V headings look shifted (pp. 53–57 are in Chapter III, pp. 59–72 in Chapter IV); the loader doesn't depend on them.

- **Backups:** the database is one file on the Fly volume. Fly takes automatic daily volume snapshots (check with `fly volumes snapshots list`). There's no export feature yet; SPEC defers it.
- **Lost edit rights:** a student who switches devices or clears cookies can't edit their old notes. You can, as admin.
- **Names aren't unique:** two people can both join as "Sam". They can't edit each other's notes, but they'll look alike.
