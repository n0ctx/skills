import test from 'node:test';
import assert from 'node:assert/strict';

import { useGuardFixture } from './guard-fixture.mjs';

const { makeRoot, write, run } = useGuardFixture('api-surface.mjs');

const lines = (result) => result.stdout.split('\n').filter(Boolean);

test('parameters render as names, ...rest, x= for defaults and {a,b} / [a,b] for destructuring', () => {
  const root = makeRoot();
  write(root, 'src/index.js', [
    'export function plain(a, b) {}',
    'export function withDefaults(a, b = 2, ...rest) {}',
    'export const arrow = ({ a, b: { c } = {} }, [d, , e]) => {};',
    'export const expr = function named(x) {};',
    'export async function* gen(opts = {}) {}',
    'export function destructured({ a, b }, [c, d], { e = 1, ...others }) {}',
    '',
  ].join('\n'));
  const result = run(root, 'src/index.js');
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(lines(result), [
    'src/index.js#arrow({a,b:{c}=},[d,,e])',
    'src/index.js#destructured({a,b},[c,d],{e=,...others})',
    'src/index.js#expr(x)',
    'src/index.js#gen(opts=)',
    'src/index.js#plain(a,b)',
    'src/index.js#withDefaults(a,b=,...rest)',
  ]);
});

test('constants and other values are `const`; classes list public methods, constructor, accessors and statics, but not private members', () => {
  const root = makeRoot();
  write(root, 'src/index.js', [
    "export const limit = 10;",
    "export let counter = 0;",
    'export const { x, y } = point;',
    'export class App {',
    '  field = 1;',
    '  constructor(opts) {}',
    '  run(a, b = 1) {}',
    '  static make(config) {}',
    '  get size() { return 1; }',
    '  set size(v) {}',
    '  #hidden(z) {}',
    '  [Symbol.iterator]() {}',
    '}',
    '',
  ].join('\n'));
  const result = run(root, 'src/index.js');
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(lines(result), [
    'src/index.js#App class',
    'src/index.js#App.[Symbol.iterator]()',
    'src/index.js#App.constructor(opts)',
    'src/index.js#App.get size()',
    'src/index.js#App.run(a,b=)',
    'src/index.js#App.set size(v)',
    'src/index.js#App.static make(config)',
    'src/index.js#counter const',
    'src/index.js#limit const',
    'src/index.js#x const',
    'src/index.js#y const',
  ]);
});

test('default exports and `export { local as alias }` resolve to the local declaration', () => {
  const root = makeRoot();
  write(root, 'src/index.js', [
    'function internal(a, b) {}',
    'class Thing { go(n) {} }',
    'const value = 1;',
    'export { internal as publicName, Thing, value };',
    'export default function main(argv) {}',
    '',
  ].join('\n'));
  const result = run(root, 'src/index.js');
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(lines(result), [
    'src/index.js#Thing class',
    'src/index.js#Thing.go(n)',
    'src/index.js#default(argv)',
    'src/index.js#publicName(a,b)',
    'src/index.js#value const',
  ]);
});

test('re-exports are followed: export *, named and renamed re-exports, and imported bindings; the entry path is on every line', () => {
  const root = makeRoot();
  write(root, 'src/index.js', [
    "export * from './util.js';",
    "export { helper as renamed, Widget } from './widget.js';",
    "export * as ns from './util.js';",
    "import { fmt } from './util.js';",
    'export { fmt as format };',
    'export function own(a) {}',
    '',
  ].join('\n'));
  write(root, 'src/util.js', 'export function fmt(x) {}\nexport const VERSION = 1;\nexport default function hidden() {}\n');
  write(root, 'src/widget.js', 'export function helper(opts) {}\nexport class Widget { render(props) {} }\n');
  const result = run(root, 'src/index.js');
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(lines(result), [
    'src/index.js#VERSION const',
    'src/index.js#Widget class',
    'src/index.js#Widget.render(props)',
    'src/index.js#fmt(x)',
    'src/index.js#format(x)',
    'src/index.js#ns const',
    'src/index.js#own(a)',
    'src/index.js#renamed(opts)',
  ]);
});

test('an explicit export wins over the same name arriving through export *', () => {
  const root = makeRoot();
  write(root, 'src/index.js', "export * from './a.js';\nexport function dup(own) {}\n");
  write(root, 'src/a.js', 'export function dup(fromStar) {}\nexport const other = 1;\n');
  const result = run(root, 'src/index.js');
  assert.deepEqual(lines(result), ['src/index.js#dup(own)', 'src/index.js#other const']);
});

test('multiple entries are merged, sorted and de-duplicated, and a directory index resolves', () => {
  const root = makeRoot();
  write(root, 'pkg/a.js', "export * from './lib';\n");
  write(root, 'pkg/lib/index.js', 'export function lib(x) {}\n');
  write(root, 'pkg/b.js', 'export const b = 1;\n');
  const result = run(root, 'pkg/b.js', 'pkg/a.js', 'pkg/b.js');
  assert.deepEqual(lines(result), ['pkg/a.js#lib(x)', 'pkg/b.js#b const']);
});

test('a removed or changed export shows up in the next run, and the output is deterministic', () => {
  const root = makeRoot();
  write(root, 'src/index.js', 'export function keep(a) {}\nexport function gone(b) {}\n');
  const first = run(root, 'src/index.js');
  assert.deepEqual(lines(first), ['src/index.js#gone(b)', 'src/index.js#keep(a)']);
  assert.equal(run(root, 'src/index.js').stdout, first.stdout);

  write(root, 'src/index.js', '// comment\nexport function keep(a, extra) {}\n');
  assert.deepEqual(lines(run(root, 'src/index.js')), ['src/index.js#keep(a,extra)']);
});

test('an unresolvable or external re-export fails closed with a message on stderr', () => {
  const root = makeRoot();
  write(root, 'src/index.js', "export function ok() {}\nexport * from './missing.js';\n");
  const missing = run(root, 'src/index.js');
  assert.equal(missing.status, 1);
  assert.equal(missing.stdout, '');
  assert.match(missing.stderr, /cannot resolve re-export from '\.\/missing\.js'/);

  write(root, 'src/index.js', "export { thing } from 'some-package';\n");
  const external = run(root, 'src/index.js');
  assert.equal(external.status, 1);
  assert.match(external.stderr, /cannot resolve re-export from 'some-package'/);

  write(root, 'src/index.js', "export { absent } from './a.js';\n");
  write(root, 'src/a.js', 'export const present = 1;\n');
  const absent = run(root, 'src/index.js');
  assert.equal(absent.status, 1);
  assert.match(absent.stderr, /src\/a\.js: does not export 'absent'/);
});

test('a parse failure, a re-export cycle and a missing entry fail closed', () => {
  const root = makeRoot();
  write(root, 'src/index.js', "export * from './bad.js';\n");
  write(root, 'src/bad.js', 'export const = ;\n');
  const parse = run(root, 'src/index.js');
  assert.equal(parse.status, 1);
  assert.match(parse.stderr, /src\/bad\.js: cannot parse/);

  write(root, 'src/p.js', "export * from './q.js';\n");
  write(root, 'src/q.js', "export * from './p.js';\n");
  const cycle = run(root, 'src/p.js');
  assert.equal(cycle.status, 1);
  assert.match(cycle.stderr, /re-export cycle/);

  const entry = run(root, 'src/nope.js');
  assert.equal(entry.status, 1);
  assert.match(entry.stderr, /src\/nope\.js: not a scanned source file/);
});

test('no entry or an unknown flag is a usage error', () => {
  const root = makeRoot();
  assert.equal(run(root).status, 2);
  assert.equal(run(root, '--update-baseline', 'x.js').status, 2);
  assert.equal(run(root, '--bogus').status, 2);
});
