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
  setupJoin();
  renderWho();
  await route();
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
      state.text.me = await api('POST', `/api/texts/${encodeURIComponent(slug)}/join`, {
        name: name.value,
        passcode: passcode.value,
      });
      $('join-error').textContent = '';
      passcode.value = '';
      dialog.close();
      renderWho();
      onIdentityChange();
    } catch (err) {
      $('join-error').textContent = err.message;
    }
  });
}

// Joining changes which annotations show edit buttons; later stages hook in here.
function onIdentityChange() {}

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
