#!/usr/bin/env node
/**
 * Cyclomatic-complexity detector: emits one fn-complexity metric per function and judges none.
 *
 * Ported from a Python project's complexity guard. High complexity is not bad in itself: some
 * functions reconcile several heterogeneous systems, and that complexity is inherent. The real
 * problem is silent growth: a function never goes from 20 to 50 in one change. So this detector
 * only measures; thresholds per code kind, recording existing offenders and "may go down, never
 * up" all belong to scripts/guard.py.
 *
 * The complexity formula is a built-in approximation (each branch, loop, catch, ternary and
 * logical operator counts one). The numbers need not match a professional tool: they are only
 * compared with their own history.
 *
 * For a private function in the same file that has exactly one caller, its decisions are added
 * back to the caller. Cutting decisions out into a function called once leaves the score
 * unchanged, so moving code cannot get under a threshold. A function called from two or more
 * places, or exported to another file, is scored on its own; an added-back function is also
 * scored on its own as usual.
 *
 * An anonymous function's key is "outer function name>call name", for example
 * matchEntries>filter (a repeat gets ~2). Adding a function earlier in the file therefore never
 * shifts the keys of the anonymous functions after it.
 *
 * Usage:
 *   node check-complexity.mjs [--root <dir>] [--ignore <glob>]
 *
 * Output: a detector@2 JSON document with one fn-complexity metric per function.
 * Exit codes: 0 scan completed / 1 crash / 2 usage error.
 */

import { collectCodeFiles, emit, parseArgs, parseFiles, walk } from './guard-common.mjs';

const FUNCTION_TYPES = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression']);
const DECISION_NODES = new Set([
  'IfStatement', 'ForStatement', 'ForInStatement', 'ForOfStatement',
  'WhileStatement', 'DoWhileStatement', 'CatchClause', 'ConditionalExpression',
]);

// ─── Traversal ──────────────────────────────────────────────────────────────
function matchGlob(rel, pattern) {
  const rx = new RegExp('^' + pattern.split('/').map((seg) => {
    if (seg === '**') return '.*';
    return seg.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*').replace(/\?/g, '.');
  }).join('/') + '(/|$)');
  return rx.test(rel);
}

// ─── Complexity ─────────────────────────────────────────────────────────────
function isDecision(node) {
  if (DECISION_NODES.has(node.type)) return true;
  if (node.type === 'SwitchCase' && node.test) return true;
  return node.type === 'LogicalExpression' && ['&&', '||', '??'].includes(node.operator);
}

function decisionCount(fn) {
  let score = 0;
  for (const [node] of walk(fn)) {
    if (node !== fn && isDecision(node)) score += 1;
  }
  return score;
}

function isFunctionRoot(node, parent) {
  return FUNCTION_TYPES.has(node.type) && !(parent?.type === 'MethodDefinition' && parent.value !== node);
}

// Only a direct call `name(...)` counts. obj.name(), name.method() and callbacks do not:
// those are not "cut the decisions out and call them once".
function calleeName(node) {
  if (node.type !== 'CallExpression') return null;
  if (node.callee.type === 'Identifier') return node.callee.name;
  return null;
}

// Inner function: caller traversal stops here, its own calls are not the caller's
const isInnerFunction = (node, parent) => parent !== null && isFunctionRoot(node, parent);

function isExported(parent) {
  return parent?.type === 'ExportNamedDeclaration' || parent?.type === 'ExportDefaultDeclaration';
}

// Name of the call a callback sits in: items.filter(() => ...) -> filter, setTimeout(() => ...) -> setTimeout
function callbackLabel(node, parent) {
  if ((parent?.type === 'CallExpression' || parent?.type === 'NewExpression') && parent.arguments.includes(node)) {
    const { callee } = parent;
    if (callee.type === 'Identifier') return callee.name;
    if (callee.type === 'MemberExpression' && !callee.computed) return callee.property.name;
  }
  return '(anonymous)';
}

// The name of each function node; an anonymous function hangs under the nearest enclosing function's name
function functionNames(tree) {
  const names = new Map();
  const parentOf = new Map();
  for (const [node, parent] of walk(tree)) {
    parentOf.set(node, parent);
    if (!isFunctionRoot(node, parent)) continue;
    let outer = parent;
    while (outer && !names.has(outer)) outer = parentOf.get(outer);
    const own = functionName(node, parent);
    names.set(node, own !== '(anonymous)' ? own : `${outer ? names.get(outer) : '(top-level)'}>${callbackLabel(node, parent)}`);
  }
  return names;
}

// Returns [{ key, line, value }]; key looks like `path#name` (same-named functions get ~2 ~3)
function fileScores(tree, rel) {
  const functions = [];
  const nameCounts = new Map();
  const names = functionNames(tree);
  for (const [node, parent] of walk(tree)) {
    if (!isFunctionRoot(node, parent)) continue;
    const name = names.get(node);
    const occurrence = (nameCounts.get(name) || 0) + 1;
    nameCounts.set(name, occurrence);
    functions.push({
      node,
      name,
      key: `${rel}#${name}${occurrence > 1 ? `~${occurrence}` : ''}`,
      line: node.loc.start.line,
      exported: isExported(parent),
      decisions: decisionCount(node),
    });
  }

  const callsByName = new Map();
  for (const fn of functions) {
    for (const [node] of walk(fn.node, null, isInnerFunction)) {
      const called = calleeName(node);
      if (!called) continue;
      const callers = callsByName.get(called) || [];
      callers.push(fn);
      callsByName.set(called, callers);
    }
  }

  // Same file, name appears once, not exported, called from exactly one function: add its decisions
  // to the caller. The callee is still scored on its own; dropping it would make an existing entry
  // vanish while the caller rises for no visible reason.
  for (const fn of functions) {
    if (fn.exported || nameCounts.get(fn.name) !== 1) continue;
    const callers = callsByName.get(fn.name) || [];
    const distinct = [...new Set(callers)];
    if (distinct.length !== 1 || distinct[0] === fn) continue;
    const caller = distinct[0];
    // A function defined inside the caller is already counted in the caller; do not add it again.
    const insideCaller = fn.node.range[0] >= caller.node.range[0] && fn.node.range[1] <= caller.node.range[1];
    if (!insideCaller) caller.decisions += fn.decisions;
  }

  return functions.map((fn) => ({ key: fn.key, line: fn.line, value: fn.decisions + 1 }));
}

function functionName(node, parent) {
  if (node.id && node.id.name) return node.id.name;
  if (!parent) return '(anonymous)';
  if (parent.type === 'VariableDeclarator' && parent.id.type === 'Identifier') return parent.id.name;
  if ((parent.type === 'MethodDefinition' || parent.type === 'Property') && parent.key) {
    return parent.key.name || parent.key.value || '(anonymous)';
  }
  if (parent.type === 'AssignmentExpression' && parent.left.type === 'MemberExpression') {
    return parent.left.property.name || '(anonymous)';
  }
  if (parent.type === 'ExportDefaultDeclaration') return '(default)';
  return '(anonymous)';
}

function main() {
  const args = parseArgs(process.argv.slice(2), { ignore: true });
  const rels = collectCodeFiles(args.root, '', (rel) => args.ignores.some((p) => matchGlob(rel, p)));
  const { parsed, parseFailures } = parseFiles(args.root, rels);
  const metrics = parsed.flatMap(({ rel, tree }) => fileScores(tree, rel)
    .map(({ key, line, value }) => ({ metric: 'fn-complexity', key, path: rel, line, value })));
  emit({
    guard: 'complexity',
    coverage: { planned: rels.length, scanned: parsed.length, functions: metrics.length },
    parseFailures,
    metrics,
  });
}

main();
