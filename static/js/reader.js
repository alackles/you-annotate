import { api } from './api.js';
import { rangeFor, selectionSpan } from './anchoring.js';
import { createPanel } from './panel.js';
import { paint } from './render.js';

const $ = (id) => document.getElementById(id);
const slug = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop());
const apiBase = `/api/texts/${encodeURIComponent(slug)}`;

const LAYER_CLASS = { vocab: 'hl-vocab', commentary: 'hl-comm', footnote: 'fn-range' };

const state = {
  text: null,          // {id, slug, title, chapters: [{id, ord, title}], me}
  chapter: null,       // {id, ord, title, html}
  cache: new Map(),    // chapter id -> chapter
  data: { annotations: [], links: [] },
  selection: null,     // span under the toolbar
  draft: null,         // span being composed, shown faintly while the composer is open
  stale: false,        // data changed while text was selected; repaint once it clears
};

const panel = createPanel($('panel'), {
  slug,
  me: () => state.text.me,
  annotations: () => state.data.annotations,
  chapterOrd: (id) => state.text.chapters.find((c) => c.id === id)?.ord,
  refresh: refreshData,
  onShow: (ids, kind) => {
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
    revealSpan(ann.start, ann.end, `a${ann.id}`);
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

// Scroll a passage into view and briefly flash the marks with this id.
function revealSpan(start, end, markId) {
  const rect = rangeFor($('chapter'), start, end).getBoundingClientRect();
  window.scrollTo({ top: rect.top + scrollY - innerHeight / 3, behavior: 'smooth' });
  if (!markId) return;
  const spans = [...$('chapter').querySelectorAll('.ann')].filter((s) => s.dataset.ids.split(' ').includes(markId));
  for (const s of spans) s.classList.add('flash');
  setTimeout(() => spans.forEach((s) => s.classList.remove('flash')), 1600);
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
    if (a.chapter_id === chapterId) marks.push({ id: `a${a.id}`, start: a.start, end: a.end, classes: [LAYER_CLASS[a.layer]] });
  }
  if (state.draft) marks.push({ id: 'draft', ...state.draft, classes: ['draft'] });
  paint($('chapter'), state.chapter.html, marks);
  markActive(panel.currentIds());
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
  const span = e.target.closest('.ann');
  if (!span) return;
  const threads = annotationsAt(span).filter((a) => a.layer !== 'footnote');
  if (threads.length) panel.showThreads(threads.map((a) => a.id));
}

function onKey(e) {
  if (e.key !== 'Escape') return;
  if (panel.isOpen()) panel.close();
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
  } else {
    tb.replaceChildren(
      toolbarButton('Vocab', 'tb-vocab', () => startAnnotation('vocab')),
      toolbarButton('Comment', 'tb-comm', () => startAnnotation('commentary')),
    );
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
  if (me.admin) {
    who.append(`${me.name} · `, Object.assign(document.createElement('a'), { href: '/admin', textContent: 'admin' }));
  } else if (me.can_write) {
    const name = Object.assign(document.createElement('strong'), { textContent: me.name });
    who.append('Annotating as ', name, ' · ', joinButton('change name'));
  } else {
    who.append('Reading as a visitor · ', joinButton('Join to annotate'));
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
