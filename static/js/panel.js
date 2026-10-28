// Right-side drawer: comment threads for vocab/commentary (and footnote editing for admin),
// plus the composer for a new annotation.

import { api } from './api.js';
import { linkParts } from './pure.js';

const LAYER_NAMES = { vocab: 'Vocabulary', commentary: 'Commentary', footnote: 'Footnote' };
const PLACEHOLDERS = {
  vocab: 'What does this mean? (optional)',
  commentary: 'Your comment',
  footnote: 'Footnote text',
};

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children.filter((c) => c != null && c !== false));
  return node;
}

function formatTime(ts) {
  const date = new Date(ts.replace(' ', 'T') + 'Z'); // SQLite CURRENT_TIMESTAMP is UTC
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function richText(text) {
  return linkParts(text).map((p) =>
    p.url ? el('a', { href: p.url, textContent: p.url, target: '_blank', rel: 'noopener' }) : p.text,
  );
}

// ctx: { slug, me(), annotations(), chapterOrd(id), refresh(), onShow(ids, modeKind) }
export function createPanel(root, ctx) {
  let mode = null;       // {kind: 'threads', ids} | {kind: 'compose', layer, span}
  let editing = null;    // key of the message being edited, e.g. 'a12' or 'r5'

  function open(next) {
    mode = next;
    editing = null;
    render();
    root.classList.add('open');
    ctx.onShow(currentIds(), mode.kind);
  }

  function close() {
    mode = null;
    editing = null;
    root.classList.remove('open');
    root.replaceChildren();
    ctx.onShow([], null);
  }

  function currentIds() {
    return mode?.kind === 'threads' ? mode.ids : [];
  }

  // Re-render from fresh data without losing what the user is typing.
  function render() {
    const drafts = new Map();
    for (const t of root.querySelectorAll('textarea[data-key]')) drafts.set(t.dataset.key, t.value);
    const focused = document.activeElement?.dataset?.key;

    root.replaceChildren(
      el('header', { className: 'panel-head' },
        el('span', { textContent: mode.kind === 'compose' ? 'New annotation' : 'Comments' }),
        el('button', { className: 'panel-close', textContent: '×', title: 'Close (Esc)', onclick: close }),
      ),
      ...(mode.kind === 'compose' ? [composer()] : threads()),
    );

    for (const t of root.querySelectorAll('textarea[data-key]')) {
      if (drafts.has(t.dataset.key)) t.value = drafts.get(t.dataset.key);
      if (t.dataset.key === focused) t.focus();
    }
  }

  function threads() {
    const byId = new Map(ctx.annotations().map((a) => [a.id, a]));
    const live = mode.ids.map((id) => byId.get(id)).filter(Boolean);
    if (!live.length) return [el('p', { className: 'panel-empty', textContent: 'This annotation was deleted.' })];
    return live.map(thread);
  }

  function thread(ann) {
    const me = ctx.me();
    return el('section', { className: `thread layer-${ann.layer}` },
      el('div', { className: 'thread-kind' },
        LAYER_NAMES[ann.layer],
        el('a', { className: 'permalink', href: `#${ctx.chapterOrd(ann.chapter_id)}/a${ann.id}`, textContent: 'link', title: 'Link to this annotation' }),
      ),
      el('blockquote', { className: 'quote', textContent: ann.quote }),
      message(ann, 'a'),
      ...ann.replies.map((r) => message(r, 'r')),
      me.can_write && ann.layer !== 'footnote' && replyForm(ann),
    );
  }

  function message(item, kind) {
    const key = `${kind}${item.id}`;
    const path = kind === 'a' ? `/api/annotations/${item.id}` : `/api/replies/${item.id}`;
    const isRoot = kind === 'a';
    const meta = el('div', { className: 'meta' },
      el('strong', { textContent: item.author_name }),
      ` · ${formatTime(item.created_at)}`,
      item.updated_at && ' (edited)',
    );
    if (item.can_edit && editing !== key) {
      meta.append(
        el('button', { className: 'link-button', textContent: 'edit', onclick: () => { editing = key; render(); } }),
        el('button', {
          className: 'link-button',
          textContent: 'delete',
          onclick: async () => {
            const what = isRoot ? 'this annotation and its replies' : 'this reply';
            if (!confirm(`Delete ${what}?`)) return;
            await act(() => api('DELETE', path));
            if (isRoot) close();
          },
        }),
      );
    }
    if (editing === key) {
      const area = el('textarea', { value: item.body, rows: 3 });
      area.dataset.key = `edit-${key}`;
      return el('div', { className: 'message' }, meta, area,
        el('div', { className: 'actions' },
          el('button', { className: 'btn', textContent: 'Cancel', onclick: () => { editing = null; render(); } }),
          el('button', {
            className: 'btn primary',
            textContent: 'Save',
            onclick: async () => {
              editing = null;
              await act(() => api('PATCH', path, { body: area.value }));
            },
          }),
        ),
      );
    }
    const body = item.body
      ? el('div', { className: 'body' }, ...richText(item.body))
      : el('div', { className: 'body empty', textContent: '(no comment)' });
    return el('div', { className: 'message' }, meta, body);
  }

  function replyForm(ann) {
    const area = el('textarea', { placeholder: 'Reply…', rows: 2 });
    area.dataset.key = `reply-${ann.id}`;
    const send = async () => {
      if (!area.value.trim()) return;
      const body = area.value;
      area.value = '';
      await act(() => api('POST', `/api/annotations/${ann.id}/replies`, { body }), () => { area.value = body; });
    };
    area.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) send();
    });
    return el('div', { className: 'reply' }, area,
      el('div', { className: 'actions' }, el('button', { className: 'btn primary', textContent: 'Reply', onclick: send })),
    );
  }

  function composer() {
    const { layer, span, chapterId } = mode;
    const area = el('textarea', { placeholder: PLACEHOLDERS[layer], rows: 4 });
    area.dataset.key = 'compose';
    const save = el('button', {
      className: 'btn primary',
      textContent: 'Save',
      onclick: async () => {
        save.disabled = true;
        const payload = { chapter_id: chapterId, start: span.start, end: span.end, quote: span.quote, layer, body: area.value };
        const res = await act(() => api('POST', `/api/texts/${encodeURIComponent(ctx.slug)}/annotations`, payload));
        save.disabled = false;
        if (res) open({ kind: 'threads', ids: [res.id] });
      },
    });
    setTimeout(() => area.focus());
    return el('section', { className: `thread compose layer-${layer}` },
      el('div', { className: 'thread-kind', textContent: LAYER_NAMES[layer] }),
      el('blockquote', { className: 'quote', textContent: span.quote }),
      area,
      el('div', { className: 'actions' },
        el('button', { className: 'btn', textContent: 'Cancel', onclick: close }),
        save,
      ),
    );
  }

  // Run a write, then refresh everything; on failure show the error and run `undo`.
  async function act(fn, undo) {
    try {
      const res = await fn();
      await ctx.refresh();
      return res;
    } catch (err) {
      undo?.();
      alert(err.message);
      return null;
    }
  }

  return {
    showThreads: (ids) => open({ kind: 'threads', ids }),
    compose: (layer, chapterId, span) => open({ kind: 'compose', layer, chapterId, span }),
    close,
    isOpen: () => mode !== null,
    currentIds,
    refresh: () => { if (mode) render(); },
  };
}
