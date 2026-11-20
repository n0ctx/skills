#!/usr/bin/env node
/**
 * Test-shape detector: looks at test source shape only; it neither runs tests nor reads timings.
 *
 * Scans *.test.{js,jsx,mjs} and *.spec.* under backend/tests, assistant/tests and frontend.
 * Keys look like `path#outer describe>case title`, with no line number; a repeated (rule, key)
 * gets ~2 ~3 appended.
 *
 * hard (writing that should never be accepted):
 *   focused-test            committed test.only / it.only / describe.only, fit / fdescribe or { only: true }
 *                           (silently stops the rest of the file from running)
 *   test-without-assertion  a test body with no assertion at all (assert / functions imported from
 *                           node:assert / expect( / the test object's .plan( / t.assert.*)
 *   tautological-assertion  an empty assertion comparing only literals: assert.ok(true),
 *                           assert.equal(1, 1), expect(true).toBe(true)
 *   long-fixed-wait         waitForTimeout in a non-e2e test, or a setTimeout / sleep delay literal > MAX_DELAY_MS
 *   playwright-outside-e2e  playwright appearing outside the e2e directory backend/tests/e2e
 *   e2e-in-default-command  the test / test:coverage scripts in backend/package.json would collect tests/e2e
 *   guard-allow-invalid     a retention marker that is malformed or has no violation left
 *
 * findings (existing offenders are compared by scripts/guard.py):
 *   heavy-setup  count per test file of listen( / initSchema( / chromium.launch (only emitted when
 *                above 1; count is the number of calls); a listen that is followed by close in the
 *                same function is a free-port probe and does not count as starting a server
 *   skip         test.skip / it.skip / describe.skip; key is file + title, count is 1
 *
 * A missing or unreadable backend/package.json, or a missing test script in it, goes into unsupported.
 * Deliberately repeated initialisation (for example checking that running twice is harmless) carries
 * `// guard-allow(tests): reason` next to the call; the rules are in guard-common.mjs.
 *
 * Usage:
 *   node check-tests.mjs [--root <dir>]
 *
 * Output: a detector@2 JSON document. Exit codes: 0 scan completed / 1 crash / 2 usage error.
 */

import { existsSync, globSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import {
  collectAllowMarkers, collectCodeFiles, dedupeKeys, emit, parseArgs, parseFiles, stringValue, walk,
} from './guard-common.mjs';

const SCAN_DIRS = ['backend/tests', 'assistant/tests', 'frontend'];
const TEST_FILE_RE = /\.(test\.(js|jsx|mjs)|spec\.[^./]+)$/;
const E2E_DIR = 'backend/tests/e2e/';
const BACKEND_TEST_SCRIPTS = ['test', 'test:coverage'];
const MAX_DELAY_MS = 50;

const TEST_NAMES = new Set(['test', 'it']);
// test.before / it.skip and the like are not test bodies that must assert
const NON_TEST_MODIFIERS = new Set(['skip', 'todo', 'before', 'after', 'beforeEach', 'afterEach']);
const SUITE_NAMES = new Set(['test', 'it', 'describe']);
const ASSERT_MODULES = new Set(['assert', 'assert/strict', 'node:assert', 'node:assert/strict']);
// Assertion methods that compare their first two arguments; ok and a direct assert(x) look only at the first
const COMPARE_ASSERTS = new Set([
  'equal', 'strictEqual', 'deepEqual', 'deepStrictEqual',
  'notEqual', 'notStrictEqual', 'notDeepEqual', 'notDeepStrictEqual',
]);
const HEAVY_SETUP = ['listen', 'initSchema', 'chromium.launch'];
const FUNCTION_TYPES = new Set(['FunctionExpression', 'ArrowFunctionExpression']);
const FOCUS_ALIASES = new Set(['fit', 'fdescribe']);

// ─── AST helpers ────────────────────────────────────────────────────────────
// Leftmost identifier of a member/call chain: expect(x).toBe -> expect, assert.strictEqual -> assert
function rootName(node) {
  let cur = node;
  while (cur) {
    if (cur.type === 'Identifier') return cur.name;
    cur = cur.type === 'MemberExpression' ? cur.object : cur.type === 'CallExpression' ? cur.callee : null;
  }
  return null;
}

function calleeName(callee) {
  if (callee.type === 'Identifier') return callee.name;
  if (callee.type === 'MemberExpression' && !callee.computed) {
    const obj = callee.object.type === 'Identifier' ? `${callee.object.name}.` : '';
    return `${obj}${callee.property.name}`;
  }
  return null;
}

const lastName = (name) => name?.split('.').pop();

// test(...) / it.only(...) / it.each(rows)(...) -> { root, modifier }
function testCall(node) {
  let callee = node.callee;
  if (callee.type === 'CallExpression') callee = callee.callee;
  if (callee.type === 'Identifier' && SUITE_NAMES.has(callee.name)) return { root: callee.name, modifier: null };
  if (callee.type === 'MemberExpression' && callee.object.type === 'Identifier'
      && SUITE_NAMES.has(callee.object.name) && !callee.computed) {
    return { root: callee.object.name, modifier: callee.property.name };
  }
  return null;
}

function assertLocals(tree) {
  const names = new Set(['assert', 'expect']);
  for (const node of tree.body) {
    if (node.type !== 'ImportDeclaration' || !ASSERT_MODULES.has(node.source.value)) continue;
    node.specifiers.forEach((s) => names.add(s.local.name));
  }
  return names;
}

function isAssertion(node, assertNames, contextName) {
  if (node.type !== 'CallExpression') return false;
  if (assertNames.has(rootName(node.callee))) return true;
  const callee = node.callee;
  if (callee.type !== 'MemberExpression' || callee.object.type !== 'Identifier') return false;
  if (callee.object.name !== contextName) return false;
  return callee.property.name === 'plan';
}

function hasAssertion(fn, assertNames) {
  const contextName = fn.params[0]?.type === 'Identifier' ? fn.params[0].name : null;
  for (const [node] of walk(fn.body)) {
    if (isAssertion(node, assertNames, contextName)) return true;
    if (node.type === 'MemberExpression' && node.object.type === 'Identifier'
        && node.object.name === contextName && node.property.name === 'assert') return true;
  }
  return false;
}

const isLiteral = (node) => node?.type === 'Literal'
  || (node?.type === 'UnaryExpression' && node.argument.type === 'Literal');

// Assertions with a hard-wired result: assert.ok(true) / t.assert.equal(1, 1) / expect(true).toBe(true)
function isTrivialAssertion(node, assertNames) {
  const { callee } = node;
  if (callee.type === 'MemberExpression' && callee.object.type === 'CallExpression'
      && callee.object.callee.type === 'Identifier' && callee.object.callee.name === 'expect') {
    return isLiteral(callee.object.arguments[0]) && node.arguments.every(isLiteral);
  }
  let method = null;
  if (callee.type === 'Identifier' && assertNames.has(callee.name)) method = callee.name === 'assert' ? 'ok' : callee.name;
  else if (callee.type === 'MemberExpression' && !callee.computed) {
    const owner = callee.object;
    const isAssertObject = (owner.type === 'Identifier' && owner.name === 'assert')
      || (owner.type === 'MemberExpression' && !owner.computed && owner.property.name === 'assert');
    if (isAssertObject) method = callee.property.name;
  }
  if (method === 'ok') return isLiteral(node.arguments[0]);
  return COMPARE_ASSERTS.has(method) && isLiteral(node.arguments[0]) && isLiteral(node.arguments[1]);
}

// ─── Per-file checks ────────────────────────────────────────────────────────
// Chain of outer describe>case titles (including the node itself if it is a test call); (top-level) when not inside any test
function scopeKey({ parents }, node) {
  const titles = [];
  for (let cur = node; cur; cur = parents.get(cur)) {
    if (cur.type !== 'CallExpression') continue;
    const info = testCall(cur);
    if (info) titles.unshift(stringValue(cur.arguments[0]) ?? info.modifier ?? '(anonymous)');
    else if (cur.callee.type === 'Identifier' && FOCUS_ALIASES.has(cur.callee.name)) {
      titles.unshift(stringValue(cur.arguments[0]) ?? cur.callee.name);
    }
  }
  return titles.length ? titles.join('>') : '(top-level)';
}

function reportHard(ctx, node, rule, message, key = scopeKey(ctx, node)) {
  ctx.found.hard.push({
    rule, key: `${ctx.file.rel}#${key}`, path: ctx.file.rel, line: node.loc.start.line, message,
  });
}

function checkFocus(ctx, call) {
  const info = testCall(call);
  const onlyOption = info && call.arguments.some((a) => a.type === 'ObjectExpression' && a.properties.some(
    (p) => p.type === 'Property' && (p.key.name ?? p.key.value) === 'only' && p.value.value === true));
  if (info?.modifier === 'only') reportHard(ctx, call, 'focused-test', `${info.root}.only stops the rest of the file from running`);
  else if (onlyOption) reportHard(ctx, call, 'focused-test', `${info.root} with { only: true } stops the rest of the file from running`);
  else if (call.callee.type === 'Identifier' && FOCUS_ALIASES.has(call.callee.name)) {
    reportHard(ctx, call, 'focused-test', `${call.callee.name} stops the rest of the file from running`);
  }
}

function checkAssertions(ctx, call) {
  const info = testCall(call);
  if (!info || !TEST_NAMES.has(info.root) || NON_TEST_MODIFIERS.has(info.modifier)) return;
  const fn = [...call.arguments].reverse().find((a) => FUNCTION_TYPES.has(a.type));
  if (!fn || hasAssertion(fn, ctx.assertNames)) return;
  const title = stringValue(call.arguments[0]) ?? '(anonymous)';
  reportHard(ctx, call, 'test-without-assertion', `test "${title}" has no assertion`);
}

function checkDelays(ctx, call) {
  if (ctx.file.rel.startsWith(E2E_DIR)) return;
  const name = lastName(calleeName(call.callee));
  if (name === 'waitForTimeout') reportHard(ctx, call, 'long-fixed-wait', 'waitForTimeout is not allowed in non-e2e tests');
  const delay = name === 'setTimeout' ? call.arguments[1] : name === 'sleep' ? call.arguments[0] : null;
  if (delay?.type === 'Literal' && typeof delay.value === 'number' && delay.value > MAX_DELAY_MS) {
    reportHard(ctx, call, 'long-fixed-wait', `${name} delay of ${delay.value}ms exceeds the ${MAX_DELAY_MS}ms limit for non-e2e tests`);
  }
}

function moduleSource(node) {
  if (node.type === 'ImportDeclaration' || node.type === 'ImportExpression') return stringValue(node.source);
  if (node.type === 'CallExpression' && node.callee.type === 'Identifier' && node.callee.name === 'require') {
    return stringValue(node.arguments[0]);
  }
  return null;
}

function checkPlaywright(ctx, node) {
  if (ctx.file.rel.startsWith(E2E_DIR)) return;
  const source = moduleSource(node);
  if (source && /^(@playwright\/|playwright)/.test(source)) {
    reportHard(ctx, node, 'playwright-outside-e2e', `playwright is only allowed under ${E2E_DIR}`, source);
  }
}

// A server variable that gets server.listen(...) and, in the function declaring it, server.close(...): a free-port probe
function isPortProbe(file, call) {
  const obj = call.callee.type === 'MemberExpression' ? call.callee.object : null;
  if (obj?.type !== 'Identifier') return false;
  let owner = null;
  for (const [node, parent] of walk(file.tree)) {
    if (node.type === 'VariableDeclarator' && node.id.type === 'Identifier' && node.id.name === obj.name
        && node.range[0] < call.range[0]) owner = parent;
  }
  const scope = owner && [...walk(file.tree)].map(([n]) => n)
    .filter((n) => FUNCTION_TYPES.has(n.type) || n.type === 'FunctionDeclaration')
    .filter((fn) => fn.range[0] <= owner.range[0] && owner.range[1] <= fn.range[1])
    .sort((a, b) => (a.range[1] - a.range[0]) - (b.range[1] - b.range[0]))[0];
  if (!scope) return false;
  return [...walk(scope)].some(([n]) => n.type === 'CallExpression' && n.callee.type === 'MemberExpression'
    && n.callee.object.type === 'Identifier' && n.callee.object.name === obj.name
    && !n.callee.computed && n.callee.property.name === 'close');
}

function recordShape(ctx, call) {
  const { file, found } = ctx;
  const name = calleeName(call.callee);
  const metric = HEAVY_SETUP.find((m) => m === name || (!m.includes('.') && lastName(name) === m));
  if (metric && !(metric === 'listen' && isPortProbe(file, call))
      && !found.allow.covers(file.rel, call.loc.start.line)) {
    const key = `${file.rel}#${metric}`;
    if (!found.heavy.has(key)) found.heavy.set(key, { count: 0, path: file.rel, line: call.loc.start.line, metric });
    found.heavy.get(key).count += 1;
  }
  const info = testCall(call);
  if (info?.modifier === 'skip' && call.callee.type === 'MemberExpression') {
    const title = stringValue(call.arguments[0]) ?? '(anonymous)';
    found.skips.push({
      rule: 'skip',
      key: `${file.rel}#${info.root}.skip ${title}`,
      path: file.rel,
      line: call.loc.start.line,
      message: `permanently skipped test: ${title}`,
    });
  }
}

function inspectFile(file, found) {
  const parents = new Map();
  for (const [node, parent] of walk(file.tree)) parents.set(node, parent);
  const ctx = { file, found, parents, assertNames: assertLocals(file.tree) };
  for (const [node, parent] of parents) {
    checkPlaywright(ctx, node);
    if (node.type !== 'CallExpression') continue;
    const info = testCall(node);
    const isHook = info && ['before', 'after', 'beforeEach', 'afterEach'].includes(info.modifier);
    if (info && TEST_NAMES.has(info.root) && !isHook
        && !(parent?.type === 'CallExpression' && parent.callee === node)) {
      found.testCases += 1;
    }
    checkAssertions(ctx, node);
    checkFocus(ctx, node);
    if (isTrivialAssertion(node, ctx.assertNames)) {
      reportHard(ctx, node, 'tautological-assertion', 'assertion compares only literals, so the result is fixed and tests nothing');
    }
    checkDelays(ctx, node);
    recordShape(ctx, node);
  }
}

// ─── backend default test commands ──────────────────────────────────────────
function scriptTargets(cmd) {
  return cmd.split(/\s+/).slice(1)
    .map((w) => w.replace(/^['"]|['"]$/g, ''))
    .filter((w) => w && !w.startsWith('-') && !/^\w+=/.test(w) && w !== 'node');
}

function scansE2E(backendDir, cmd) {
  const targets = scriptTargets(cmd);
  if (!targets.length) return true;
  return targets.some((target) => {
    const abs = path.join(backendDir, target);
    if (existsSync(abs) && statSync(abs).isDirectory()) return 'tests/e2e/'.startsWith(`${path.posix.normalize(target)}/`);
    return globSync(target, { cwd: backendDir }).some((f) => f.split(path.sep).join('/').startsWith('tests/e2e/'));
  });
}

// Returns { hard, unsupported }: a command that would collect e2e is hard; a missing or unreadable package.json or command is unsupported
function checkBackendScripts(root) {
  const rel = 'backend/package.json';
  const pkgPath = path.join(root, rel);
  if (!existsSync(pkgPath)) return { hard: [], unsupported: [{ path: rel, message: `${rel} not found` }] };
  const text = readFileSync(pkgPath, 'utf8');
  let scripts;
  try {
    scripts = JSON.parse(text).scripts || {};
  } catch (err) {
    return { hard: [], unsupported: [{ path: rel, message: `cannot read ${rel}: ${err.message}` }] };
  }
  const hard = [];
  const unsupported = [];
  for (const name of BACKEND_TEST_SCRIPTS) {
    if (!scripts[name]) unsupported.push({ path: rel, message: `missing "${name}" script` });
    else if (scansE2E(path.join(root, 'backend'), scripts[name])) {
      hard.push({
        rule: 'e2e-in-default-command',
        key: `${rel}#${name}`,
        path: rel,
        line: text.split('\n').findIndex((l) => l.includes(`"${name}"`)) + 1 || 1,
        message: `${name} would collect tests/e2e (browser tests must run on their own)`,
      });
    }
  }
  return { hard, unsupported };
}

// ─── Summary ────────────────────────────────────────────────────────────────
function main() {
  const { root } = parseArgs(process.argv.slice(2));
  const rels = SCAN_DIRS.flatMap((dir) => collectCodeFiles(root, dir)).filter((rel) => TEST_FILE_RE.test(rel));
  const { parsed, parseFailures } = parseFiles(root, rels);
  const allow = collectAllowMarkers(parsed, 'tests');
  const scripts = checkBackendScripts(root);
  const found = { hard: [], heavy: new Map(), skips: [], testCases: 0, allow };
  for (const file of parsed) inspectFile(file, found);

  const heavy = [...found.heavy.entries()].filter(([, h]) => h.count > 1).map(([key, h]) => ({
    rule: 'heavy-setup',
    key,
    count: h.count,
    path: h.path,
    line: h.line,
    message: `${h.metric} appears ${h.count} times in ${h.path}; share one startup`,
  }));
  const marks = allow.items();
  emit({
    guard: 'tests',
    coverage: { planned: rels.length, scanned: parsed.length, test_cases: found.testCases },
    parseFailures,
    unsupported: scripts.unsupported,
    hard: [...scripts.hard, ...dedupeKeys(found.hard), ...marks.hard],
    advisory: marks.advisory,
    findings: [...heavy, ...dedupeKeys(found.skips)],
  });
}

main();
