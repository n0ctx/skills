import test from 'node:test';
import assert from 'node:assert/strict';

import { useGuardFixture, ruleKeys } from './guard-fixture.mjs';

const { makeRoot, write, scan } = useGuardFixture('check-cycles.mjs');

function fixture() {
  const root = makeRoot();
  write(root, 'backend/a.js', "import { b } from './b.js';\nexport const a = () => b;\n");
  write(root, 'backend/b.js', "export const b = 1;\nexport const lazy = () => import('./a.js');\n");
  write(root, 'backend/tests/a.test.js', "import { a } from '../a.js';\nexport const x = a;\n");
  return root;
}

test('no static cycle: import() and test files do not form one, and coverage counts modules and edges', () => {
  const { status, doc } = scan(fixture());
  assert.equal(status, 0);
  assert.deepEqual(doc.findings, []);
  assert.deepEqual(doc.coverage, { planned: 2, scanned: 2, unit: 'files', modules: 2, edges: 1 });
});

test('a static import cycle is one finding keyed by its sorted members', () => {
  const root = fixture();
  write(root, 'backend/b.js', "import { a } from './a.js';\nexport const b = 1;\nexport const c = () => a;\n");
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  assert.deepEqual(ruleKeys(doc.findings), ['cycle:backend/a.js <-> backend/b.js']);
  assert.equal(doc.findings[0].count, 1);
  assert.equal(doc.findings[0].path, 'backend/a.js');
});

test('require and export-from edges close cycles too; a three-member cycle is one finding', () => {
  const root = makeRoot();
  write(root, 'src/c.js', "export { b } from './b.js';\nexport const c = 1;\n");
  write(root, 'src/b.js', "const a = require('./a.js');\nexport const b = a;\n");
  write(root, 'src/a.js', "import { c } from './c.js';\nexport const a = c;\n");
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), ['cycle:src/a.js <-> src/b.js <-> src/c.js']);
});

test('two independent cycles are two findings, sorted by key', () => {
  const root = makeRoot();
  write(root, 'x/p.js', "import './q.js';\n");
  write(root, 'x/q.js', "import './p.js';\n");
  write(root, 'a/m.js', "import './n.js';\n");
  write(root, 'a/n.js', "import './m.js';\n");
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), ['cycle:a/m.js <-> a/n.js', 'cycle:x/p.js <-> x/q.js']);
});

test('inserting unrelated code and files does not change a cycle key', () => {
  const root = makeRoot();
  write(root, 'backend/a.js', "import { b } from './b.js';\nexport const a = b;\n");
  write(root, 'backend/b.js', "import { a } from './a.js';\nexport const b = a;\n");
  const before = ruleKeys(scan(root).doc.findings);
  write(root, 'backend/a.js', "// unrelated\nconst noise = 1;\nimport { b } from './b.js';\nexport const a = b + noise;\n");
  write(root, 'backend/zzz.js', 'export const z = 1;\n');
  assert.deepEqual(ruleKeys(scan(root).doc.findings), before);
});

test('an unresolvable static import lands in unsupported', () => {
  const root = makeRoot();
  write(root, 'backend/a.js', "import './missing.js';\n");
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  assert.deepEqual(doc.unsupported, [{ path: 'backend/a.js', message: 'cannot resolve static import ./missing.js' }]);
});

test('a file that does not parse lands in parse_failures', () => {
  const root = makeRoot();
  write(root, 'backend/bad.js', 'export const = ;\n');
  write(root, 'backend/ok.js', 'export const ok = 1;\n');
  const { doc } = scan(root);
  assert.deepEqual(doc.parse_failures, ['backend/bad.js']);
  assert.equal(doc.coverage.planned, 2);
  assert.equal(doc.coverage.scanned, 1);
});

test('an empty scan reports planned 0', () => {
  const { status, doc } = scan(makeRoot());
  assert.equal(status, 0);
  assert.deepEqual(doc.coverage, { planned: 0, scanned: 0, unit: 'files', modules: 0, edges: 0 });
});
