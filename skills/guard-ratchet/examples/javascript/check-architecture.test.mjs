import test from 'node:test';
import assert from 'node:assert/strict';

import { useGuardFixture, ruleKeys } from './guard-fixture.mjs';

const { makeRoot, write, read, scan } = useGuardFixture('check-architecture.mjs');

test('allowed dependencies produce no finding, and coverage counts files, modules and edges', () => {
  const root = makeRoot();
  write(root, 'frontend/app.js', "import { get } from './api/get.js';\nget();\n");
  write(root, 'frontend/api/get.js', 'export function get() {}\n');
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  assert.deepEqual(doc.findings, []);
  assert.deepEqual(doc.coverage, { planned: 2, scanned: 2, unit: 'files', modules: 2, edges: 1 });
});

test('test, dependency, generated and build directories are not scanned as production source', () => {
  const root = makeRoot();
  write(root, 'frontend/app.js', 'export const app = true;\n');
  write(root, 'backend/tests/bad.test.js', 'export const = ;\n');
  write(root, 'node_modules/pkg/bad.js', 'export const = ;\n');
  write(root, 'vendor/pkg/bad.js', 'export const = ;\n');
  write(root, 'generated/out.js', 'export const = ;\n');
  write(root, 'build/out.js', 'export const = ;\n');
  const { doc } = scan(root);
  assert.deepEqual(doc.parse_failures, []);
  assert.equal(doc.coverage.planned, 1);
  assert.equal(doc.coverage.scanned, 1);
});

test('frontend importing backend/db is a forbidden-dependency finding keyed by the module pair', () => {
  const root = makeRoot();
  write(root, 'frontend/a.js', "import { get } from '../backend/db/x.js';\nget();\n");
  write(root, 'backend/db/x.js', 'export function get() {}\n');
  const { status, doc } = scan(root);
  assert.equal(status, 0);
  assert.deepEqual(ruleKeys(doc.findings), ['forbidden-dependency:frontend/a.js -> backend/db/x.js']);
  assert.deepEqual(doc.findings[0], {
    rule: 'forbidden-dependency',
    key: 'frontend/a.js -> backend/db/x.js',
    count: 1,
    path: 'frontend/a.js',
    line: 1,
  });
  assert.deepEqual(doc.hard, []);
});

test('routes importing backend/db is a finding, even through several imports of the same pair', () => {
  const root = makeRoot();
  write(root, 'backend/routes/user.js', "import { get } from '../db/user.js';\nimport { set } from '../db/user.js';\nget(); set();\n");
  write(root, 'backend/db/user.js', 'export function get() {}\nexport function set() {}\n');
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), ['forbidden-dependency:backend/routes/user.js -> backend/db/user.js']);
});

test('a cross-feature import of a public index entry is allowed', () => {
  const root = makeRoot();
  write(root, 'features/a/x.js', "import { y } from '../b/index.js';\ny();\n");
  write(root, 'features/b/index.js', 'export function y() {}\n');
  write(root, 'features/b/internal/y.js', 'export function y() {}\n');
  assert.deepEqual(scan(root).doc.findings, []);
});

test('a cross-feature deep import is an internal-api-import finding; the same feature is allowed', () => {
  const root = makeRoot();
  write(root, 'features/a/x.js', "import { y } from '../b/internal/y.js';\nimport { z } from './internal/z.js';\ny(); z();\n");
  write(root, 'features/a/internal/z.js', 'export function z() {}\n');
  write(root, 'features/b/index.js', 'export function y() {}\n');
  write(root, 'features/b/internal/y.js', 'export function y() {}\n');
  const { doc } = scan(root);
  assert.deepEqual(ruleKeys(doc.findings), ['internal-api-import:features/a/x.js -> features/b/internal/y.js']);
});

test('inserting unrelated code and adding a file does not change an existing finding key', () => {
  const root = makeRoot();
  write(root, 'frontend/a.js', "import { get } from '../backend/db/x.js';\nget();\n");
  write(root, 'backend/db/x.js', 'export function get() {}\n');
  const before = scan(root).doc;
  assert.deepEqual(ruleKeys(before.findings), ['forbidden-dependency:frontend/a.js -> backend/db/x.js']);

  write(root, 'frontend/a.js', `const unrelated = 1;\n${read(root, 'frontend/a.js')}`);
  write(root, 'frontend/added.js', 'export const unrelated = true;\n');
  const after = scan(root).doc;
  assert.deepEqual(ruleKeys(after.findings), ruleKeys(before.findings));
  assert.equal(after.findings[0].line, 2);
});

test('there is no baseline mode: --baseline-mode is an unknown argument', () => {
  const { status, doc, stderr } = scan(makeRoot(), '--baseline-mode');
  assert.equal(status, 2);
  assert.equal(doc, null);
  assert.match(stderr, /unknown argument: --baseline-mode/);
});

test('a source that does not parse, an unresolvable static import and an empty scan are all visible', () => {
  const parseRoot = makeRoot();
  write(parseRoot, 'frontend/bad.js', 'export const = ;\n');
  assert.deepEqual(scan(parseRoot).doc.parse_failures, ['frontend/bad.js']);

  const importRoot = makeRoot();
  write(importRoot, 'frontend/a.js', "import './missing.js';\n");
  assert.deepEqual(scan(importRoot).doc.unsupported,
    [{ path: 'frontend/a.js', message: 'cannot resolve static import ./missing.js' }]);

  const empty = scan(makeRoot());
  assert.equal(empty.status, 0);
  assert.equal(empty.doc.coverage.planned, 0);
});
