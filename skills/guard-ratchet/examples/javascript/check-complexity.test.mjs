import test from 'node:test';
import assert from 'node:assert/strict';

import { useGuardFixture } from './guard-fixture.mjs';

const { makeRoot, write, scan } = useGuardFixture('check-complexity.mjs');

// A function with `branches` ifs: complexity = branches + 1
const branchy = (name, branches) => `export function ${name}(x) {\n${
  Array.from({ length: branches }, (_, i) => `  if (x === ${i}) return ${i};`).join('\n')}\n  return -1;\n}\n`;

const valueOf = (doc, key) => doc.metrics.find((m) => m.key === key)?.value;

test('a function with N ifs scores N + 1, with no threshold applied', () => {
  const root = makeRoot();
  write(root, 'backend/n.js', [0, 1, 29, 30, 45].map((n) => branchy(`f${n}`, n)).join(''));
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  for (const n of [0, 1, 29, 30, 45]) assert.equal(valueOf(doc, `backend/n.js#f${n}`), n + 1);
  assert.deepEqual(doc.findings, []);
  assert.deepEqual(doc.hard, []);
});

test('every function gets a fn-complexity metric with path and line, and coverage counts them', () => {
  const root = makeRoot();
  write(root, 'backend/a.js', 'export function a() {}\n\nexport const b = () => 1;\n');
  write(root, 'backend/c.js', 'export function c(x) { return x ? 1 : 2; }\n');
  const { doc } = scan(root);
  assert.deepEqual(doc.metrics, [
    { metric: 'fn-complexity', key: 'backend/a.js#a', path: 'backend/a.js', line: 1, value: 1 },
    { metric: 'fn-complexity', key: 'backend/a.js#b', path: 'backend/a.js', line: 3, value: 1 },
    { metric: 'fn-complexity', key: 'backend/c.js#c', path: 'backend/c.js', line: 1, value: 2 },
  ]);
  assert.deepEqual(doc.coverage, { planned: 2, scanned: 2, unit: 'files', functions: 3 });
});

test('loops, catch, ternary, logical operators and switch cases each count one; default does not', () => {
  const root = makeRoot();
  write(root, 'backend/mixed.js', `export function mixed(a, b) {
  if (a && b) return 1;
  for (const x of a) {}
  while (b) { break; }
  try {} catch (e) {}
  const t = a ? 1 : 2;
  switch (a) { case 1: break; case 2: break; default: break; }
  return a ?? b;
}
`);
  assert.equal(valueOf(scan(root).doc, 'backend/mixed.js#mixed'), 10);
});

test('decisions of a private helper with exactly one caller are added back to the caller', () => {
  const root = makeRoot();
  write(root, 'backend/legacy.js', `function step(x) {
  if (x === 1) return 1;
  if (x === 2) return 2;
  return 0;
}
export function legacy(x) {
  step(x);
  if (x === 3) return 3;
  return -1;
}
`);
  const { doc } = scan(root);
  assert.equal(valueOf(doc, 'backend/legacy.js#step'), 3);
  assert.equal(valueOf(doc, 'backend/legacy.js#legacy'), 4);
});

test('a helper called from two places is scored alone and the callers do not carry it', () => {
  const root = makeRoot();
  write(root, 'backend/legacy.js', `function step(x) {
  if (x === 1) return 1;
  return 0;
}
export function legacy(x) {
  step(x);
  return -1;
}
export function other(x) {
  step(x);
  return -1;
}
`);
  const { doc } = scan(root);
  assert.equal(valueOf(doc, 'backend/legacy.js#step'), 2);
  assert.equal(valueOf(doc, 'backend/legacy.js#legacy'), 1);
  assert.equal(valueOf(doc, 'backend/legacy.js#other'), 1);
});

test('exported helpers, method calls and callbacks are not add-back targets', () => {
  const root = makeRoot();
  write(root, 'backend/a.js', `export function exportedStep(x) { if (x) return 1; return 0; }
export function callerA(x) { exportedStep(x); }
function methodStep(x) { if (x) return 1; return 0; }
const obj = { methodStep };
export function callerB(x) { obj.methodStep(x); }
function callbackStep(x) { if (x) return 1; return 0; }
export function callerC(items) { items.map(callbackStep); }
`);
  const { doc } = scan(root);
  assert.equal(valueOf(doc, 'backend/a.js#callerA'), 1);
  assert.equal(valueOf(doc, 'backend/a.js#callerB'), 1);
  assert.equal(valueOf(doc, 'backend/a.js#callerC'), 1);
});

test('a function defined inside its only caller is not added twice', () => {
  const root = makeRoot();
  write(root, 'backend/a.js', 'export function outer(x) {\n  function inner(y) { if (y) return 1; return 0; }\n  return inner(x);\n}\n');
  const { doc } = scan(root);
  assert.equal(valueOf(doc, 'backend/a.js#outer'), 2);
  assert.equal(valueOf(doc, 'backend/a.js#inner'), 2);
});

test('anonymous functions are keyed "outer>call", and their decisions count in the outer function', () => {
  const root = makeRoot();
  write(root, 'backend/m.js', [
    'export function match(items) { return items.filter((x) => x.a && x.b); }',
    "app.post('/x', (req) => { if (req) return 1; return 0; });",
    'export default function () { return 1; }',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.equal(valueOf(doc, 'backend/m.js#match'), 2);
  assert.equal(valueOf(doc, 'backend/m.js#match>filter'), 2);
  assert.equal(valueOf(doc, 'backend/m.js#(top-level)>post'), 2);
  assert.equal(valueOf(doc, 'backend/m.js#(default)'), 1);
});

test('same-named functions in one file get ~2 in order of appearance', () => {
  const root = makeRoot();
  write(root, 'backend/d.js', `export function a() { function dup() { if (1) return 1; } return dup; }
export function b() { function dup() {} return dup; }
`);
  const { doc } = scan(root);
  assert.equal(valueOf(doc, 'backend/d.js#dup'), 2);
  assert.equal(valueOf(doc, 'backend/d.js#dup~2'), 1);
});

test('inserting unrelated code and functions before a function does not change existing keys or values', () => {
  const root = makeRoot();
  const callback = Array.from({ length: 31 }, (_, i) => `    if (x === ${i}) return ${i};`).join('\n');
  const source = (extra) => `${extra}export function match(items) {\n  return items.filter((x) => {\n${callback}\n    return false;\n  });\n}\n`;
  write(root, 'backend/match.js', source(''));
  const before = scan(root).doc.metrics;
  write(root, 'backend/match.js', source('// unrelated comment\nsetTimeout(() => {}, 0);\nfunction unrelated(a) { return a || 1; }\n'));
  const after = scan(root).doc.metrics;
  for (const metric of before) {
    const same = after.find((m) => m.key === metric.key);
    assert.equal(same?.value, metric.value, metric.key);
  }
  assert.ok(before.some((m) => m.key === 'backend/match.js#match>filter'));
  assert.ok(after.length > before.length);
});

test('a file that does not parse lands in parse_failures; the rest is still measured', () => {
  const root = makeRoot();
  write(root, 'backend/bad.js', 'export const = ;\n');
  write(root, 'backend/ok.js', 'export function ok() {}\n');
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  assert.deepEqual(doc.parse_failures, ['backend/bad.js']);
  assert.deepEqual(doc.coverage, { planned: 2, scanned: 1, unit: 'files', functions: 1 });
  assert.equal(valueOf(doc, 'backend/ok.js#ok'), 1);
});

test('an empty scan reports planned 0 and no floor is applied', () => {
  const { status, doc } = scan(makeRoot());
  assert.equal(status, 0);
  assert.deepEqual(doc.coverage, { planned: 0, scanned: 0, unit: 'files', functions: 0 });
  assert.deepEqual(doc.metrics, []);
});

test('dependency, build and dot directories are skipped, and --ignore drops matching paths', () => {
  const root = makeRoot();
  write(root, 'src/a.js', 'export function a() {}\n');
  write(root, 'node_modules/p/bad.js', 'export const = ;\n');
  write(root, 'dist/out.js', 'export function out() {}\n');
  write(root, '.hidden/h.js', 'export function h() {}\n');
  write(root, 'legacy/old/o.js', 'export function o() {}\n');
  write(root, 'legacy/keep.js', 'export function keep() {}\n');
  const all = scan(root).doc;
  assert.deepEqual(all.metrics.map((m) => m.key), ['legacy/keep.js#keep', 'legacy/old/o.js#o', 'src/a.js#a']);
  const ignored = scan(root, '--ignore', 'legacy/old').doc;
  assert.deepEqual(ignored.metrics.map((m) => m.key), ['legacy/keep.js#keep', 'src/a.js#a']);
  assert.equal(ignored.coverage.planned, 2);
});
