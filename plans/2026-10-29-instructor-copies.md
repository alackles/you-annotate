# Instructor copies: one Fly app per instructor

## Context

Three colleagues teaching the same course want an "instructor copy" of the Equiano reader. Acacia decided (2026-10-29) against multi-tenancy inside one app ("sections"). Instead each instructor gets **a separate Fly app running this same code**: `you-annotate-<name>.fly.dev`. Reasons, in her words and mine: a copy is like handing someone a packet. Her own version can keep changing without affecting theirs. One colleague may take over his copy, and the history colleague wants to upload her own texts, which a copy's admin can already do with no new code.

Decisions already made with Acacia:
- **Hosting:** all copies live in Acacia's Fly org (`personal`), and she runs them this term.
- **Code:** one repo. Copies deploy from **dated release tags**. A fork happens only when someone wants to customize their copy.
- **What a new copy contains:** Equiano with its footnotes, and nothing else. The copy's admin adds their own footnotes and annotations from there.
- **What the instructor gets:** URL + instructor code (= that app's `ADMIN_PASSWORD`) + student passcode. `ADMIN_NAME` = their name.
- **Isolation:** copies are fully separate; view-only links still work as now.
- **No colleague-facing guide** until someone asks for one.
- **Custom domain deferred** until after the copies exist. Acacia's app keeps the name `you-annotate`, since Fly apps can't be renamed.

No changes to `app/` or `static/`. This is a script, a gitignore line, one test, and docs.

## Step 0: commit the pending export/restore work

`app/backup.py`, together with the changes to `api.py`, `admin.html` and `tests/test_api.py`, is done and logged in DECISIONS.md but not committed. Copies need it, because seeding uses restore, and a tag only captures committed code. Steps:
1. Run `pytest` and `node --test tests/`.
2. Commit it as its own commit.
3. Deploy Acacia's app (`fly deploy --ha=false`), so its export endpoint is live.
4. Take the first export, which is already on the HUMAN.md to-do list.

## Step 1: `scripts/copies.py`

Python, following the existing scripts' style (`httpx`, `argparse`, a module docstring with usage). It has two subcommands.

```
.venv/bin/python scripts/copies.py create smith --name "Dr. Smith" --passcode equiano [--tag release-2026-10-29]
.venv/bin/python scripts/copies.py deploy smith [--tag release-2026-11-05]
```

**`create`** goes through the steps below. Each step skips itself if already done, so a failed run can simply be re-run.
1. `fly apps create you-annotate-<name> --org personal`. If the name is taken by someone else, it stops with a clear message.
2. `fly volumes create data --app … --region ord --size 1 --yes`, unless the app already has a volume. This mirrors the current `fly.toml` mount.
3. **Secrets.** Generate `ADMIN_PASSWORD` (the instructor code: 12 characters, lowercase letters and digits with ambiguous ones dropped, grouped `xxxx-xxxx-xxxx`) and a `SECRET_KEY`. Set them, plus `ADMIN_NAME`, with `fly secrets set --stage`. Record them in **`copies/<name>.env`**, which is gitignored: `APP`, `URL`, `ADMIN_NAME`, `ADMIN_PASSWORD`, `PASSCODE`, `TAG`. They're never regenerated on a re-run, which would lock the instructor out. The `copies/` folder is Acacia's key ring.
4. **Deploy from the tag** (the default is the newest `release-*` tag). Run `git worktree add` into the session's temp dir, then `fly deploy --app you-annotate-<name> --ha=false` from the worktree, then remove the worktree. `--app` overrides the `app =` line in `fly.toml`. Deploying from a worktree means uncommitted local changes never reach a colleague's copy.
5. **Wait for the site** by polling `GET /api/texts`. The machine auto-starts.
6. **Upload the text.** Log in (`POST /api/admin/login`), then `POST /api/admin/texts` with `texts/equiano.md`. The slug is `equiano`, the title is read from Acacia's live `GET /api/texts/equiano`, and the passcode comes from `--passcode`. A 409 means it's already there, so the step is skipped.
7. **Seed the footnotes.**
   - **Fetch and filter.** `GET https://you-annotate.fly.dev/api/texts/equiano/export` (public), then a pure function `footnotes_only(export)` keeps only the `footnote` annotations and drops other layers, replies and links.
   - **Preview.** `POST /api/admin/texts/equiano/restore`. If the preview reports any `unplaced`, the script prints the problems and stops. Otherwise it applies with `?apply=true`.
   - **Why not the loader.** This copies Acacia's footnotes as they currently stand, including fixes she's made by hand in the reader. It doesn't need the gitignored notes index on hand, and footnotes keep her name as author. Restored items get the owner token `""`, so only the copy's admin can edit them, which is the intended result.
8. **Print the handoff card:** URL (`/t/equiano`), admin page, instructor code, student passcode. It's ready to paste into an email.

**`deploy <name> [--tag]`** repeats step 4 for an existing copy and updates `TAG` in its `copies/<name>.env`. Acacia's own app keeps deploying from `main` with `fly deploy --ha=false`, unchanged.

Tags are dated release tags (`release-YYYY-MM-DD`) shared across copies, rather than one tag per copy. HUMAN.md records which release each copy runs.

## Step 2: test

One test in `tests/test_api.py`, reusing its existing fixtures:
- **Setup:** a text with a footnote, a vocab note with a reply, and a link.
- **Action:** export it, run `footnotes_only`, and restore onto a fresh text.
- **Check:** only the footnote arrives.

This is the privacy-relevant behavior: Acacia's students' comments must never reach a colleague's copy. The Fly and HTTP orchestration isn't unit-tested; the real run in Verification covers it.

## Step 3: docs

- **`.gitignore`:** add `copies/`.
- **`docs/HUMAN.md`:**
  - A new **"Instructor copies"** section: a table of copies (app, URL, instructor, release; no secrets), how to make one, how to update one, and that the codes live in `copies/`.
  - Under **Next time**, add the custom-domain item. The plan for it: buy a domain such as `you-annotate.com`, add one CNAME per subdomain plus `fly certs add`. The cookie caveat: a student's `ya_token` belongs to one hostname, so switching an existing class to a new URL mid-term loses their edit rights to their old notes. Introduce the new URL at the start of a term.
  - Note that `you-annotate` keeps its name, because Fly apps can't be renamed.
- **`docs/DECISIONS.md`:** entries for
  - **Separate apps rather than in-app sections**, with Acacia's reasoning in the human column (instructor copy as handed-over packet, empowerment over SaaS, her colleagues' own texts) and the AI column covering the A/B analysis and the fact that question 5 tipped it. Flagged as a SPEC-adjacent change: SPEC calls multiple courses "a later concern", and this answers it without touching the app.
  - **Seeding footnotes from export**, not the loader.
  - **Release tags and the `copies/` key ring.**
- **`CLAUDE.md` Commands:** add the two `copies.py` lines.
- **`README.md`:** one line saying instructors can get their own copy.
- **Plan file:** save this plan to `plans/2026-10-29-instructor-copies.md`.

## Commits

These are small and separate, authored by Claude:
1. Export/restore work (step 0)
2. `copies.py` + test + gitignore
3. Docs

Then create the first `release-2026-10-29` tag. Push only if Acacia says so.

## Verification

1. `pytest` (including the new test) and `node --test tests/` pass.
2. **Real run with a throwaway copy.**
   - `copies.py create test --name "Test Instructor" --passcode test`.
   - Then open `https://you-annotate-test.fly.dev/t/equiano` and check:
     - the footnote count matches Acacia's site (currently 115)
     - there are no vocab, commentary or links
     - logging into `/admin` with the instructor code works
     - joining with the passcode `test` in a private window lets you annotate
     - Acacia's site is unchanged
   - Re-run `create test` to confirm everything gets skipped.
   - Run `copies.py deploy test` to confirm a redeploy works.
3. Afterward, `fly apps destroy you-annotate-test`. This can't be undone, but it's a throwaway app; I'll ask before running it.
4. Then Acacia creates the real copies herself, or asks me to, once she has the colleagues' names.
