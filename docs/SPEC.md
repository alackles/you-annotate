## Architecture Overview

**Web app.** Deploy to Fly.io (`you-annotate.fly.dev`). Needs real-time collaboration (multiple users annotating simultaneously), user authentication, and a persistent data layer for texts and annotations.

## Layout

Three-column layout:

- **Left margin:** Footnotes (editorial apparatus, part of the original text)
- **Center:** The text itself, with inline color-coded highlights for vocab and commentary annotations
- **Right margin:** Structural annotation markers (Roman numerals + vertical bars marking linked passages)
- **Right side panel (opens on click):** Comment threads for vocab and commentary annotations

## Text Display

- Upload a file to load a text (support common formats — decide during build based on what's available for public domain texts)
- Text renders as readable prose, organized by chapter - each chapter is its own page
- No special parsing of outlines or preludes — structure emerges from annotations, not from the text format
- Clean, readable typography. This is a tool for sustained reading, not skimming

## Annotation Layers

### 1. Structural (right margin)

Bidirectional links between two segments of text. Primary use case: linking an outline item at the top of a chapter to the passage in the body where that topic appears.

**Creating:** User selects a text segment (the "anchor," e.g., a line in the prelude), then selects the destination passage. This creates a linked pair.

**Display at destination:** Roman numeral label in the right margin + a vertical bar running the height of the passage along the right edge. No highlighting on the text itself — structural annotations live entirely in the margin so they don't compete with word-level highlights.

**Navigation:** Click the anchor text → jumps to the destination passage. Click the Roman numeral in the margin → jumps back to the anchor. Bidirectional.

**Visual:** Distinct from highlights. Margin-only. Should feel like section markers in a printed book.

### 2. Vocabulary (color-coded highlight)

Word or phrase-level highlights on the text. One distinct color.

**Creating:** Select text, choose vocabulary layer, add a comment.

**Display:** Color-coded highlight on the selected text range. Click opens a comment thread in the right side panel.

**Comment threads:** Anyone can reply. Designed for the pattern: student highlights a word they don't know → someone else (or the instructor) replies with a definition or explanation.

### 3. Commentary (color-coded highlight)

Identical interaction model to vocabulary, different color. Used for reactions, observations, interpretive notes — "this is well written," "I notice he's making a rhetorical move here," etc.

**Creating:** Select text, choose commentary layer, add a comment.

**Display:** Different color highlight from vocabulary. Click opens comment thread in right side panel.

## Footnotes (left margin)

Editorial footnotes — part of the text's published apparatus, not reader annotations.

**Creating:** Admin-only. Select a text range, add footnote content.

**Display:** Faint/grayscale, visually quiet. Marker on the text, content appears in the left margin on click or hover. Should feel like it came with the book, not like someone added it.

**Purpose:** The instructor pre-loads these from a published edition's footnotes so students can see that annotation is a standard scholarly practice, not just a classroom exercise.

## Users and Permissions

### Authentication
- Enter your name + a passcode to access a text (e.g., passcode "equiano" for the Equiano text). Each text has its own passcode, set by the admin.
- No accounts, no email, no passwords. Just name + passcode → you're in.
- View-only mode without entering anything (shareable via URL).

### Roles
- **Admin (one account, the instructor):**
  - Edit/delete any annotation from any user
  - Create footnotes
  - Upload and manage texts, set passcodes per text
  - When making annotations (vocab, commentary, structural), they look identical to student annotations, just attributed to the admin's name. Admin annotations are reader contributions, not editorial apparatus
  - Admin auth is separate — a real login (email + password or similar), not the passcode system
- **User (students):**
  - Enter name + passcode to join
  - Create annotations in all three layers
  - Edit/delete their own annotations (keyed to the name they entered)
  - Reply to any comment thread
- **Visitor (no passcode):**
  - View only. Can read text and all annotations but cannot create or modify anything

## Collaboration

Real-time. Multiple users annotating simultaneously, changes visible to everyone. Annotations attributed by user name.

## Sharing

Shareable via URL. The default view for a non-authenticated visitor is read-only — they see the text with all annotations but can't modify anything. This is important: the polished, curated version gets shared to other course sections as a reading resource.

## Design Notes

This is a reading tool. The text is the center of attention. Annotations should enhance the reading experience, not overwhelm it. The two highlight colors (vocab, commentary) and the margin markers (structural, footnotes) should be distinguishable at a glance but not loud.

The spatial separation matters: left margin = the text's own voice (footnotes), right margin = readers' structural mapping, inline highlights = readers' word-level engagement. This is a deliberate information architecture, not arbitrary placement.

## What to Defer

- **Media embedding:** Links only for now. No inline video/audio players.
- **Export:** Not in the initial build. Future feature.
- **Multiple texts/courses:** Build it to work for one text at a time. Multi-text management is a later concern.
