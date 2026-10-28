import assert from 'node:assert/strict';
import { test } from 'node:test';

import { linkParts, segment, trimSpan } from '../static/js/pure.js';

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
