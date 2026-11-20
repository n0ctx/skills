import test from 'node:test';
import assert from 'node:assert/strict';

import { useGuardFixture, ruleKeys } from './guard-fixture.mjs';

const { makeRoot, write, scan } = useGuardFixture('check-tests.mjs');
const GLOB = '"tests/{*.test.js,!(e2e)/**/*.test.js}"';

function fixture() {
  const root = makeRoot();
  write(root, 'backend/package.json', JSON.stringify({
    scripts: { test: `node --test ${GLOB}`, 'test:coverage': `node --test --experimental-test-coverage ${GLOB}` },
  }));
  write(root, 'backend/tests/a.test.js', [
    "import test from 'node:test';",
    "import assert from 'node:assert/strict';",
    'test.before(() => {});',
    "test('ok', () => { assert.equal(sum(1, 1), 2); });",
    "test('plan', (t) => { t.plan(1); t.assert.ok(ready()); });",
    "test.skip('pending', () => {});",
    'server.listen(0); server.listen(0);',
    '',
  ].join('\n'));
  write(root, 'backend/tests/e2e/ui.test.js', [
    "import { chromium } from 'playwright';",
    "test('ui', async () => { await page.waitForTimeout(500); expect(await title()).toBe('x'); });",
    '',
  ].join('\n'));
  write(root, 'frontend/src/x.test.jsx', "it('renders', async () => { await sleep(20); expect(view()).toBe(1); });\n");
  return root;
}

const BASE_FINDINGS = [
  'heavy-setup:backend/tests/a.test.js#listen',
  'skip:backend/tests/a.test.js#test.skip pending',
];

test('baseline repository: no hard items; two listen calls and a skip are findings; e2e-only waits and playwright are allowed', () => {
  const { status, doc } = scan(fixture());
  assert.equal(status, 0);
  assert.deepEqual(doc.hard, []);
  assert.deepEqual(doc.unsupported, []);
  assert.deepEqual(ruleKeys(doc.findings), BASE_FINDINGS);
  assert.deepEqual(doc.findings.map((f) => f.count), [2, 1]);
  assert.deepEqual(doc.coverage, { planned: 3, scanned: 3, unit: 'files', test_cases: 5 });
});

test('no assertion, a long wait, playwright outside e2e and a default command that collects e2e are hard items with stable keys', () => {
  const root = fixture();
  write(root, 'frontend/src/y.test.js', [
    "import { test } from '@playwright/test';",
    "it('no assert', () => { run(); });",
    "it('slow', async () => { await new Promise((r) => setTimeout(r, 51)); expect(view()).toBe(1); });",
    '',
  ].join('\n'));
  write(root, 'backend/package.json', JSON.stringify({
    scripts: { test: 'node --test "tests/**/*.test.js"', 'test:coverage': `node --test ${GLOB}` },
  }));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.hard), [
    'e2e-in-default-command:backend/package.json#test',
    'playwright-outside-e2e:frontend/src/y.test.js#@playwright/test',
    'test-without-assertion:frontend/src/y.test.js#no assert',
    'long-fixed-wait:frontend/src/y.test.js#slow',
  ]);
  const byRule = Object.fromEntries(doc.hard.map((h) => [h.rule, h]));
  assert.equal(byRule['test-without-assertion'].line, 2);
  assert.equal(byRule['test-without-assertion'].message, 'test "no assert" has no assertion');
  assert.equal(byRule['long-fixed-wait'].line, 3);
  assert.match(byRule['long-fixed-wait'].message, /setTimeout delay of 51ms/);
  assert.equal(byRule['playwright-outside-e2e'].line, 1);
  assert.equal(byRule['e2e-in-default-command'].path, 'backend/package.json');
  assert.ok(!doc.hard.some((h) => h.key.endsWith('#test:coverage')));
});

test('committed focus (.only, { only: true }, fit, fdescribe) is a hard focused-test item, keyed by the describe>case chain', () => {
  const root = fixture();
  write(root, 'backend/tests/b.test.js', [
    "import assert from 'node:assert/strict';",
    "test.only('focus', () => { assert.equal(sum(1, 2), 3); });",
    "test('option', { only: true }, () => { assert.ok(ready()); });",
    "describe('suite', () => { it.only('nested', () => { assert.ok(ready()); }); });",
    "fit('legacy focus', () => { expect(ready()).toBe(true); });",
    "fdescribe('legacy suite', () => {});",
    '',
  ].join('\n'));
  const { doc } = scan(root);
  const focused = doc.hard.filter((h) => h.rule === 'focused-test');
  assert.deepEqual(focused.map((h) => h.key), [
    'backend/tests/b.test.js#focus',
    'backend/tests/b.test.js#legacy focus',
    'backend/tests/b.test.js#legacy suite',
    'backend/tests/b.test.js#option',
    'backend/tests/b.test.js#suite>nested',
  ]);
  assert.equal(focused[0].line, 2);
  assert.equal(focused[0].message, 'test.only stops the rest of the file from running');
});

test('assertions that only compare literals are hard tautological-assertion items; real comparisons are not', () => {
  const root = fixture();
  write(root, 'backend/tests/b.test.js', [
    "import assert from 'node:assert/strict';",
    "test('fake', (t) => { assert.ok(true); t.assert.equal(1, 1); expect(true).toBe(true); });",
    "test('real', () => { assert.equal(sum(1, 1), 2); expect(view()).toBe(1); assert.ok(ready()); });",
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.hard), [
    'tautological-assertion:backend/tests/b.test.js#fake',
    'tautological-assertion:backend/tests/b.test.js#fake ~2',
    'tautological-assertion:backend/tests/b.test.js#fake ~3',
  ]);
});

test('a fixed wait of 50ms is fine, 51ms is a hard long-fixed-wait; waitForTimeout is hard outside e2e only', () => {
  const root = fixture();
  const source = (ms) => [
    "import { test } from 'node:test';",
    `test('wait', async () => { await new Promise((resolve) => setTimeout(resolve, ${ms})); expect(view()).toBe(1); });`,
    '',
  ].join('\n');
  write(root, 'frontend/src/boundary.test.js', source(50));
  assert.deepEqual(scan(root).doc.hard, []);
  write(root, 'frontend/src/boundary.test.js', source(51));
  assert.deepEqual(ruleKeys(scan(root).doc.hard), ['long-fixed-wait:frontend/src/boundary.test.js#wait']);

  write(root, 'frontend/src/boundary.test.js',
    "test('p', async () => { await page.waitForTimeout(10); expect(view()).toBe(1); });\n");
  assert.deepEqual(ruleKeys(scan(root).doc.hard), ['long-fixed-wait:frontend/src/boundary.test.js#p']);
});

test('hooks, skipped and todo tests need no assertion; t.plan, imported assert functions and expect all count', () => {
  const root = fixture();
  write(root, 'backend/tests/ok.test.js', [
    "import test from 'node:test';",
    "import { strictEqual } from 'node:assert';",
    'test.before(() => { setup(); });',
    'test.afterEach(() => { cleanup(); });',
    "test.skip('later', () => { run(); });",
    "test.todo('someday');",
    "test('plan only', (t) => { t.plan(1); });",
    "test('imported', () => { strictEqual(sum(1, 1), 2); });",
    "test('expect', () => { expect(view()).toBe(1); });",
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(doc.hard, []);
});

test('only e2e tests may use playwright and waitForTimeout', () => {
  const { doc } = scan(fixture());
  assert.deepEqual(doc.hard.filter((h) => h.path.includes('e2e')), []);
});

test('default commands: a directory target that contains e2e is hard, one that does not is not', () => {
  const root = fixture();
  write(root, 'backend/tests/unit/u.test.js', "test('u', () => { expect(view()).toBe(1); });\n");
  write(root, 'backend/package.json', JSON.stringify({ scripts: { test: 'node --test tests', 'test:coverage': 'node --test tests/unit' } }));
  assert.deepEqual(ruleKeys(scan(root).doc.hard), ['e2e-in-default-command:backend/package.json#test']);
});

test('heavy-setup is emitted only above one call, ignores free-port probes, and skips guard-allow calls', () => {
  const root = fixture();
  write(root, 'backend/tests/single.test.js', [
    "import assert from 'node:assert/strict';",
    "test('x', () => { server.listen(0); assert.ok(ready()); });",
    '',
  ].join('\n'));
  write(root, 'backend/tests/b.test.js', [
    "import test from 'node:test';",
    "import assert from 'node:assert/strict';",
    'async function freePort() { const probe = createServer(); probe.listen(0); await probe.close(); }',
    "test('x', async () => { await freePort(); server.listen(0);",
    '  // guard-allow(tests): checks that repeated initialisation is harmless',
    '  initSchema(db);',
    '  initSchema(db);',
    '  assert.ok(ready()); });',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), BASE_FINDINGS);
  assert.deepEqual(doc.hard, []);
  assert.deepEqual(doc.advisory.map((a) => [a.rule, a.path, a.line, a.message]), [
    ['guard-allow', 'backend/tests/b.test.js', 5, 'checks that repeated initialisation is harmless'],
  ]);
});

test('three initSchema calls without a marker is a heavy-setup finding with count 3', () => {
  const root = fixture();
  write(root, 'backend/tests/c.test.js', [
    "import assert from 'node:assert/strict';",
    "test('x', () => { initSchema(db); initSchema(db); initSchema(db); assert.ok(ready()); });",
    '',
  ].join('\n'));
  const { doc } = scan(root);
  const heavy = doc.findings.find((f) => f.key === 'backend/tests/c.test.js#initSchema');
  assert.equal(heavy.count, 3);
  assert.equal(heavy.rule, 'heavy-setup');
});

test('guard-allow with no reason, a wrong name or nothing to cover is hard guard-allow-invalid', () => {
  const root = fixture();
  write(root, 'backend/tests/marks.test.js', [
    "import assert from 'node:assert/strict';",
    '// guard-allow(tests)',
    "test('a', () => { assert.ok(ready()); });",
    '// guard-allow(test): misspelt guard name',
    "test('b', () => { assert.ok(ready()); });",
    '// guard-allow(tests): no heavy setup is covered',
    "test('c', () => { assert.ok(ready()); });",
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.hard), [
    'guard-allow-invalid:backend/tests/marks.test.js#missing-reason:tests',
    'guard-allow-invalid:backend/tests/marks.test.js#unknown-guard:test',
    'guard-allow-invalid:backend/tests/marks.test.js#unused:no heavy setup is covered',
  ]);
});

test('inserting an unrelated test before a skipped one keeps its key and the focus/assertion keys', () => {
  const root = fixture();
  write(root, 'backend/tests/a.test.js', [
    "import assert from 'node:assert/strict';",
    "test('unrelated', () => { assert.ok(ready()); });",
    "test.skip('pending', () => {});",
    'server.listen(0); server.listen(0);',
    '',
  ].join('\n'));
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), BASE_FINDINGS);
  assert.equal(doc.findings[1].line, 3);

  const keys = (d) => ruleKeys(d.hard);
  write(root, 'backend/tests/f.test.js', "test.only('f', () => { assert.ok(1); });\ntest('g', () => {});\n");
  const first = keys(scan(root).doc);
  write(root, 'backend/tests/f.test.js', "// comment\nconst unrelated = 1;\ntest.only('f', () => { assert.ok(1); });\ntest('g', () => {});\n");
  assert.deepEqual(keys(scan(root).doc), first);
});

test('a missing or broken backend/package.json, or a missing script, lands in unsupported', () => {
  const missing = makeRoot();
  write(missing, 'backend/tests/a.test.js', "test('x', () => { expect(view()).toBe(1); });\n");
  assert.deepEqual(scan(missing).doc.unsupported, [{ path: 'backend/package.json', message: 'backend/package.json not found' }]);

  const broken = makeRoot();
  write(broken, 'backend/package.json', '{ nope');
  assert.equal(scan(broken).doc.unsupported[0].path, 'backend/package.json');
  assert.match(scan(broken).doc.unsupported[0].message, /cannot read backend\/package\.json/);

  const noScript = makeRoot();
  write(noScript, 'backend/package.json', JSON.stringify({ scripts: { test: `node --test ${GLOB}` } }));
  assert.deepEqual(scan(noScript).doc.unsupported, [{ path: 'backend/package.json', message: 'missing "test:coverage" script' }]);
});

test('a test file that does not parse lands in parse_failures', () => {
  const root = fixture();
  write(root, 'backend/tests/bad.test.js', 'test(,);\n');
  const { doc } = scan(root);
  assert.deepEqual(doc.parse_failures, ['backend/tests/bad.test.js']);
  assert.equal(doc.coverage.planned, 4);
  assert.equal(doc.coverage.scanned, 3);
});

test('an empty scan reports planned 0 and 0 test cases; no floor is applied', () => {
  const { status, doc } = scan(makeRoot());
  assert.equal(status, 0);
  assert.deepEqual(doc.coverage, { planned: 0, scanned: 0, unit: 'files', test_cases: 0 });

  const noCases = makeRoot();
  write(noCases, 'backend/package.json', JSON.stringify({
    scripts: { test: `node --test ${GLOB}`, 'test:coverage': `node --test ${GLOB}` },
  }));
  write(noCases, 'backend/tests/helper.test.js', 'export const helper = 1;\n');
  assert.deepEqual(scan(noCases).doc.coverage, { planned: 1, scanned: 1, unit: 'files', test_cases: 0 });
});
