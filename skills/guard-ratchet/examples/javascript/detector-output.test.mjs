// The detector@2 output contract shared by every check-*.mjs: document shape, exit codes,
// determinism, and sort order. Detection behaviour lives in each detector's own test file.

import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { useGuardFixture } from './guard-fixture.mjs';

const GUARDS = {
  'check-architecture.mjs': 'architecture',
  'check-complexity.mjs': 'complexity',
  'check-cycles.mjs': 'cycles',
  'check-dead-code.mjs': 'dead-code',
  'check-duplication.mjs': 'duplication',
  'check-perf-shape.mjs': 'perf-shape',
  'check-tests.mjs': 'tests',
};
const TOP_LEVEL = [
  'schema', 'guard', 'tool', 'coverage', 'parse_failures', 'unsupported', 'hard', 'advisory', 'findings', 'metrics',
];

// A small repository that gives every detector something to report
function populate({ write }, root) {
  write(root, 'backend/a.js', "import { b } from './b.js';\nexport const a = () => b;\n");
  write(root, 'backend/b.js', "import { a } from './a.js';\nexport const b = 1;\nexport const c = () => a;\n");
  write(root, 'backend/db/queries/t.js', "export function reorder(db, ids) { const s = db.prepare('UPDATE t SET a = ?'); ids.forEach((i) => s.run(i)); }\n");
  write(root, 'backend/routes/list.js', "import { get } from '../db/x.js';\nexport const sql = 'SELECT id FROM t';\nget();\n");
  write(root, 'backend/db/x.js', 'export function get() {}\nexport const unusedExport = 1;\n');
  write(root, 'backend/dup1.js', 'export function one(items) {\n  let total = 0;\n  for (const item of items) {\n    if (item.enabled && item.value > 10) total += item.value * 2;\n    else total -= item.value;\n  }\n  return total;\n}\n');
  write(root, 'backend/dup2.js', 'export function two(items) {\n  let total = 0;\n  for (const item of items) {\n    if (item.enabled && item.value > 10) total += item.value * 2;\n    else total -= item.value;\n  }\n  return total;\n}\n');
  write(root, 'backend/package.json', JSON.stringify({ scripts: { test: 'node --test tests', 'test:coverage': 'node --test tests' } }));
  write(root, 'backend/tests/a.test.js', "test.only('x', () => {});\ntest.skip('y', () => {});\ninitSchema(); initSchema();\n");
  write(root, 'frontend/z.js', "import { get } from '../backend/db/x.js';\nget();\n");
  write(root, 'frontend/src/bad.js', 'export const = ;\n');
  write(root, 'frontend/src/m.js', "import './missing.js';\nexport function m(a) { return a ? 1 : 2; }\n");
}

for (const [script, guard] of Object.entries(GUARDS)) {
  const fixture = useGuardFixture(script);
  const { makeRoot, scan, run } = fixture;

  test(`${script}: prints one detector@2 document with the fixed top-level shape and tool identity`, () => {
    const root = makeRoot();
    populate(fixture, root);
    const result = run(root);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stderr, '');
    const doc = JSON.parse(result.stdout);
    assert.deepEqual(Object.keys(doc), TOP_LEVEL);
    assert.equal(doc.schema, 'guard-ratchet/detector@2');
    assert.equal(doc.guard, guard);
    assert.deepEqual(doc.tool, { name: script, version: '2.0.0' });
    assert.equal(doc.coverage.unit, 'files');
    assert.ok(Number.isInteger(doc.coverage.planned) && Number.isInteger(doc.coverage.scanned));
    assert.ok(doc.coverage.scanned <= doc.coverage.planned);
    for (const key of ['parse_failures', 'unsupported', 'hard', 'advisory', 'findings', 'metrics']) {
      assert.ok(Array.isArray(doc[key]), key);
    }
  });

  test(`${script}: two runs, also from a different temporary root, print identical output`, () => {
    const first = makeRoot();
    const second = makeRoot();
    populate(fixture, first);
    populate(fixture, second);
    const a = run(first).stdout;
    assert.equal(run(first).stdout, a);
    assert.equal(run(second).stdout, a);
  });

  test(`${script}: every array is sorted by key (then rule) and keys carry no absolute path`, () => {
    const root = makeRoot();
    populate(fixture, root);
    const { doc } = scan(root);
    for (const name of ['hard', 'advisory', 'findings', 'metrics']) {
      const ids = doc[name].map((item) => `${item.key}\u0000${item.rule ?? item.metric}`);
      assert.deepEqual(ids, [...ids].sort(), name);
    }
    assert.deepEqual(doc.parse_failures, [...doc.parse_failures].sort());
    assert.ok(!JSON.stringify(doc).includes(root));
  });

  test(`${script}: an empty scan exits 0 with planned 0`, () => {
    const { status, doc } = scan(makeRoot());
    assert.equal(status, 0);
    assert.equal(doc.coverage.planned, 0);
    assert.equal(doc.coverage.scanned, 0);
    assert.deepEqual(doc.parse_failures, []);
  });

  test(`${script}: --baseline, --update-baseline and unknown flags are usage errors (exit 2, no document)`, () => {
    const root = makeRoot();
    for (const args of [['--baseline', 'b.json'], ['--update-baseline'], ['--bogus']]) {
      const { status, doc, stderr } = scan(root, ...args);
      assert.equal(status, 2, args.join(' '));
      assert.equal(doc, null);
      assert.match(stderr, /unknown argument/);
    }
    const dir = path.dirname(fileURLToPath(import.meta.url));
    const noValue = spawnSync(process.execPath, [path.join(dir, script), '--root'], { encoding: 'utf8' });
    assert.equal(noValue.status, 2);
    assert.equal(noValue.stdout, '');
  });
}
