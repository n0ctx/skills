import test from 'node:test';
import assert from 'node:assert/strict';

import { useGuardFixture, ruleKeys } from './guard-fixture.mjs';

const { makeRoot, write, scan } = useGuardFixture('check-dead-code.mjs');

function fixture() {
  const root = makeRoot();
  write(root, 'backend/server.js', "import { used } from './lib.js';\nconst page = await import('./pages/home');\nused(page);\n");
  write(root, 'backend/lib.js', 'export function used() {}\nexport const unused = 1;\n');
  write(root, 'backend/pages/home/index.js', 'export default 1;\n');
  write(root, 'backend/only-tested.js', 'export const x = 1;\n');
  write(root, 'backend/tests/only-tested.test.js', "import { x } from '../only-tested.js';\n");
  write(root, 'hooks/on-save.js', 'export default function hook() {}\n');
  write(root, 'tools/package.json', JSON.stringify({ scripts: { go: 'node ./run.mjs --fast' } }));
  write(root, 'tools/run.mjs', 'export const unusedInEntry = 1;\n');
  write(root, 'frontend/vite.config.js', 'export default {};\n');
  write(root, 'backend/modes.js', 'export const chatMode = 1;\n');
  write(root, 'backend/tests/modes.test.js', "const { chatMode } = await freshImport('backend/modes.js');\n");
  return root;
}

test('entries, config files and test references (including freshImport) are not reported; only the unused export is', () => {
  const { status, doc } = scan(fixture());
  assert.equal(status, 0);
  assert.deepEqual(ruleKeys(doc.findings), ['dead-export:backend/lib.js#unused']);
  assert.deepEqual(doc.findings[0], {
    rule: 'dead-export',
    key: 'backend/lib.js#unused',
    count: 1,
    path: 'backend/lib.js',
    line: 2,
    message: 'no other file references this export',
  });
  assert.deepEqual(doc.hard, []);
});

test('an unreferenced file is a dead-file finding and an unreferenced export is a dead-export finding', () => {
  const root = fixture();
  write(root, 'backend/orphan.js', 'export const o = 1;\n');
  write(root, 'backend/lib.js', 'export function used() {}\nexport const unused = 1;\nexport const extra = 2;\n');
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), [
    'dead-export:backend/lib.js#extra',
    'dead-export:backend/lib.js#unused',
    'dead-file:backend/orphan.js',
  ]);
});

test('a referenced export is not reported, nor are exports of a namespace-imported module', () => {
  const root = fixture();
  write(root, 'backend/ns.js', 'export const one = 1;\nexport const two = 2;\n');
  write(root, 'backend/server.js', [
    "import * as ns from './ns.js';",
    "import { used } from './lib.js';",
    "const page = await import('./pages/home');",
    'used(ns, page);',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), ['dead-export:backend/lib.js#unused']);
});

test('inserting unrelated content before an export keeps the key and only moves the line', () => {
  const root = fixture();
  write(root, 'backend/lib.js', '// unrelated comment\nexport function used() {}\nexport const unused = 1;\n');
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), ['dead-export:backend/lib.js#unused']);
  assert.equal(doc.findings[0].line, 3);
});

test('convention entries, the public API, repo paths inside import() expressions and guard-allow markers are not reported', () => {
  const root = fixture();
  write(root, 'desktop/src/preload.js', 'export const bridge = 1;\n');
  write(root, 'frontend/src/components/index.js', "export { default as Button } from './Button.jsx';\n");
  write(root, 'frontend/src/components/Button.jsx', 'export default function Button() {}\n');
  write(root, 'frontend/src/main.jsx', "import './components/index.js';\n");
  write(root, 'backend/log.js', 'export const level = 1;\n');
  write(root, 'backend/tests/log.test.js',
    "const mod = await import(pathToFileURL(path.resolve(ROOT, 'backend/log.js')).href);\nmod.level;\n");
  write(root, 'backend/lib.js', [
    'export function used() {}',
    'export const unused = 1;',
    '// guard-allow(dead-code): called by name from an external system',
    'export const external = 2;',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), ['dead-export:backend/lib.js#unused']);
  assert.deepEqual(doc.hard, []);
  assert.deepEqual(doc.advisory, [{
    rule: 'guard-allow',
    key: 'backend/lib.js#called by name from an external system',
    path: 'backend/lib.js',
    line: 3,
    message: 'called by name from an external system',
  }]);
});

test('dynamically loaded modules count the members used: destructuring, dot access, string keys by property name', () => {
  const root = fixture();
  write(root, 'backend/q/a.js', 'export const pick = 1;\nexport const dotted = 2;\nexport const byKey = 3;\nexport const idle = 4;\n');
  write(root, 'backend/q/b.js', 'export const create = 1;\nexport const unusedB = 2;\n');
  write(root, 'backend/tests/q.test.js', [
    "const { pick } = await freshImport('backend/q/a.js');",
    "const mod = await freshImport('backend/q/a.js');",
    "mod.dotted; mod['byKey'];",
    "const suites = [{ path: 'backend/q/b.js', createName: 'create', otherName: 'unusedB' }];",
    'for (const suite of suites) { const m = await freshImport(suite.path); m[suite.createName]; }',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  const keys = doc.findings.map((f) => f.key);
  assert.ok(keys.includes('backend/q/a.js#idle'));
  assert.ok(keys.includes('backend/q/b.js#unusedB'));
  for (const used of ['pick', 'dotted', 'byKey', 'create']) {
    assert.ok(!keys.some((k) => k.endsWith(`#${used}`)), used);
  }
});

test('a dynamically loaded module object passed elsewhere counts every export as used', () => {
  const root = fixture();
  write(root, 'backend/q/c.js', 'export const one = 1;\nexport const two = 2;\n');
  write(root, 'backend/tests/c.test.js', "const mod = await freshImport('backend/q/c.js');\ninspect(mod);\n");
  const { doc } = scan(root);
  assert.ok(!doc.findings.some((f) => f.key.startsWith('backend/q/c.js')));
});

test('malformed, unknown-guard, reasonless and unused guard-allow markers are hard guard-allow-invalid items', () => {
  const root = fixture();
  write(root, 'backend/marks.js', [
    '// guard-allow(dead-code)',
    'export const a = 1;',
    '// guard-allow(deadcode): misspelt guard name',
    'export const b = 2;',
    '// guard-allow(dead-code): this export is actually referenced',
    'export const c = 3;',
    '// guard-allow(dead-code): nothing follows',
  ].join('\n'));
  write(root, 'backend/server.js', "import { c } from './marks.js';\nc;\n");
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.hard), [
    'guard-allow-invalid:backend/marks.js#missing-reason:dead-code',
    'guard-allow-invalid:backend/marks.js#no-target:dead-code',
    'guard-allow-invalid:backend/marks.js#unknown-guard:deadcode',
    'guard-allow-invalid:backend/marks.js#unused:this export is actually referenced',
  ]);
  assert.ok(doc.hard.every((h) => h.line > 0 && h.message));
  // only the valid marker is advisory
  assert.deepEqual(doc.advisory.map((a) => a.message), ['this export is actually referenced']);
});

test('an unresolvable static import and a broken package.json land in unsupported', () => {
  const root = makeRoot();
  write(root, 'backend/server.js', "import './missing.js';\n");
  write(root, 'tools/package.json', '{ not json');
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  assert.equal(doc.unsupported.length, 2);
  assert.deepEqual(doc.unsupported[0], { path: 'backend/server.js', message: 'cannot resolve static import ./missing.js' });
  assert.equal(doc.unsupported[1].path, 'tools/package.json');
  assert.match(doc.unsupported[1].message, /cannot read package\.json/);
});

test('a file that does not parse lands in parse_failures', () => {
  const root = makeRoot();
  write(root, 'backend/server.js', 'export const ok = 1;\n');
  write(root, 'backend/bad.js', 'export const = ;\n');
  const { doc } = scan(root);
  assert.deepEqual(doc.parse_failures, ['backend/bad.js']);
  assert.equal(doc.coverage.planned, 2);
  assert.equal(doc.coverage.scanned, 1);
});

test('an empty scan reports planned 0; coverage counts modules and edges', () => {
  const empty = scan(makeRoot());
  assert.equal(empty.status, 0);
  assert.deepEqual(empty.doc.coverage, { planned: 0, scanned: 0, unit: 'files', modules: 0, edges: 0 });

  const { doc } = scan(fixture());
  assert.equal(doc.coverage.planned, doc.coverage.scanned);
  assert.equal(doc.coverage.modules, 10);
  assert.equal(doc.coverage.edges, 4);
});
