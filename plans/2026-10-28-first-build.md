# First build: you-annotate MVP

## Context

The repo has a frozen SPEC.md, CLAUDE.md, and two logged decisions (multi-text data model with a single-text UI; ownership tied to a browser token). No code yet. Acacia's goal is a working classroom tool. The meta-goal is to see how well Claude builds an app to a front-loaded spec, so **Claude makes the judgment calls** and logs them in DECISIONS.md. The stack is agreed: FastAPI + SQLite on a Fly volume (one machine), SSE for live updates, plain JS modules with no build step, Markdown text import.

This plan builds the whole spec in five stages. Each stage is runnable and gets its own commit (author Claude). Execution stops before the first `fly deploy`, which is outward-facing and needs Acacia's go-ahead. Converting the Equiano text she's fetching is a separate follow-up; dev and tests use a small fixture text.

## Layout

```
app/
  main.py        FastAPI app, page routes, mounts /static
  db.py          sqlite3 (stdlib, no ORM), schema, connection helper, WAL
  auth.py        passcode join, browser-token cookie, admin session
  api.py         JSON routes (texts, annotations, replies, links, admin)
  events.py      in-memory SSE hub: text_id -> set[asyncio.Queue]
  importer.py    Markdown -> per-chapter HTML + plain text
static/
  reader.html, admin.html, index.html
  css/reader.css
  js/ api.js  anchoring.js (DOM<->offsets)  segments.js (pure)  render.js
      margins.js (footnote + structural layout)  panel.js  reader.js
tests/  test_importer.py  test_api.py  segments.test.mjs
fixtures/sample.md
requirements.txt  requirements-dev.txt  .env.example  Dockerfile  fly.toml
```

## Core design

**Data model** (all rows carry `text_id`):
- `texts(id, slug, title, passcode, created_at)`. The passcode is stored as plaintext, since it's a shared class word that the admin needs to see, not a secret.
- `chapters(id, text_id, ord, title, html, plain)`
- `participants(token, text_id, name, joined_at)`: one row per browser per text.
- `annotations(id, text_id, chapter_id, layer ∈ {vocab, commentary, footnote}, start, end, quote, body, author_name, author_token, created_at, updated_at)`
- `replies(id, annotation_id, body, author_name, author_token, …)`
- `links(id, text_id, anchor_chapter_id, anchor_start, anchor_end, anchor_quote, dest_chapter_id, dest_start, dest_end, dest_quote, author_name, author_token, …)`

**Anchoring.** Offsets are UTF-16 code-unit indices into the chapter's DOM `textContent`, which is what JS sees natively. The server computes the same `plain` string at import time with `html.parser` and validates every write: `plain[start:end] == quote`, sliced in UTF-16 units. A mismatch is rejected with a 422, so corrupt anchors can't get into the database. The text can't be changed after upload, so offsets never go stale. UI-only elements such as footnote markers carry the class `.ui`, and the DOM walker skips them.

**Rendering.** For each chapter: start from a clean clone of the chapter HTML; `segments.js` cuts the text at every annotation boundary into runs, each with the set of annotations covering it; `render.js` wraps each run in one `<span>` with `data-anns` and layer classes. Spans are never nested. Where vocab and commentary overlap, the run gets both tints as a split gradient. Clicking a run opens every annotation that covers it. The whole chapter is re-rendered on any change, which is simpler than incremental patching and fast enough at this size.

**Live updates.** Every write goes through `events.publish(text_id)`, which pushes a bare "changed" ping. Each client keeps one `EventSource`. On a ping it refetches `GET /api/texts/{slug}/annotations` (all layers for the whole text, which is small) and re-renders, with a 300ms debounce. The server sends a heartbeat comment every 15s so Fly's proxy doesn't drop idle streams. It runs as a single uvicorn worker (the hub lives in memory). Routes are `async` and run sqlite calls inline, which takes microseconds at this scale.

**Identity.**
- Visitor: no cookie, so read-only. `/t/{slug}` is the shareable URL.
- Join: name + passcode → the server sets a long-lived httpOnly, SameSite=Lax `ya_token` cookie and upserts a `participants` row. Writes require a participant row (or admin). Edit/delete requires `author_token == token` or admin.
- Admin: password only (`ADMIN_PASSWORD` env var / Fly secret, checked with `compare_digest`), stored in a signed Starlette session cookie (`SECRET_KEY`). The admin annotates under the name `ADMIN_NAME`; their annotations look like everyone else's, as the spec requires.

**UI.**
- The reader is one page with hash routing (`/t/equiano#3`, or `#3/a42` to deep-link an annotation). Only one chapter is shown at a time; prev/next and a chapter menu sit in the header.
- Three columns: left margin ~13rem, a ~66ch serif text column, right margin ~13rem. The comment panel is a right-side drawer that slides over the right margin. Below ~1000px the margins narrow and footnotes become popovers (basic, not polished).
- Selecting text shows a floating toolbar: Vocab · Commentary · Link (· Footnote, admin only). Vocab and Commentary open the panel with a comment box. Link stores the selection as a pending anchor and shows a banner, "Select the destination passage (Esc to cancel)"; the next selection, even in another chapter, completes the link.
- Structural links: in the right margin, a thin ink-colored bar runs the height of the destination passage, topped by a Roman numeral. The numeral links back to the anchor. Numbering is per anchor chapter, in anchor text order (so outline items read I, II, III), and is computed, not stored. Overlapping bars get separate lanes by greedy interval assignment. The anchor text has no color, just a pointer cursor and an underline on hover, plus a faint small numeral in the margin so it can be found. The owner or admin sees a × on hover to delete.
- Footnotes: a faint superscript number (`.ui`) after the range. On hover or click, the note's text appears in the left margin, aligned to the marker's line, in grayscale. The admin gets edit/delete there.
- Threads: show the quote, author, body, replies, and a reply box (participants only), plus edit/delete where allowed. User text is rendered with `textContent`, and bare URLs are turned into `<a>` elements built through the DOM, which covers the spec's "links only" for media.
- Colors: vocab is a muted blue tint and commentary a muted amber tint, both low alpha. Footnotes are gray. Structural markers are dark ink. The body font is Literata (Google Fonts) with a serif fallback.

**Admin page** (`/admin`): log in or out; upload a `.md`/`.txt` file with title, slug and passcode; list texts; change a passcode; delete a text. Each top-level `#` heading starts a chapter, and text before the first heading becomes a front-matter chapter if it isn't empty. Re-uploading a text that has annotations is not supported, because offsets would break.

## Stages (one commit each)

1. **Skeleton + reading view.** db schema, importer, page routes, chapter API, reader with chapter navigation and typography, admin upload. Tests: chapter splitting; `plain` matches the browser's `textContent` rules; UTF-16 slicing.
2. **Identity.** Join flow, token cookie, admin login, permission checks. Tests: visitor can't write; wrong passcode rejected; a user can edit or delete their own annotation but not someone else's; admin can edit or delete anything; footnotes are admin-only.
3. **Highlights + threads + live updates.** segments.js, render.js, the selection toolbar, the panel, replies, and SSE. Tests: `node --test` for overlap segmentation; an API test that a quote mismatch returns 422.
4. **Footnotes + structural links.** margins.js: positions are measured with `Range.getClientRects()`, layout is recomputed on resize and re-render, plus lane assignment. Tests: `node --test` for lane assignment and Roman numerals.
5. **Deploy prep + docs.** Dockerfile (python:3.12-slim, one uvicorn worker), fly.toml (`you-annotate`, region `ord`, volume mounted at `/data`, `DB_PATH=/data/annotate.db`, one machine). Write README.md for non-coders. Add commands and the "Claude makes judgment calls here" note to CLAUDE.md. Add Fly setup steps to HUMAN.md (volume, secrets, deploy, and a manual browser test checklist). Add DECISIONS.md rows for the stack and every judgment call above, with the anchor numeral marked as an addition beyond the spec. Copy this plan to `plans/2026-10-28-first-build.md`.

Dev env: `uv venv && uv pip install -r requirements-dev.txt`; `.env` holds `ADMIN_PASSWORD`, `SECRET_KEY`, `ADMIN_NAME`, `DB_PATH` (loaded via python-dotenv).

## Verification

- `pytest` and `node --test tests/` pass.
- Run `uvicorn app.main:app --reload`, upload `fixtures/sample.md` through /admin, then check with curl: join, create an annotation, reject a mismatched quote, and confirm an event arrives on an open `curl -N` SSE stream.
- Browser: if a headless browser is available, take screenshots of the reader with each layer present. Otherwise the HUMAN.md checklist covers it: two browser windows with different names show each other's annotations live, the visitor view is read-only, and structural navigation works in both directions.
- Stop. Acacia approves before the first `fly deploy`.
