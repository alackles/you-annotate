import assert from 'node:assert/strict';
import { test } from 'node:test';

import { assignLanes, letter, linkParts, numberLinks, roman, segment, stackTops, trimSpan } from '../static/js/pure.js';

test('segment splits overlapping ranges into runs that list every covering range', () => {
  const runs = segment([
    { id: 'a', start: 0, end: 10 },
    { id: 'b', start: 5, end: 15 },
    { id: 'c', start: 20, end: 25 },
  ]);
  assert.deepEqual(runs, [
    { start: 0, end: 5, ids: ['a'] },
    { start: 5, end: 10, ids: ['a', 'b'] },
    { start: 10, end: 15, ids: ['b'] },
    { start: 20, end: 25, ids: ['c'] }, // gap 15-20 is not a run
  ]);
});

test('segment handles nesting, identical ranges, and empty ranges', () => {
  assert.deepEqual(
    segment([
      { id: 'outer', start: 0, end: 9 },
      { id: 'inner', start: 3, end: 6 },
      { id: 'twin', start: 3, end: 6 },
      { id: 'empty', start: 4, end: 4 },
    ]),
    [
      { start: 0, end: 3, ids: ['outer'] },
      { start: 3, end: 6, ids: ['outer', 'inner', 'twin'] },
      { start: 6, end: 9, ids: ['outer'] },
    ],
  );
});

test('trimSpan drops surrounding whitespace', () => {
  assert.deepEqual(trimSpan('  a word \n', 0, 10), [2, 8]);
  assert.deepEqual(trimSpan('   ', 0, 3), [3, 3]);
});

test('linkParts finds URLs without swallowing trailing punctuation', () => {
  assert.deepEqual(linkParts('See https://example.com/a_b?x=1. Or (http://x.org)'), [
    { text: 'See ' },
    { url: 'https://example.com/a_b?x=1' },
    { text: '. Or (' },
    { url: 'http://x.org' },
    { text: ')' },
  ]);
  assert.deepEqual(linkParts('no links'), [{ text: 'no links' }]);
});

test('roman numerals', () => {
  assert.deepEqual([1, 4, 9, 14, 40, 1999].map(roman), ['I', 'IV', 'IX', 'XIV', 'XL', 'MCMXCIX']);
});

test('links are numbered per anchor chapter in anchor order', () => {
  const link = (id, chapter_id, start) => ({ id, anchor: { chapter_id, start } });
  const numbers = numberLinks([link(1, 2, 50), link(2, 2, 10), link(3, 3, 0), link(4, 2, 30)]);
  assert.deepEqual(Object.fromEntries(numbers), { 2: 1, 4: 2, 1: 3, 3: 1 });
});

test('overlapping bars get separate lanes; disjoint ones reuse lane 0', () => {
  const lanes = assignLanes([
    { id: 'a', top: 0, bottom: 100 },
    { id: 'b', top: 50, bottom: 150 },
    { id: 'c', top: 120, bottom: 200 },
    { id: 'd', top: 300, bottom: 400 },
  ]);
  assert.deepEqual(Object.fromEntries(lanes), { a: 0, b: 1, c: 0, d: 0 });
});

test('stackTops nudges colliding labels down', () => {
  assert.deepEqual(stackTops([{ top: 0, height: 10 }, { top: 5, height: 10 }, { top: 40, height: 10 }], 2), [0, 12, 40]);
});

test('letters for author footnotes', () => {
  assert.deepEqual([1, 2, 26, 27, 28].map(letter), ['a', 'b', 'z', 'aa', 'ab']);
});
