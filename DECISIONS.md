# Decisions

| Date | Decision | AI contribution | Human contribution |
|---|---|---|---|
| 2026-10-28 | Data model is multi-text from day one (texts have IDs; annotations, footnotes, and passcodes belong to a text), but the UI is built for one text at a time. | Spotted the tension between SPEC's "multiple texts deferred" and its per-text passcodes and text management; recommended a schema that supports multiple texts from day one, since adding a text ID later would mean a migration. | Approved. |
| 2026-10-28 | Annotation ownership is tied to a browser token, not just the entered name. On joining, the browser gets a random token; each annotation stores it, and only that token (or the admin) can edit/delete it. Names are not reserved: anyone can join as any name, and duplicate display names are allowed. Clearing cookies or switching devices loses edit rights to past annotations. | Flagged that SPEC's name-keyed ownership lets anyone edit anyone's annotations by typing their name; proposed a browser token; laid out token-owns-annotations vs. token-claims-name and recommended the former. | Chose the browser token, and the token-owns-annotations option. |
