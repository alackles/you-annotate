# For Acacia

Running to-do list and handoff notes for the human side of the project. Move items to done when they're checked off or stated as done.

## Status (2026-10-28)

**Live at https://you-annotate.fly.dev/**, with the whole Equiano text uploaded at https://you-annotate.fly.dev/t/equiano. Admin login uses the password from your local `.env`; your annotations show as "Acacia Ackles". The text has 115 footnotes: Equiano's 26 plus 89 from your notes index.

## To do

- **Deploy and take a first export** (`fly deploy --ha=false`, then Export on /admin). Keep the file somewhere durable. `texts/` is gitignored, so the export's copy of the text may be the only one off your laptop.

## Next time

Planned for the next round of work. Context: the first class used it on 2026-10-28, about 100 minutes after the build started. Students used structural links as instructed, and (unprompted) took readily to answering each other's questions in threads.

- **Let a text be revised after upload.** Right now texts can't be changed, because annotations anchor by UTF-16 offsets into each chapter's `plain` text. The groundwork for revision exists: every annotation and link end stores its `quote`, so a revised text can re-anchor each one by searching for that quote. Search near the old offset first, then anywhere in the chapter, normalizing dashes and whitespace the way `scripts/load_footnotes.py` does. Match chapters by title, falling back to the whole text. Make it preview-then-apply like the loader, and **report** anything that doesn't land uniquely rather than dropping it. Restore already does most of this (`_Placer` in `app/backup.py`: quote search with prefix/suffix tie-breaking, a placement report). Revision could be "export, upload the revised text, restore", with dash/whitespace normalization added to the placer.
- **PDF texts (thinking it over, not decided).** These are for texts other than Equiano. There are three approaches, best built in this order:
  - **A. Extract to Markdown.** A prep script, like `gutenberg_to_md.py`, converts the PDF and uploads the result as an ordinary text. Almost no app changes. Good for clean born-digital PDFs, but it loses page layout and fails on scans. For scans, `ocrmypdf` run offline can add a text layer first.
  - **B. Page images + box annotations.** Rasterize pages at upload. Add a second anchor type, `(page, x, y, w, h)` in 0–1 page coordinates. Students draw a box, then pick vocab, comment, link, or footnote as usual. No text alignment is needed, so this handles garbled text layers and scans. The panel shows a CSS-cropped thumbnail of the box where the quote would be. Estimated at about 300–450 lines, one session.
  - **C. Page images + invisible text layer.** The server emits positioned word spans over each page image, so `plain = textContent` still holds and text highlighting works on pages. The hard part is getting selection to line up with the glyphs.
  - *Open decisions:* (1) Is page mode a per-text setting, or always on for PDFs? Claude suggests per-text, with clean PDFs going through A. (2) Do boxes exist only in page mode, or also in text mode? Claude suggests page mode only, at first. (3) Build C at all? Claude suggests building B, trying it with a class, and seeing whether anyone misses text selection.
  - *Gotchas:* `paint()` resets `innerHTML` on every repaint, so page images must live in a layer it doesn't touch. Inline footnote `<sup>`s would push a positioned text layer out of alignment, so page mode needs overlay markers. Pages want a wider center column. PyMuPDF is AGPL; pypdfium2 (Apache/BSD) also rasterizes and gives character boxes.
- *Known, not planned:* the app is single-machine by design (in-memory live-update hub, SQLite on one volume). That's fine for a class; going beyond one machine would need a shared message bus and database.

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

- **Backups:** the database is one file on the Fly volume. Fly takes automatic daily volume snapshots, kept 5 days (check with `fly volumes snapshots list`). For a copy you hold: Export on /admin, or `curl -o equiano-$(date +%F).json https://you-annotate.fly.dev/api/texts/equiano/export` (no login needed). To recover after losing the database: re-upload `texts/equiano.md` under the same slug, then Restore… with the export file. Restored notes are admin-editable only (students' edit rights can't be carried in a backup without copying their browser keys into it).
- **Lost edit rights:** a student who switches devices or clears cookies can't edit their old notes. You can, as admin.
- **Names aren't unique:** two people can both join as "Sam". They can't edit each other's notes, but they'll look alike.
