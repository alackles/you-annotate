// DOM-free helpers, kept separate so `node --test` can exercise them.

// Cut possibly-overlapping ranges into non-overlapping runs, each listing every range
// that covers it. [{id, start, end}] -> [{start, end, ids}], in order, covered runs only.
export function segment(ranges) {
  const valid = ranges.filter((r) => r.end > r.start);
  const cuts = [...new Set(valid.flatMap((r) => [r.start, r.end]))].sort((a, b) => a - b);
  const runs = [];
  for (let i = 0; i < cuts.length - 1; i++) {
    const start = cuts[i];
    const end = cuts[i + 1];
    const ids = valid.filter((r) => r.start <= start && r.end >= end).map((r) => r.id);
    if (ids.length) runs.push({ start, end, ids });
  }
  return runs;
}

// Shrink [start, end) so it neither starts nor ends on whitespace.
export function trimSpan(text, start, end) {
  while (start < end && /\s/.test(text[start])) start++;
  while (end > start && /\s/.test(text[end - 1])) end--;
  return [start, end];
}

const URL_RE = /\bhttps?:\/\/[^\s<>"]*[^\s<>".,;:!?'")\]]/g;

// Split plain text into [{text}] and [{url}] parts so links can be built as DOM nodes.
export function linkParts(text) {
  const parts = [];
  let last = 0;
  for (const m of text.matchAll(URL_RE)) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index) });
    parts.push({ url: m[0] });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}
