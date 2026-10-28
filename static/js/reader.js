import { api } from './api.js';

const $ = (id) => document.getElementById(id);
const slug = decodeURIComponent(location.pathname.split('/').filter(Boolean).pop());

const state = {
  text: null,         // {id, slug, title, chapters: [{id, ord, title}], me}
  chapter: null,      // {id, ord, title, html}
  cache: new Map(),   // chapter id -> chapter
};

async function boot() {
  try {
    state.text = await api('GET', `/api/texts/${encodeURIComponent(slug)}`);
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
  await route();
}

// #3 = chapter 3; #3/a42 = annotation 42 in chapter 3; #3/l7 = structural link 7.
function parseHash() {
  const m = location.hash.match(/^#(\d+)(?:\/([al])(\d+))?$/);
  return m ? { ord: +m[1], kind: m[2], id: m[3] ? +m[3] : null } : { ord: 1 };
}

function go(ord) {
  if (state.text.chapters.some((c) => c.ord === ord)) location.hash = `#${ord}`;
}

async function route() {
  const { ord } = parseHash();
  await showChapter(ord);
}

async function showChapter(ord) {
  const chapters = state.text.chapters;
  const meta = chapters.find((c) => c.ord === ord) ?? chapters[0];
  if (!meta || state.chapter?.id === meta.id) return;
  let ch = state.cache.get(meta.id);
  if (!ch) {
    ch = await api('GET', `/api/texts/${encodeURIComponent(slug)}/chapters/${meta.id}`);
    state.cache.set(meta.id, ch);
  }
  state.chapter = ch;
  $('chapter-title').textContent = ch.title;
  $('chapter').innerHTML = ch.html;
  $('chapter-select').value = ch.ord;
  const first = ch.ord === chapters[0].ord;
  const last = ch.ord === chapters[chapters.length - 1].ord;
  $('prev').disabled = $('prev-foot').hidden = first;
  $('next').disabled = $('next-foot').hidden = last;
  window.scrollTo(0, 0);
}

boot();
