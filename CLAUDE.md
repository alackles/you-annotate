# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Collaborative Text Annotation Tool

## What This Is

A web-based collaborative annotation platform for close reading of texts. Built for a college classroom but designed as a general-purpose tool. The first text is Olaudah Equiano's *The Interesting Narrative* (public domain, 18th century), but the platform should work for any uploaded text.

The core idea: students annotate a shared text together in real time using three distinct annotation layers, each with its own visual language and interaction model. An instructor can also pre-load editorial footnotes as part of the text's own apparatus.

## Specifications

See @docs/SPEC.md for full specs. **Do not edit docs/SPEC.md** -- when changes arise or decisions are made regarding the layout of the app which a human might want to know, instead add to docs/DECISIONS.md.

## Working agreement

Acacia's goal here is a working classroom tool, and the meta-goal is to see how well Claude builds an app from a front-loaded spec. So **Claude makes the judgment calls** in this project rather than asking about each one, and logs every call in docs/DECISIONS.md, flagging anything that departs from or adds to docs/SPEC.md.

## Commands

```bash
uv venv && uv pip install -r requirements-dev.txt   # once
cp .env.example .env                                 # set ADMIN_PASSWORD etc.
.venv/bin/uvicorn app.main:app --reload              # http://localhost:8000, admin at /admin

.venv/bin/pytest                                     # Python tests (API, permissions, importer)
.venv/bin/pytest tests/test_api.py::test_mismatched_quote_rejected   # one test
node --test tests/                                   # JS pure-function tests (Node 18+, no deps)
.venv/bin/python scripts/e2e.py [shots-dir]          # browser end-to-end; needs `uv pip install playwright` + Google Chrome

fly deploy --ha=false                                # deploy (see docs/HUMAN.md for first-time setup)
.venv/bin/python scripts/gutenberg_to_md.py texts/equiano.html --out texts/equiano.md --footnotes texts/equiano-footnotes.json
.venv/bin/python scripts/load_footnotes.py [--base URL] [--apply]   # footnotes onto a live text; dry run unless --apply; idempotent
curl -o backup.json https://you-annotate.fly.dev/api/texts/equiano/export   # JSON backup; restore via /admin
```

## Architecture

FastAPI + stdlib `sqlite3` (no ORM) serving a JSON API and static files; the frontend is plain ES modules with no build step. Runs as **one process on one Fly machine**: the live-update hub (`app/events.py`) is in-memory, and SQLite lives on a single Fly volume.

**Anchoring is the core invariant.** An annotation is `(chapter_id, start, end, quote)`, with offsets in **UTF-16 code units** into the chapter's `plain` text, which equals the browser's `textContent` of the chapter HTML. `app/importer.py` computes `plain` at upload; `static/js/anchoring.js` maps DOM positions to offsets by walking text nodes. Every write re-checks `plain[start:end] == quote` server-side (`check_span` in `app/api.py`). Consequences:
- Texts can't be edited after upload; offsets would go stale.
- Anything injected into the chapter DOM for display (footnote markers) must have class `ui`, which the text-node walker skips. Otherwise every offset after it shifts.
- Highlight spans don't change `textContent`, so painting is safe.

**Rendering is redraw-from-scratch.** On any data change, `reader.js` `repaint()` resets the chapter to its pristine HTML, `render.js` `paint()` wraps covered runs in non-nested spans (`pure.js` `segment()` splits overlapping ranges), footnote markers are inserted, and `margins.js` re-measures both margins from `Range.getClientRects()`. Margins also re-lay out on resize and font load (ResizeObserver). Repaint is deferred while the reader has text selected, since it would destroy the selection.

**Live updates** carry no data: every write calls `events.publish(text_id)`, SSE clients get a `changed` ping and refetch `GET /api/texts/{slug}/annotations` (everything for the text). The comment panel (`panel.js`) preserves half-typed drafts across these refreshes.

**Identity:** admin is a signed session cookie (password from `ADMIN_PASSWORD`). Students join with name + passcode, which sets a random httpOnly `ya_token` cookie; rows store `author_token`, and edit/delete requires a matching token or admin (`auth.can_modify`). Tokens must never appear in API output.

**Export/restore** (`app/backup.py`) is the portable form of a text's data: chapter text plus every span as offsets + quote + prefix/suffix, keyed by chapter position, no tokens or ids. Restore re-finds each span and reports what it can't place. Restored rows get author token `""`, and admin rows get `"admin"`; `auth.is_issued_token` stops a browser from joining under either.

Layers: `vocab`/`commentary` (highlights + threads) and `footnote` (admin-only, no thread) share the `annotations` table; structural links are the separate `links` table (two spans, no thread). Link numerals are computed client-side (`numberLinks`), not stored.

## Documentation

- @docs/HUMAN.md: instructions and notes for the human (Acacia) developer - leave items here when they need human input or steps (e.g. setting up the fly.io server, testing between steps). Like a handoff document and running to-do list for the human.
- README.md: Human-facing, written for non-coders who want to understand what the tool is and how it's used.
- @docs/DECISIONS.md: A running list of decisions which have a bearing on the design, as a Markdown table with four columns: date, decision, AI contribution, Human contribution. (Either contribution may be empty, if the decision was solely AI or solely human.)
- @plans/: Whenever you enter "plan mode" and produce a plan, when the plan is approved, save it to `plans/YYYY-MM-DD-<plan-title-slug>.md`.

Freely update all these documents (except docs/SPEC.md).

## Additional Notes

- See `/home/acacia/Documents/software/home-software/baseball-for-girls/` for an example of an existing Claude-coded Fly.io-deployed app, if desired; however, note that was the first attempt at "vibe-coding" something like this, so do not take anything in there as superseding your instincts. Use its documentation (e.g. its `DEPLOY.md`, `fly.toml`) only if you run into Fly.io specific issues.
