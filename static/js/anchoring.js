// Mapping between DOM positions and character offsets into a chapter's text.
//
// Offsets count UTF-16 units over the chapter's text nodes, i.e. its textContent, which the
// server stores as `plain`. Elements with class "ui" (footnote markers etc.) are added for
// display only and are skipped, so painting them in never shifts anyone's offsets.

import { trimSpan } from './pure.js';

export function textNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement.closest('.ui') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  return nodes;
}

export function textOf(root) {
  return textNodes(root).map((n) => n.data).join('');
}

// Offset of a DOM boundary point (as found in a Range or Selection). Points before the
// root give 0 and points after it give the full length, so selections that spill out of
// the chapter are clamped.
export function offsetOf(root, container, offset) {
  const point = document.createRange();
  point.setStart(container, offset);
  let total = 0;
  for (const node of textNodes(root)) {
    if (node === container) return total + offset;
    if (point.comparePoint(node, node.length) > 0) break; // node ends after the point
    total += node.length;
  }
  return total;
}

// DOM position for an offset. At a boundary between two text nodes, `atEnd` picks the end
// of the earlier one (right for range ends) instead of the start of the later one.
export function positionAt(root, offset, atEnd = false) {
  const nodes = textNodes(root);
  let total = 0;
  for (const node of nodes) {
    const next = total + node.length;
    if (offset < next || (atEnd && offset === next)) return { node, offset: offset - total };
    total = next;
  }
  const last = nodes[nodes.length - 1];
  return { node: last, offset: last.length };
}

export function rangeFor(root, start, end) {
  const a = positionAt(root, start);
  const b = positionAt(root, end, true);
  const range = document.createRange();
  range.setStart(a.node, a.offset);
  range.setEnd(b.node, b.offset);
  return range;
}

// The current selection as {start, end, quote, rect}, trimmed of edge whitespace, or null.
export function selectionSpan(root) {
  const sel = getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return null;
  const range = sel.getRangeAt(0);
  if (!range.intersectsNode(root)) return null;
  const text = textOf(root);
  const [start, end] = trimSpan(
    text,
    offsetOf(root, range.startContainer, range.startOffset),
    offsetOf(root, range.endContainer, range.endOffset),
  );
  if (end <= start) return null;
  return { start, end, quote: text.slice(start, end), rect: range.getBoundingClientRect() };
}
