// Margin layout, measured from where passages actually render.
// Left margin: footnote notes (hidden until hovered or pinned).
// Right margin: structural links, as a bar + numeral beside each destination passage and a
// faint numeral beside each anchor.

import { rangeFor } from './anchoring.js';
import { assignLanes, roman, stackTops } from './pure.js';

const LANE_PX = 10;
const LABEL_PX = 18; // approximate height of a margin label, for collision stacking

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

// Vertical extent of a passage relative to `margin`'s top edge, or null if not rendered.
function extent(root, margin, start, end) {
  const rects = [...rangeFor(root, start, end).getClientRects()].filter((r) => r.width > 0 && r.height > 0);
  if (!rects.length) return null;
  const base = margin.getBoundingClientRect().top;
  return {
    top: Math.min(...rects.map((r) => r.top)) - base,
    bottom: Math.max(...rects.map((r) => r.bottom)) - base,
  };
}

// footnotes: [{id, number, body, can_edit}] for this chapter, markers already in `root`.
// Returns Map(id -> note element).
export function layoutFootnotes(margin, root, footnotes, { onEdit }) {
  margin.replaceChildren();
  const notes = new Map();
  const base = margin.getBoundingClientRect().top;
  for (const fn of footnotes) {
    const marker = root.querySelector(`.fn-mark[data-id="${fn.id}"]`);
    if (!marker) continue;
    const note = el('div', { className: 'fn-note' },
      el('span', { className: 'fn-num', textContent: `${fn.number}. ` }),
      fn.body,
    );
    if (fn.can_edit) {
      note.append(' ', el('button', { className: 'link-button fn-edit', textContent: 'edit', onclick: () => onEdit(fn.id) }));
    }
    note.style.top = `${marker.getBoundingClientRect().top - base}px`;
    margin.append(note);
    notes.set(fn.id, note);
  }
  return notes;
}

// links: all links for the text; numbers: Map(id -> number) from numberLinks.
export function layoutLinks(margin, root, chapterId, links, numbers, { chapterTitle, onJump, onDelete }) {
  margin.replaceChildren();

  const dests = [];
  for (const link of links) {
    if (link.dest.chapter_id !== chapterId) continue;
    const ext = extent(root, margin, link.dest.start, link.dest.end);
    if (ext) dests.push({ link, ...ext });
  }
  const lanes = assignLanes(dests.map((d) => ({ id: d.link.id, top: d.top, bottom: d.bottom })));
  const laneCount = Math.max(0, ...lanes.values()) + 1;

  for (const d of dests) {
    const x = lanes.get(d.link.id) * LANE_PX;
    const numeral = roman(numbers.get(d.link.id));
    const from = d.link.anchor.chapter_id === chapterId ? '' : ` in ${chapterTitle(d.link.anchor.chapter_id)}`;
    const bar = el('div', { className: 'struct-bar', style: `top:${d.top}px;height:${d.bottom - d.top}px;left:${x}px` });
    bar.dataset.link = d.link.id;
    margin.append(
      bar,
      label(d.link, numeral, `Linked from “${d.link.anchor.quote}”${from}. Click to go there.`,
        () => onJump(d.link, 'anchor'), onDelete, 'struct-num', `top:${d.top}px;left:${x + 6}px`),
    );
  }

  const anchors = [];
  for (const link of links) {
    if (link.anchor.chapter_id !== chapterId) continue;
    const ext = extent(root, margin, link.anchor.start, link.anchor.end);
    if (ext) anchors.push({ link, top: ext.top, height: LABEL_PX });
  }
  anchors.sort((a, b) => a.top - b.top);
  const tops = stackTops(anchors);
  const anchorX = laneCount * LANE_PX + 34;
  anchors.forEach(({ link }, i) => {
    const to = link.dest.chapter_id === chapterId ? '' : ` in ${chapterTitle(link.dest.chapter_id)}`;
    margin.append(label(link, `→ ${roman(numbers.get(link.id))}`, `Go to linked passage${to}: “${link.dest.quote}”`,
      () => onJump(link, 'dest'), onDelete, 'struct-anchor-num', `top:${tops[i]}px;left:${anchorX}px`));
  });
}

function label(link, text, title, onClick, onDelete, className, style) {
  const wrap = el('div', { className: `struct-label ${className}`, style });
  wrap.dataset.link = link.id;
  wrap.append(el('button', { className: 'struct-go', textContent: text, title, onclick: onClick }));
  if (link.can_edit) {
    wrap.append(el('button', { className: 'struct-del', textContent: '×', title: 'Delete this link', onclick: () => onDelete(link) }));
  }
  return wrap;
}
