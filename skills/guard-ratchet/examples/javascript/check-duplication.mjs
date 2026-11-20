#!/usr/bin/env node
/**
 * Duplicate-code detector: a token sequence of consecutive statements that appears in several places.
 *
 * The unit of comparison is the run of consecutive executable statements in one statement list
 * (file top level, block, case branch). Identifier names are erased before comparing; whitespace
 * and comments never become tokens, so code copied and then renamed still counts as a duplicate.
 * Literals, keywords and operators stay as they are.
 * A fragment shorter than MIN_TOKENS is not reported; a small fragment wrapped inside a larger
 * duplicate is not reported again. When every statement of a fragment is just one simple call
 * (setter, selector, hook read, registration), erasing names leaves only the call shape, so such a
 * fragment is reported only if it is also verbatim identical with the names kept.
 *
 * One finding per duplicate group: rule is duplicate, key is the content hash of the normalised
 * fragment, count is the number of occurrences, and message lists the locations. Whether a group
 * is new, grew or shrank is for scripts/guard.py to decide by comparing count.
 * Mirror code that must stay verbatim identical (for example one algorithm kept on both frontend
 * and backend) carries `// guard-allow(duplication): reason` next to the fragment: the marked
 * occurrence no longer counts, and a group left with fewer than two occurrences is not emitted.
 * The rules are in guard-common.mjs.
 *
 * Usage:
 *   node check-duplication.mjs [--root <dir>]
 *
 * Output: a detector@2 JSON document. Exit codes: 0 scan completed / 1 crash / 2 usage error.
 */

import { createHash } from 'node:crypto';
import { collectAllowMarkers, collectCodeFiles, emit, isTestPath, parseArgs, parseFiles, walk } from './guard-common.mjs';

const SCAN_DIRS = ['frontend/src', 'backend', 'assistant/server', 'assistant/client/src'];
const MIN_TOKENS = 40;

const IDENTIFIER_TOKENS = new Set(['Identifier', 'JSXIdentifier', 'PrivateIdentifier']);
const STATEMENT_LISTS = { Program: 'body', BlockStatement: 'body', StaticBlock: 'body', SwitchCase: 'consequent' };

// ─── Normalisation ──────────────────────────────────────────────────────────
function normalizeTokens(tokens) {
  const out = [];
  for (const tok of tokens) {
    if (IDENTIFIER_TOKENS.has(tok.type)) out.push({ start: tok.range[0], value: '$', raw: tok.value });
    else if (tok.type === 'JSXText') {
      const text = tok.value.replace(/\s+/g, ' ').trim();
      if (text) out.push({ start: tok.range[0], value: text, raw: text });
    } else out.push({ start: tok.range[0], value: tok.value, raw: tok.value });
  }
  return out;
}

function lowerBound(tokens, pos) {
  let lo = 0;
  let hi = tokens.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (tokens[mid].start < pos) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function isExecutable(stmt) {
  if (stmt.type === 'ImportDeclaration' || stmt.type === 'ExportAllDeclaration') return false;
  if (stmt.type === 'ExportNamedDeclaration') return Boolean(stmt.declaration);
  return true;
}

function isPlainValue(node) {
  switch (node.type) {
    case 'Identifier':
    case 'Literal':
    case 'ThisExpression':
      return true;
    case 'MemberExpression':
      return !node.computed && isPlainValue(node.object);
    case 'ArrowFunctionExpression':
      return node.body.type !== 'BlockStatement' && isPlainValue(node.body);
    case 'ObjectExpression':
      return node.properties.every((prop) => prop.type === 'Property' && !prop.computed && isPlainValue(prop.value));
    case 'ArrayExpression':
      return node.elements.every((element) => element && isPlainValue(element));
    default:
      return false;
  }
}

// The whole statement just calls a function once with ready-made values, such as setX(settings.x) or useStore((s) => s.x)
function isPlainCall(stmt) {
  let call = null;
  if (stmt.type === 'ExpressionStatement') call = stmt.expression;
  else if (stmt.type === 'VariableDeclaration' && stmt.declarations.length === 1) call = stmt.declarations[0].init;
  return call?.type === 'CallExpression' && isPlainValue(call.callee) && call.arguments.every(isPlainValue);
}

// Split a file into runs of consecutive executable statements, each statement carrying its normalised token text
function statementRuns(file, tokens) {
  const runs = [];
  for (const [node] of walk(file.tree)) {
    const key = STATEMENT_LISTS[node.type];
    if (!key) continue;
    let run = [];
    for (const stmt of node[key]) {
      if (!isExecutable(stmt)) {
        if (run.length) runs.push(run);
        run = [];
        continue;
      }
      const from = lowerBound(tokens, stmt.range[0]);
      const to = lowerBound(tokens, stmt.range[1]);
      run.push({
        rel: file.rel,
        text: tokens.slice(from, to).map((t) => t.value).join(' '),
        raw: tokens.slice(from, to).map((t) => t.raw).join(' '),
        count: to - from,
        plainCall: isPlainCall(stmt),
        range: stmt.range,
        startLine: stmt.loc.start.line,
        endLine: stmt.loc.end.line,
      });
    }
    if (run.length) runs.push(run);
  }
  return runs;
}

// ─── Finding duplicates ─────────────────────────────────────────────────────
function indexStatements(runs) {
  const ids = new Map();
  const occurrences = new Map();
  runs.forEach((run, r) => run.forEach((stmt, p) => {
    if (!ids.has(stmt.text)) ids.set(stmt.text, ids.size);
    stmt.id = ids.get(stmt.text);
    if (!occurrences.has(stmt.id)) occurrences.set(stmt.id, []);
    occurrences.get(stmt.id).push([r, p]);
  }));
  return occurrences;
}

// Extend forward from a pair of identical statements; a pair that still aligns on the left is not a start, an earlier pair owns it
function extendPair(runs, [ra, pa], [rb, pb]) {
  const a = runs[ra];
  const b = runs[rb];
  if (pa > 0 && pb > 0 && a[pa - 1].id === b[pb - 1].id) return null;
  let len = 0;
  let tokens = 0;
  while (pa + len < a.length && pb + len < b.length && a[pa + len].id === b[pb + len].id) {
    if (ra === rb && pa + len >= pb) break;
    tokens += a[pa + len].count;
    len += 1;
  }
  if (tokens < MIN_TOKENS) return null;
  const first = a.slice(pa, pa + len);
  const second = b.slice(pb, pb + len);
  if (first.every((s) => s.plainCall) && first.some((s, i) => s.raw !== second[i].raw)) return null;
  return { tokens, first, second };
}

function occurrenceOf(stmts) {
  const first = stmts[0];
  const last = stmts[stmts.length - 1];
  return {
    rel: first.rel,
    range: [first.range[0], last.range[1]],
    startLine: first.startLine,
    location: `${first.rel}:${first.startLine}-${last.endLine}`,
  };
}

function findClones(runs, allow) {
  const groups = new Map();
  for (const list of indexStatements(runs).values()) {
    for (let i = 0; i < list.length; i += 1) {
      for (let j = i + 1; j < list.length; j += 1) {
        const clone = extendPair(runs, list[i], list[j]);
        if (clone) addClone(groups, clone);
      }
    }
  }
  return dropContained(groups, allow);
}

function addClone(groups, { tokens, first, second }) {
  const fingerprint = createHash('sha1')
    .update(first.map((s) => s.text).join(' ')).digest('hex').slice(0, 16);
  if (!groups.has(fingerprint)) groups.set(fingerprint, { tokens, occurrences: new Map() });
  const group = groups.get(fingerprint);
  for (const occ of [occurrenceOf(first), occurrenceOf(second)]) group.occurrences.set(occ.location, occ);
}

// A group whose every occurrence lies inside another, larger duplicate is not reported on its own; occurrences covered by a retention marker do not count
function dropContained(groups, allow) {
  const byFile = new Map();
  for (const group of groups.values()) {
    for (const occ of group.occurrences.values()) {
      if (!byFile.has(occ.rel)) byFile.set(occ.rel, []);
      byFile.get(occ.rel).push(occ);
    }
  }
  const covered = (occ) => byFile.get(occ.rel).some((o) => o !== occ
    && o.range[0] <= occ.range[0] && o.range[1] >= occ.range[1]
    && o.range[1] - o.range[0] > occ.range[1] - occ.range[0]);
  const result = [];
  for (const [fingerprint, group] of [...groups.entries()].sort()) {
    const occs = [...group.occurrences.values()];
    if (occs.every(covered)) continue;
    const kept = occs.filter((o) => !allow.covers(o.rel, o.startLine));
    if (kept.length < 2) continue;
    const locations = kept.map((o) => o.location).sort();
    result.push({
      fingerprint, tokens: group.tokens, locations, first: kept.find((o) => o.location === locations[0]),
    });
  }
  return result;
}

function main() {
  const { root } = parseArgs(process.argv.slice(2));
  const rels = SCAN_DIRS.flatMap((dir) => collectCodeFiles(root, dir)).filter((rel) => !isTestPath(rel));
  const { parsed, parseFailures } = parseFiles(root, rels, { tokens: true });
  const runs = parsed.flatMap((file) => statementRuns(file, normalizeTokens(file.tree.tokens)));
  const allow = collectAllowMarkers(parsed, 'duplication');
  const findings = findClones(runs, allow).map(({ fingerprint, tokens, locations, first }) => ({
    rule: 'duplicate',
    key: fingerprint,
    count: locations.length,
    path: first.rel,
    line: first.startLine,
    message: `duplicated consecutive statements (${tokens} tokens): ${locations.join(', ')}`,
  }));
  emit({
    guard: 'duplication',
    coverage: { planned: rels.length, scanned: parsed.length },
    parseFailures,
    ...allow.items(),
    findings,
  });
}

main();
