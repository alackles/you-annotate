# Collaborative Text Annotation Tool

## What This Is

A web-based collaborative annotation platform for close reading of texts. Built for a college classroom but designed as a general-purpose tool. The first text is Olaudah Equiano's *The Interesting Narrative* (public domain, 18th century), but the platform should work for any uploaded text.

The core idea: students annotate a shared text together in real time using three distinct annotation layers, each with its own visual language and interaction model. An instructor can also pre-load editorial footnotes as part of the text's own apparatus.

## Specifications

See @SPEC.md for full specs. **Do not edit SPEC.md** -- when changes arise or decisions are made regarding the layout of the app which a human might want to know, instead add to DECISIONS.md.

## Documentation

- @HUMAN.md: instructions and notes for the human (Acacia) developer - leave items here when they need human input or steps (e.g. setting up the fly.io server, testing between steps). Like a handoff document and running to-do list for the human.
- @README.md: Human-facing, written for non-coders who want to understand what the tool is and how it's used.
- @DECISIONS.md: A running list of decisions made which have, bearing on the design. Four columns: date, decision, AI contribution, Human contribution. (Either contribution may be empty, if the decision was solely AI or solely human.)
- @plans/: Whenever you enter "plan mode" and produce a plan, when the plan is approved, save it with today's date and the plan title to `plans/`. 

Freely update all these documents.

## Additional Notes

- See `/home/acacia/Documents/software/home-software/baseball-for-girls/` for an example of an existing Claude-coded Fly.io-deployed app, if desired; however, note that was the first attempt at "vibe-coding" something like this, so do not take anything in there as superceding your instincts. Use its documentation only if you run into Fly.io specific issues. 