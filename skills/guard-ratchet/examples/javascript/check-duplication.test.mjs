import test from 'node:test';
import assert from 'node:assert/strict';

import { useGuardFixture } from './guard-fixture.mjs';

const { makeRoot, write, scan } = useGuardFixture('check-duplication.mjs');

const block = (name) => `export function ${name}(items) {
  let total = 0;
  for (const item of items) {
    if (item.enabled && item.value > 10) total += item.value * 2;
    else total -= item.value;
  }
  return total;
}
`;

function fixture() {
  const root = makeRoot();
  write(root, 'backend/a.js', block('sumA'));
  write(root, 'backend/b.js', block('sumB'));
  write(root, 'backend/tests/c.test.js', block('sumC'));
  return root;
}

test('the same statements in two files are one duplicate finding with a content-hash key and count 2', () => {
  const { status, doc } = scan(fixture());
  assert.equal(status, 0);
  assert.equal(doc.findings.length, 1);
  const [finding] = doc.findings;
  assert.equal(finding.rule, 'duplicate');
  assert.match(finding.key, /^[0-9a-f]{16}$/);
  assert.equal(finding.count, 2);
  assert.equal(finding.path, 'backend/a.js');
  assert.equal(finding.line, 1);
  assert.match(finding.message, /backend\/a\.js:1-8, backend\/b\.js:1-8/);
  assert.deepEqual(doc.hard, []);
});

test('test files are not scanned', () => {
  const { doc } = scan(fixture());
  assert.equal(doc.coverage.planned, 2);
  assert.ok(!doc.findings[0].message.includes('c.test.js'));
});

test('a third copy keeps the key and raises the count', () => {
  const root = fixture();
  const before = scan(root).doc.findings[0];
  write(root, 'backend/d.js', block('sumD'));
  const after = scan(root).doc.findings;
  assert.equal(after.length, 1);
  assert.equal(after[0].key, before.key);
  assert.equal(after[0].count, 3);
});

test('a copy inside one file is found', () => {
  const root = makeRoot();
  const loop = 'for (const row of rows) { if (row.id > 3 && row.name !== "x") { out.push({ id: row.id, name: row.name, tag: "t" }); } }\n';
  write(root, 'frontend/src/d.js', `const out = [];\n${loop}console.log(out.length);\n${loop}`);
  const { doc } = scan(root);
  assert.equal(doc.findings.length, 1);
  assert.match(doc.findings[0].message, /frontend\/src\/d\.js:2-2, frontend\/src\/d\.js:4-4/);
});

test('renaming identifiers does not change the key, and unrelated comments or code do not either', () => {
  const root = fixture();
  const before = scan(root).doc.findings[0].key;
  write(root, 'backend/a.js', `// unrelated comment\nconst unrelated = 1;\n${block('renamedFunction').replaceAll('items', 'rows').replaceAll('total', 'sum')}`);
  const after = scan(root).doc.findings;
  assert.equal(after.length, 1);
  assert.equal(after[0].key, before);
});

test('different statements are not duplicates', () => {
  const root = fixture();
  write(root, 'backend/b.js', block('sumB').replace('item.value * 2', 'item.value * 3'));
  assert.deepEqual(scan(root).doc.findings, []);
});

test('a 39-token fragment is not reported; 40 tokens is', () => {
  const root = makeRoot();
  const declarations = (prefix, count) => Array.from(
    { length: count }, (_, i) => `const ${prefix}${i} = 1;`,
  ).join('\n');
  write(root, 'frontend/src/edge-a.js', `${declarations('a', 7)}\n`);
  write(root, 'frontend/src/edge-b.js', `${declarations('b', 7)}\n`);
  assert.deepEqual(scan(root).doc.findings, []);

  write(root, 'frontend/src/edge-a.js', `${declarations('a', 8)}\n`);
  write(root, 'frontend/src/edge-b.js', `${declarations('b', 8)}\n`);
  const { doc } = scan(root);
  assert.equal(doc.findings.length, 1);
  assert.match(doc.findings[0].message, /edge-a\.js:1-8, frontend\/src\/edge-b\.js:1-8/);
  assert.match(doc.findings[0].message, /40 tokens/);
});

const setters = (source) => ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta']
  .map((field) => `set_${source}_${field}(${source}.${field}_value);`).join('\n');

test('a run of simple calls that differ only in names is not a duplicate', () => {
  const root = makeRoot();
  write(root, 'frontend/src/d.js', `${setters('prompt')}\n`);
  write(root, 'frontend/src/e.js', `${setters('display')}\n`);
  assert.deepEqual(scan(root).doc.findings, []);
});

test('a verbatim-identical run of simple calls is still a duplicate', () => {
  const root = makeRoot();
  write(root, 'frontend/src/d.js', `${setters('prompt')}\n`);
  write(root, 'frontend/src/e.js', `${setters('prompt')}\n`);
  const { doc } = scan(root);
  assert.equal(doc.findings.length, 1);
  assert.match(doc.findings[0].message, /frontend\/src\/d\.js:1-6, frontend\/src\/e\.js:1-6/);
});

test('a guard-allow marker drops its occurrence, leaving under two so nothing is emitted, and is listed as advisory', () => {
  const root = fixture();
  write(root, 'backend/b.js', `// guard-allow(duplication): mirror of a.js that must stay verbatim\n${block('sumB')}`);
  const { doc } = scan(root);
  assert.deepEqual(doc.findings, []);
  assert.deepEqual(doc.hard, []);
  assert.deepEqual(doc.advisory, [{
    rule: 'guard-allow',
    key: 'backend/b.js#mirror of a.js that must stay verbatim',
    path: 'backend/b.js',
    line: 1,
    message: 'mirror of a.js that must stay verbatim',
  }]);
});

test('a guard-allow marker over code that is not duplicated is a hard guard-allow-invalid item', () => {
  const root = fixture();
  write(root, 'backend/e.js', '// guard-allow(duplication): nothing here is duplicated\nexport const e = 1;\n');
  const { doc } = scan(root);
  assert.equal(doc.hard.length, 1);
  assert.equal(doc.hard[0].rule, 'guard-allow-invalid');
  assert.equal(doc.hard[0].key, 'backend/e.js#unused:nothing here is duplicated');
  assert.equal(doc.findings.length, 1);
});

test('a file that does not parse lands in parse_failures; an empty scan reports planned 0', () => {
  const root = fixture();
  write(root, 'frontend/src/bad.js', 'export const = ;\n');
  const { doc } = scan(root);
  assert.deepEqual(doc.parse_failures, ['frontend/src/bad.js']);
  assert.deepEqual(doc.coverage, { planned: 3, scanned: 2, unit: 'files' });

  const empty = scan(makeRoot());
  assert.equal(empty.status, 0);
  assert.deepEqual(empty.doc.coverage, { planned: 0, scanned: 0, unit: 'files' });
});
