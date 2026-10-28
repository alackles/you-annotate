// Paint annotation layers onto a fresh copy of a chapter's HTML.

import { positionAt, textNodes } from './anchoring.js';
import { segment } from './pure.js';

// marks: [{id, start, end, classes}]. Each covered run of text becomes one
// <span class="ann ..." data-ids="..."> carrying the classes of every mark over it, so
// overlapping annotations never produce nested spans.
export function paint(root, html, marks) {
  root.innerHTML = html;
  const classesOf = new Map(marks.map((m) => [m.id, m.classes]));
  const runs = segment(marks);
  let total = 0;
  let r = 0;
  for (const node of textNodes(root)) {
    const nodeStart = total;
    const nodeEnd = total + node.length;
    total = nodeEnd;
    while (r < runs.length && runs[r].end <= nodeStart) r++;
    const pieces = [];
    for (let k = r; k < runs.length && runs[k].start < nodeEnd; k++) {
      pieces.push({
        s: Math.max(runs[k].start, nodeStart) - nodeStart,
        e: Math.min(runs[k].end, nodeEnd) - nodeStart,
        ids: runs[k].ids,
      });
    }
    // Right to left, so splitting off a later piece leaves earlier offsets valid.
    for (const p of pieces.reverse()) {
      if (p.e < node.length) node.splitText(p.e);
      const piece = p.s > 0 ? node.splitText(p.s) : node;
      const span = document.createElement('span');
      span.className = ['ann', ...new Set(p.ids.flatMap((id) => classesOf.get(id)))].join(' ');
      span.dataset.ids = p.ids.join(' ');
      piece.replaceWith(span);
      span.append(piece);
    }
  }
}

// Insert a display-only element (it should carry class "ui") at a text offset.
export function insertAt(root, offset, el) {
  const { node, offset: o } = positionAt(root, offset, true);
  const range = document.createRange();
  range.setStart(node, o);
  range.insertNode(el);
}
