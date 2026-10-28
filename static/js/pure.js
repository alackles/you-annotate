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

const ROMAN = [[1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'],
  [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']];

export function roman(n) {
  let out = '';
  for (const [value, numeral] of ROMAN) {
    while (n >= value) {
      out += numeral;
      n -= value;
    }
  }
  return out;
}

// Structural links are numbered 1, 2, ... within each anchor chapter, in anchor text order,
// so an outline at the top of a chapter reads I, II, III. links -> Map(id -> number).
export function numberLinks(links) {
  const byChapter = new Map();
  for (const link of links) {
    const list = byChapter.get(link.anchor.chapter_id) ?? [];
    list.push(link);
    byChapter.set(link.anchor.chapter_id, list);
  }
  const numbers = new Map();
  for (const list of byChapter.values()) {
    list.sort((a, b) => a.anchor.start - b.anchor.start || a.id - b.id);
    list.forEach((link, i) => numbers.set(link.id, i + 1));
  }
  return numbers;
}

// Greedy interval partitioning: each [top, bottom] interval gets the lowest lane whose
// previous occupant ended more than `gap` above it. [{id, top, bottom}] -> Map(id -> lane).
export function assignLanes(intervals, gap = 4) {
  const sorted = [...intervals].sort((a, b) => a.top - b.top || a.bottom - b.bottom);
  const laneBottoms = [];
  const lanes = new Map();
  for (const iv of sorted) {
    let lane = laneBottoms.findIndex((bottom) => bottom + gap < iv.top);
    if (lane === -1) lane = laneBottoms.length;
    laneBottoms[lane] = iv.bottom;
    lanes.set(iv.id, lane);
  }
  return lanes;
}

// Push labels down just enough that none overlap. Items sorted by top: [{top, height}] -> tops.
export function stackTops(items, gap = 2) {
  let floor = -Infinity;
  return items.map(({ top, height }) => {
    const t = Math.max(top, floor);
    floor = t + height + gap;
    return t;
  });
}
