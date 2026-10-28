import { api } from './api.js';
import { rangeFor, selectionSpan } from './anchoring.js';
import { layoutFootnotes, layoutLinks } from './margins.js';
import { createPanel } from './panel.js';
import { letter, numberLinks } from './pure.js';
import { insertAt, paint } from './render.js';

const $ = (id) => document.getElementById(id);
const slug = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop());
const apiBase = `/api/texts/${encodeURIComponent(slug)}`;

const LAYER_CLASS = { vocab: 'hl-vocab', commentary: 'hl-comm' };

const state = {
  text: null,          // {id, slug, title, chapters: [{id, ord, title}], me}
  chapter: null,       // {id, ord, title, html}
  cache: new Map(),    // chapter id -> chapter
  data: { annotations: [], links: [] },
  selection: null,     // span under the toolbar
  draft: null,         // span being composed, shown faintly while the composer is open
  stale: false,        // data changed while text was selected; repaint once it clears
  pendingAnchor: null, // first half of a structural link: {chapter_id, start, end, quote}
  notes: new Map(),    // footnote id -> note element in the left margin
  pinnedNote: null,    // footnote id kept open by a click
};

const panel = createPanel($('panel'), {
  slug,
  me: () => state.text.me,
  annotations: () => state.data.annotations,
  chapterOrd: (id) => state.text.chapters.find((c) => c.id === id)?.ord,
  refresh: refreshData,
  onShow: (ids, kind) => {
    document.body.classList.toggle('panel-open', kind !== null);
    if (kind !== 'compose' && state.draft) {
      state.draft = null;
      repaint();
    } else {
      markActive(ids);
    }
  },
});

async function boot() {
  try {
    state.text = await api('GET', apiBase);
  } catch (err) {
    $('chapter').textContent = `Couldn't load this text (${err.message}).`;
    return;
  }
  document.title = state.text.title;
  $('text-title').textContent = state.text.title;
  for (const c of state.text.chapters) $('chapter-select').add(new Option(c.title, c.ord));
  $('chapter-select').addEventListener('change', (e) => go(+e.target.value));
  for (const id of ['prev', 'prev-foot']) $(id).addEventListener('click', () => go(state.chapter.ord - 1));
  for (const id of ['next', 'next-foot']) $(id).addEventListener('click', () => go(state.chapter.ord + 1));
  addEventListener('hashchange', route);
  addEventListener('keydown', onKey);
  setupJoin();
  setupSelection();
  $('chapter').addEventListener('click', onChapterClick);
  $('chapter').addEventListener('mouseover', (e) => hoverFootnote(e, true));
  $('chapter').addEventListener('mouseout', (e) => hoverFootnote(e, false));
  let frame;
  new ResizeObserver(() => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(layoutMargins);
  }).observe($('chapter'));
  document.fonts?.ready.then(layoutMargins);
  renderWho();
  await refreshData();
  await route();
  connectEvents();
}

// --- Routing -------------------------------------------------------------------------

// #3 = chapter 3; #3/a42 = annotation 42 in chapter 3.
function parseHash() {
  const m = location.hash.match(/^#(\d+)(?:\/a(\d+))?$/);
  return m ? { ord: +m[1], annotation: m[2] ? +m[2] : null } : { ord: 1 };
}

function go(ord) {
  if (state.text.chapters.some((c) => c.ord === ord)) location.hash = `#${ord}`;
}

async function route() {
  const { ord, annotation } = parseHash();
  await showChapter(ord);
  const ann = annotation && state.data.annotations.find((a) => a.id === annotation);
  if (ann && ann.chapter_id === state.chapter.id) {
    if (ann.layer !== 'footnote') panel.showThreads([ann.id]);
    else pinNote(ann.id);
    revealSpan(ann.start, ann.end);
    flash(marksFor(`a${ann.id}`));
  }
}

async function showChapter(ord) {
  const chapters = state.text.chapters;
  const meta = chapters.find((c) => c.ord === ord) ?? chapters[0];
  if (!meta || state.chapter?.id === meta.id) return;
  let ch = state.cache.get(meta.id);
  if (!ch) {
    ch = await api('GET', `${apiBase}/chapters/${meta.id}`);
    state.cache.set(meta.id, ch);
  }
  state.chapter = ch;
  state.pinnedNote = null;
  getSelection().removeAllRanges();
  $('chapter-title').textContent = ch.title;
  $('chapter-select').value = ch.ord;
  const first = ch.ord === chapters[0].ord;
  const last = ch.ord === chapters[chapters.length - 1].ord;
  $('prev').disabled = $('prev-foot').hidden = first;
  $('next').disabled = $('next-foot').hidden = last;
  repaint();
  window.scrollTo(0, 0);
}

function revealSpan(start, end) {
  const rect = rangeFor($('chapter'), start, end).getBoundingClientRect();
  window.scrollTo({ top: rect.top + scrollY - innerHeight / 3, behavior: 'smooth' });
}

function marksFor(markId) {
  return [...$('chapter').querySelectorAll('.ann')].filter((s) => s.dataset.ids.split(' ').includes(markId));
}

function flash(elements) {
  for (const e of elements) e.classList.add('flash');
  setTimeout(() => elements.forEach((e) => e.classList.remove('flash')), 1600);
}

// Follow a structural link to one of its ends, switching chapters if needed.
async function jumpTo(link, end) {
  const span = link[end];
  if (span.chapter_id !== state.chapter.id) {
    history.pushState(null, '', `#${chapterOrd(span.chapter_id)}`); // back button returns here
    await showChapter(chapterOrd(span.chapter_id));
  }
  revealSpan(span.start, span.end);
  flash(end === 'anchor' ? marksFor(`l${link.id}`) : [...$('margin-right').querySelectorAll(`.struct-bar[data-link="${link.id}"]`)]);
}

function chapterOrd(chapterId) {
  return state.text.chapters.find((c) => c.id === chapterId)?.ord;
}

// --- Data and painting ---------------------------------------------------------------

async function refreshData() {
  state.data = await api('GET', `${apiBase}/annotations`);
  repaint();
  panel.refresh();
}

function connectEvents() {
  const source = new EventSource(`${apiBase}/events`);
  let timer;
  const soon = () => {
    clearTimeout(timer);
    timer = setTimeout(refreshData, 300);
  };
  source.onmessage = soon;
  source.onopen = soon; // after a reconnect, catch up on anything missed
}

function selectingInChapter() {
  const sel = getSelection();
  return sel.rangeCount > 0 && !sel.isCollapsed && sel.getRangeAt(0).intersectsNode($('chapter'));
}

function repaint() {
  if (!state.chapter) return;
  // Repainting replaces the chapter's DOM, which would destroy the user's selection.
  if (selectingInChapter()) {
    state.stale = true;
    return;
  }
  state.stale = false;
  const chapterId = state.chapter.id;
  const marks = [];
  for (const a of state.data.annotations) {
    if (a.chapter_id !== chapterId) continue;
    const classes = a.layer === 'footnote' ? ['fn-range', `fn-${a.voice}`] : [LAYER_CLASS[a.layer]];
    marks.push({ id: `a${a.id}`, start: a.start, end: a.end, classes });
  }
  for (const l of state.data.links) {
    if (l.anchor.chapter_id === chapterId) marks.push({ id: `l${l.id}`, start: l.anchor.start, end: l.anchor.end, classes: ['link-anchor'] });
  }
  if (state.draft) marks.push({ id: 'draft', ...state.draft, classes: ['draft'] });
  const pending = state.pendingAnchor;
  if (pending?.chapter_id === chapterId) marks.push({ id: 'pending', start: pending.start, end: pending.end, classes: ['pending-anchor'] });
  paint($('chapter'), state.chapter.html, marks);
  footnotesHere().forEach((fn) => {
    const marker = Object.assign(document.createElement('sup'), { className: `ui fn-mark fn-mark-${fn.voice}`, textContent: fn.number });
    marker.dataset.id = fn.id;
    insertAt($('chapter'), fn.end, marker);
  });
  markActive(panel.currentIds());
  layoutMargins();
}

// This chapter's footnotes in text order: the book's own lettered a, b, c…, editors'
// numbered 1, 2, 3…, each series counted separately.
function footnotesHere() {
  const count = { author: 0, editor: 0 };
  return state.data.annotations
    .filter((a) => a.layer === 'footnote' && a.chapter_id === state.chapter.id)
    .sort((a, b) => a.start - b.start || a.id - b.id)
    .map((a) => {
      const n = ++count[a.voice];
      return { ...a, number: a.voice === 'author' ? letter(n) : String(n) };
    });
}

function layoutMargins() {
  if (!state.chapter) return;
  state.notes = layoutFootnotes($('margin-left'), $('chapter'), footnotesHere(), {
    onEdit: (id) => panel.showThreads([id]),
  });
  if (state.pinnedNote) state.notes.get(state.pinnedNote)?.classList.add('show');
  layoutLinks($('margin-right'), $('chapter'), state.chapter.id, state.data.links, numberLinks(state.data.links), {
    chapterTitle: (id) => state.text.chapters.find((c) => c.id === id)?.title ?? 'another chapter',
    onJump: jumpTo,
    onDelete: async (link) => {
      if (!confirm('Delete this structural link?')) return;
      try {
        await api('DELETE', `/api/links/${link.id}`);
        await refreshData();
      } catch (err) {
        alert(err.message);
      }
    },
  });
}

// --- Footnotes -----------------------------------------------------------------------

function footnoteIdsAt(target) {
  const marker = target.closest('.fn-mark');
  if (marker) return [+marker.dataset.id];
  const span = target.closest('.ann.fn-range');
  return span ? annotationsAt(span).filter((a) => a.layer === 'footnote').map((a) => a.id) : [];
}

function hoverFootnote(e, entering) {
  for (const id of footnoteIdsAt(e.target)) {
    if (entering || id !== state.pinnedNote) state.notes.get(id)?.classList.toggle('show', entering);
    for (const s of marksFor(`a${id}`)) s.classList.toggle('fn-active', entering);
  }
}

function pinNote(id) {
  if (state.pinnedNote) state.notes.get(state.pinnedNote)?.classList.remove('show');
  state.pinnedNote = state.pinnedNote === id ? null : id;
  if (state.pinnedNote) state.notes.get(id)?.classList.add('show');
}

function markActive(ids) {
  const want = new Set(ids.map((id) => `a${id}`));
  for (const span of $('chapter').querySelectorAll('.ann')) {
    span.classList.toggle('active', span.dataset.ids.split(' ').some((id) => want.has(id)));
  }
}

function annotationsAt(span) {
  const byId = new Map(state.data.annotations.map((a) => [`a${a.id}`, a]));
  return span.dataset.ids.split(' ').map((id) => byId.get(id)).filter(Boolean);
}

function onChapterClick(e) {
  if (!getSelection().isCollapsed) return;
  const footnotes = footnoteIdsAt(e.target);
  if (e.target.closest('.fn-mark')) return pinNote(footnotes[0]);
  const span = e.target.closest('.ann');
  if (!span) return;
  // Highlights win over link anchors; their numeral in the margin still reaches the link.
  const threads = annotationsAt(span).filter((a) => a.layer !== 'footnote');
  if (threads.length) return panel.showThreads(threads.map((a) => a.id));
  const linkIds = span.dataset.ids.split(' ').filter((id) => id.startsWith('l')).map((id) => +id.slice(1));
  const link = state.data.links.find((l) => l.id === linkIds[0]);
  if (link) return jumpTo(link, 'dest');
  if (footnotes.length) pinNote(footnotes[0]);
}

function onKey(e) {
  if (e.key !== 'Escape') return;
  if (panel.isOpen()) panel.close();
  else if (state.pendingAnchor) cancelLink();
}

// --- Selection toolbar ---------------------------------------------------------------

function setupSelection() {
  const check = () => setTimeout(updateToolbar, 0);
  $('chapter').addEventListener('mouseup', check);
  $('chapter').addEventListener('keyup', check);
  let settle;
  document.addEventListener('selectionchange', () => {
    clearTimeout(settle);
    if (getSelection().isCollapsed) {
      hideToolbar();
      if (state.stale) repaint();
    } else {
      settle = setTimeout(updateToolbar, 500); // touch devices: wait for handles to settle
    }
  });
}

function toolbarButton(label, className, onClick) {
  const b = Object.assign(document.createElement('button'), { type: 'button', className, textContent: label });
  b.addEventListener('mousedown', (e) => e.preventDefault()); // keep the selection alive
  b.addEventListener('click', onClick);
  return b;
}

function updateToolbar() {
  const span = selectionSpan($('chapter'));
  if (!span) return hideToolbar();
  state.selection = span;
  const me = state.text.me;
  const tb = $('toolbar');
  if (!me.can_write) {
    tb.replaceChildren(toolbarButton('Join to annotate', '', () => { hideToolbar(); $('join-dialog').showModal(); }));
  } else if (state.pendingAnchor) {
    tb.replaceChildren(
      toolbarButton('Link here', 'tb-link', finishLink),
      toolbarButton('Cancel link', '', () => { hideToolbar(); cancelLink(); }),
    );
  } else {
    tb.replaceChildren(
      toolbarButton('Vocab', 'tb-vocab', () => startAnnotation('vocab')),
      toolbarButton('Comment', 'tb-comm', () => startAnnotation('commentary')),
      toolbarButton('Link…', 'tb-link', startLink),
    );
    if (me.admin) tb.append(toolbarButton('Footnote', 'tb-fn', () => startAnnotation('footnote')));
  }
  tb.hidden = false;
  const r = span.rect;
  const left = Math.min(Math.max(8, r.left + r.width / 2 - tb.offsetWidth / 2), innerWidth - tb.offsetWidth - 8);
  let top = r.top - tb.offsetHeight - 8;
  if (top < 56) top = r.bottom + 8; // would hide under the sticky top bar
  tb.style.left = `${left + scrollX}px`;
  tb.style.top = `${top + scrollY}px`;
}

function hideToolbar() {
  $('toolbar').hidden = true;
}

function takeSelection() {
  const span = state.selection;
  hideToolbar();
  getSelection().removeAllRanges();
  return span;
}

function startAnnotation(layer) {
  const span = takeSelection();
  state.draft = { start: span.start, end: span.end };
  repaint();
  panel.compose(layer, state.chapter.id, span);
}

// --- Structural links ----------------------------------------------------------------

function startLink() {
  const span = takeSelection();
  state.pendingAnchor = { chapter_id: state.chapter.id, start: span.start, end: span.end, quote: span.quote };
  const quote = span.quote.length > 60 ? `${span.quote.slice(0, 57)}…` : span.quote;
  const cancel = Object.assign(document.createElement('button'), { className: 'link-button', textContent: 'Cancel' });
  cancel.addEventListener('click', cancelLink);
  $('banner').replaceChildren(`Linking from “${quote}”. Now select the passage it points to (any chapter). `, cancel);
  $('banner').hidden = false;
  repaint();
}

async function finishLink() {
  const span = takeSelection();
  const dest = { chapter_id: state.chapter.id, start: span.start, end: span.end, quote: span.quote };
  try {
    await api('POST', `${apiBase}/links`, { anchor: state.pendingAnchor, dest });
    cancelLink();
    await refreshData();
  } catch (err) {
    alert(err.message);
  }
}

function cancelLink() {
  state.pendingAnchor = null;
  $('banner').hidden = true;
  repaint();
}

// --- Identity ------------------------------------------------------------------------

function renderWho() {
  const me = state.text.me;
  const who = $('who');
  who.replaceChildren();
  const joinButton = (label) => {
    const b = Object.assign(document.createElement('button'), { className: 'link-button', textContent: label });
    b.addEventListener('click', () => $('join-dialog').showModal());
    return b;
  };
  const prefix = (text) => Object.assign(document.createElement('span'), { className: 'who-prefix', textContent: text });
  if (me.admin) {
    who.append(`${me.name} · `, Object.assign(document.createElement('a'), { href: '/admin', textContent: 'admin' }));
  } else if (me.can_write) {
    const name = Object.assign(document.createElement('strong'), { textContent: me.name });
    who.append(prefix('Annotating as '), name, prefix(' · '), joinButton('change name'));
  } else {
    who.append(prefix('Reading as a visitor · '), joinButton('Join to annotate'));
  }
}

function setupJoin() {
  const dialog = $('join-dialog');
  const form = $('join-form');
  $('join-cancel').addEventListener('click', () => dialog.close());
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const { name, passcode } = form.elements; // not form.name: that's the form's own attribute
      state.text.me = await api('POST', `${apiBase}/join`, { name: name.value, passcode: passcode.value });
      $('join-error').textContent = '';
      passcode.value = '';
      dialog.close();
      renderWho();
      await refreshData(); // which annotations are editable has changed
    } catch (err) {
      $('join-error').textContent = err.message;
    }
  });
}

boot();
