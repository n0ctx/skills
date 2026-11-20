import test from 'node:test';
import assert from 'node:assert/strict';

import { useGuardFixture, ruleKeys } from './guard-fixture.mjs';

const { makeRoot, write, scan } = useGuardFixture('check-perf-shape.mjs');

const QUERIES = `export function reorder(db, ids) {
  const stmt = db.prepare('UPDATE t SET sort = ? WHERE id = ?');
  ids.forEach((id, i) => stmt.run(i, id));
  const all = db.prepare('SELECT * FROM t').all();
  const map = new Map(all.map((r) => [r.id, r]));
  for (const id of ids) map.get(id);
}
`;

function fixture() {
  const root = makeRoot();
  write(root, 'backend/db/queries/t.js', QUERIES);
  write(root, 'backend/routes/list.js', "export const sql = 'SELECT id FROM t';\n");
  write(root, 'backend/services/import-export.js', "export const sql = 'SELECT * FROM t';\n");
  write(root, 'frontend/src/grid.js', [
    'export function grid(rows, cols) {',
    '  for (const r of rows) { for (const c of cols) { let n = 0; while (n < 3) n += 1; } }',
    '}',
    '',
  ].join('\n'));
  return root;
}

const BASE = [
  'loop-query:backend/db/queries/t.js#reorder#stmt.run',
  'unbounded-select:backend/routes/list.js#(top-level)#SELECT id FROM t',
];

test('baseline repository: a per-item write and one unbounded SELECT; nested loops, in-memory matching and the exempt file are quiet', () => {
  const { status, doc } = scan(fixture());
  assert.equal(status, 0);
  assert.deepEqual(ruleKeys(doc.findings), BASE);
  assert.deepEqual(doc.hard, []);
  assert.deepEqual(doc.findings[0], {
    rule: 'loop-query',
    key: 'backend/db/queries/t.js#reorder#stmt.run',
    count: 1,
    path: 'backend/db/queries/t.js',
    line: 3,
    message: 'per-item query stmt.run inside a loop; query once and match in memory',
  });
});

test('business code calling a query-layer function inside a loop or an array-iteration callback is a loop-query finding', () => {
  const root = fixture();
  write(root, 'backend/services/items.js', [
    "import { getById } from '../db/queries/items.js';",
    "import * as q from '../db/queries/tags.js';",
    'export const load = (ids) => ids.map((id) => getById(id));',
    'export function tags(ids) { for (const id of ids) q.listTags(id); }',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  const keys = ruleKeys(doc.findings);
  assert.ok(keys.includes('loop-query:backend/services/items.js#load#getById'));
  assert.ok(keys.includes('loop-query:backend/services/items.js#tags#q.listTags'));
});

test('a source evaluated in the loop header runs once and is not a loop-query', () => {
  const root = fixture();
  write(root, 'backend/services/once.js', [
    "import { reorder } from '../db/queries/t.js';",
    'export function once(db, ids) {',
    '  for (const r of reorder(db, ids)) use(r);',
    '  return reorder(db, ids).map((r) => r.id);',
    '}',
    '',
  ].join('\n'));
  assert.deepEqual(ruleKeys(scan(root).doc.findings), BASE);
});

test('adding an unrelated function before the query function does not change finding keys', () => {
  const root = fixture();
  write(root, 'backend/db/queries/t.js', `export function unrelated() {}\n${QUERIES}`);
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), BASE);
  assert.equal(doc.findings[0].line, 4);
});

test('three nested loops whose innermost body uses an outer loop variable is a hard deep-loop item', () => {
  const root = fixture();
  write(root, 'frontend/src/deep.js', [
    'export function deep(a, b, c) {',
    '  for (const x of a) { b.forEach((y) => { for (const z of c) { if (z === x) return; } }); }',
    '}',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.hard), ['deep-loop:frontend/src/deep.js#deep#x']);
  assert.equal(doc.hard[0].line, 2);
  assert.match(doc.hard[0].message, /nested 3 deep/);
  assert.deepEqual(ruleKeys(doc.findings), BASE);
});

test('two nested loops that share a variable, and three levels that use no outer variable, are not reported', () => {
  const root = fixture();
  write(root, 'frontend/src/shallow.js', [
    'export function two(a, b) { for (const x of a) { for (const y of b) { if (x === y) return; } } }',
    'export function three(a, b, c) { for (const x of a) { for (const y of b) { for (const z of c) { use(z); } } } }',
    '',
  ].join('\n'));
  assert.deepEqual(scan(root).doc.hard, []);
});

test('batch writes of a prepared statement inside a transaction are not reported, but per-item reads there are', () => {
  const root = fixture();
  write(root, 'backend/db/queries/batch.js', [
    "import db from '../index.js';",
    'function insertAll(stmt, rows) { for (const r of rows) stmt.run(r); }',
    'export function save(rows) {',
    "  const stmt = db.prepare('INSERT INTO t VALUES (?)');",
    "  const read = db.prepare('SELECT * FROM t WHERE id = ?');",
    '  db.transaction(() => {',
    '    insertAll(stmt, rows);',
    '    rows.forEach((r) => stmt.run(r));',
    '    for (const r of rows) read.get(r);',
    '  })();',
    '}',
    '',
  ].join('\n'));
  const keys = ruleKeys(scan(root).doc.findings);
  assert.ok(keys.includes('loop-query:backend/db/queries/batch.js#save#read.get'));
  assert.ok(!keys.some((k) => k.includes('stmt.run') && k.includes('batch.js')));
});

test('pure functions in the query directory are not queries; a function that wraps a real query is', () => {
  const root = fixture();
  write(root, 'backend/db/queries/items.js', [
    "import db from '../index.js';",
    'export function normalize(v) { return Number(v) || 1; }',
    "export function getById(id) { return db.prepare('SELECT * FROM items WHERE id = ?').get(id); }",
    'export function getViaHelper(id) { return getById(id); }',
    '',
  ].join('\n'));
  write(root, 'backend/services/items.js', [
    "import { normalize, getViaHelper } from '../db/queries/items.js';",
    'export function load(ids) { for (const id of ids) { normalize(id); getViaHelper(id); } }',
    '',
  ].join('\n'));
  const keys = ruleKeys(scan(root).doc.findings);
  assert.ok(keys.includes('loop-query:backend/services/items.js#load#getViaHelper'));
  assert.ok(!keys.some((k) => k.endsWith('#normalize')));
});

test('db-read and db-write effects propagate through local functions and across modules, so N+1 is still caught', () => {
  const root = fixture();
  write(root, 'backend/db/index.js', 'export default {};\n');
  write(root, 'backend/db/queries/read.js', [
    "import db from '../index.js';",
    "export function byId(id) { return db.prepare('SELECT * FROM items WHERE id = ?').get(id); }",
    '',
  ].join('\n'));
  write(root, 'backend/db/queries/write.js', [
    "import db from '../index.js';",
    "export function save(item) { return db.prepare('INSERT INTO items VALUES (?)').run(item); }",
    '',
  ].join('\n'));
  write(root, 'backend/db/queries/facade.js', [
    "import * as reads from './read.js';",
    "import { save } from './write.js';",
    'export function loadOne(id) { return reads.byId(id); }',
    'export function saveOne(item) { return save(item); }',
    '',
  ].join('\n'));
  write(root, 'backend/services/repeat.js', [
    "import { loadOne, saveOne } from '../db/queries/facade.js';",
    'export function repeat(ids) { for (const id of ids) { loadOne(id); saveOne(id); } }',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  const keys = ruleKeys(doc.findings);
  assert.ok(keys.includes('loop-query:backend/services/repeat.js#repeat#loadOne'));
  assert.ok(keys.includes('loop-query:backend/services/repeat.js#repeat#saveOne'));
  assert.equal(doc.coverage.db_read_exports, 3);
  assert.equal(doc.coverage.db_write_exports, 3);
});

test('a default-exported database function is still recognised as a query', () => {
  const root = fixture();
  write(root, 'backend/db/index.js', 'export default {};\n');
  write(root, 'backend/db/queries/default-read.js', [
    "import db from '../index.js';",
    "export default function readById(id) { return db.prepare('SELECT * FROM items WHERE id = ?').get(id); }",
    '',
  ].join('\n'));
  write(root, 'backend/services/default-read.js', [
    "import readById from '../db/queries/default-read.js';",
    'export function load(ids) { for (const id of ids) readById(id); }',
    '',
  ].join('\n'));
  const keys = ruleKeys(scan(root).doc.findings);
  assert.ok(keys.includes('loop-query:backend/services/default-read.js#load#readById'));
});

test('a computed method name such as db["prepare"] is analysed rather than crashing the detector', () => {
  const root = fixture();
  write(root, 'backend/db/index.js', 'export default {};\n');
  write(root, 'backend/db/queries/computed.js', [
    "import db from '../index.js';",
    "export function byId(id) { return db['prepare']('SELECT * FROM items WHERE id = ?').get(id); }",
    '',
  ].join('\n'));
  write(root, 'backend/services/computed.js', [
    "import { byId } from '../db/queries/computed.js';",
    'export function load(ids) { for (const id of ids) byId(id); }',
    '',
  ].join('\n'));
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  assert.ok(ruleKeys(doc.findings).includes('loop-query:backend/services/computed.js#load#byId'));
});

test('a repeated loop-query in one function gets ~2 in order of appearance', () => {
  const root = fixture();
  write(root, 'backend/services/twice.js', [
    "import { getById } from '../db/queries/items.js';",
    'export function twice(ids) {',
    '  for (const id of ids) getById(id);',
    '  for (const id of ids) getById(id);',
    '}',
    '',
  ].join('\n'));
  const keys = ruleKeys(scan(root).doc.findings);
  assert.ok(keys.includes('loop-query:backend/services/twice.js#twice#getById'));
  assert.ok(keys.includes('loop-query:backend/services/twice.js#twice#getById ~2'));
});

test('a per-item prepare in a loop, and a SELECT with neither WHERE nor LIMIT, are findings; filtered SELECTs and other directories are not', () => {
  const root = fixture();
  write(root, 'backend/services/load.js', [
    "export function load(db, ids) { for (const id of ids) db.prepare('SELECT * FROM t WHERE id = ?').get(id); }",
    'export const sql = `SELECT name FROM t ORDER BY name`;',
    "export const filtered = 'SELECT name FROM t WHERE id = 1';",
    "export const limited = 'SELECT name FROM t LIMIT 5';",
    '',
  ].join('\n'));
  write(root, 'backend/lib/free.js', "export const free = 'SELECT name FROM t';\n");
  const keys = ruleKeys(scan(root).doc.findings);
  assert.ok(keys.includes('loop-query:backend/services/load.js#load#db.prepare'));
  assert.ok(keys.includes('unbounded-select:backend/services/load.js#(top-level)#SELECT name FROM t ORDER BY name'));
  assert.ok(!keys.some((k) => k.includes('WHERE id = 1') || k.includes('LIMIT 5') || k.includes('backend/lib/')));
});

test('a guard-allow marker covers the statements right after it, and is listed as advisory', () => {
  const root = fixture();
  write(root, 'backend/services/seed.js', [
    "import { getById } from '../db/queries/items.js';",
    'export function seed(ids) {',
    '  // guard-allow(perf-shape): fixed small table',
    '  const first = ids[0];',
    '  for (const id of ids) getById(id, first);',
    '',
    '  for (const id of ids) getById(id);',
    '}',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  const keys = ruleKeys(doc.findings).filter((k) => k.includes('seed.js'));
  assert.deepEqual(keys, ['loop-query:backend/services/seed.js#seed#getById']);
  assert.equal(doc.findings.find((f) => f.key.includes('seed.js')).line, 7);
  assert.deepEqual(doc.advisory.map((a) => [a.rule, a.path, a.line, a.message]),
    [['guard-allow', 'backend/services/seed.js', 3, 'fixed small table']]);
  assert.deepEqual(doc.hard, []);
});

test('guard-allow without a reason, with a wrong guard name, or over code with no violation is hard guard-allow-invalid', () => {
  const root = fixture();
  write(root, 'backend/services/marks.js', [
    '// guard-allow(perf-shape)',
    'export const a = 1;',
    '// guard-allow(perf): misspelt guard name',
    'export const b = 2;',
    '// guard-allow(perf-shape): there is no loop query here',
    'export const c = 3;',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.hard), [
    'guard-allow-invalid:backend/services/marks.js#missing-reason:perf-shape',
    'guard-allow-invalid:backend/services/marks.js#unknown-guard:perf',
    'guard-allow-invalid:backend/services/marks.js#unused:there is no loop query here',
  ]);
  assert.deepEqual(doc.hard.map((h) => h.line), [1, 3, 5]);
});

test('a file that does not parse lands in parse_failures and an unresolvable import in unsupported', () => {
  const root = makeRoot();
  write(root, 'frontend/src/bad.js', 'export const = ;\n');
  write(root, 'backend/services/missing.js', "import '../db/queries/nope.js';\n");
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  assert.deepEqual(doc.parse_failures, ['frontend/src/bad.js']);
  assert.deepEqual(doc.unsupported, [{
    path: 'backend/services/missing.js', message: 'cannot resolve static import ../db/queries/nope.js',
  }]);
  assert.equal(doc.coverage.planned, 2);
  assert.equal(doc.coverage.scanned, 1);
});

test('an empty scan reports planned 0 and no query-layer counts', () => {
  const { status, doc } = scan(makeRoot());
  assert.equal(status, 0);
  assert.deepEqual(doc.coverage, {
    planned: 0, scanned: 0, unit: 'files', modules: 0, edges: 0, db_read_exports: 0, db_write_exports: 0,
  });
});
