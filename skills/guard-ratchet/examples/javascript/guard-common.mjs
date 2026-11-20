/**
 * Shared detector pieces: repository traversal, espree parsing, command-line arguments,
 * detector@2 output, and the intentional-retention marker.
 *
 * Detectors only measure: stdout carries one guard-ratchet/detector@2 JSON document. Baselines,
 * new/worse/stale comparison, exceptions, thresholds and coverage floors all belong to
 * scripts/guard.py. Nothing here reads or writes a baseline or decides pass/fail.
 *
 * Intentional-retention marker: for code a detector cannot tell is deliberate, write next to it
 *   // guard-allow(<guard name>): <reason>
 * The marker sits on its own line and covers the statement right after it, plus the following
 * sibling statements that touch it with no blank line in between. Covered findings are not
 * emitted; the marker travels with the code, so moving or renaming does not invalidate it.
 * Every valid marker is listed as advisory (rule: guard-allow). A marker with no reason, a wrong
 * guard name, no code after it, or no violation left in its range is hard
 * (rule: guard-allow-invalid).
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const espree = require('espree');

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SCHEMA = 'guard-ratchet/detector@2';
const TOOL_VERSION = '2.0.0';

export const CODE_SUFFIXES = new Set(['.js', '.jsx', '.mjs', '.cjs']);
const SKIP_DIRS = new Set([
  'node_modules', 'vendor', 'generated', 'dist', 'coverage', 'build', 'test-results', 'data', 'node-runtime',
  '__pycache__',
]);

export function isTestPath(rel) {
  return /(^|\/)(tests|__tests__)\//.test(rel) || /\.(test|spec)\.[^./]+$/.test(rel);
}

const isCodeFile = (name) => CODE_SUFFIXES.has(path.extname(name).toLowerCase());

// Files under root/relDir whose name satisfies accept (relative to root, `/` separated, sorted);
// empty when relDir does not exist. Files and directories for which ignore(rel) is true are skipped.
export function collectFiles(root, relDir = '', accept = isCodeFile, ignore = () => false) {
  const out = [];
  const start = path.join(root, relDir);
  if (existsSync(start)) walkDir(start, relDir, accept, ignore, out);
  return out.sort();
}

export function collectCodeFiles(root, relDir = '', ignore = undefined) {
  return collectFiles(root, relDir, isCodeFile, ignore);
}

function walkDir(dir, relPrefix, accept, ignore, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) continue;
    const rel = relPrefix ? `${relPrefix}/${entry.name}` : entry.name;
    if (ignore(rel)) continue;
    if (entry.isDirectory()) {
      if (entry.name.startsWith('.') || SKIP_DIRS.has(entry.name)) continue;
      walkDir(path.join(dir, entry.name), rel, accept, ignore, out);
    } else if (entry.isFile() && accept(entry.name)) {
      out.push(rel);
    }
  }
}

function parseCode(text, { tokens = false } = {}) {
  for (const sourceType of ['module', 'script']) {
    try {
      return espree.parse(text, {
        ecmaVersion: 'latest',
        sourceType,
        ecmaFeatures: { jsx: true },
        loc: true,
        range: true,
        tokens,
        comment: true,
      });
    } catch { /* try the next sourceType */ }
  }
  return null;
}

// Read and parse a batch of files; relative paths that fail to parse go into parseFailures
export function parseFiles(root, rels, options) {
  const parsed = [];
  const parseFailures = [];
  for (const rel of rels) {
    const text = readFileSync(path.join(root, rel), 'utf8');
    const tree = parseCode(text, options);
    if (tree) parsed.push({ rel, text, tree });
    else parseFailures.push(rel);
  }
  return { parsed, parseFailures };
}

// comments / tokens are the parser's attached comment and token lists, not syntax-tree nodes
const SKIP_KEYS = new Set(['loc', 'range', 'parent', 'comments', 'tokens']);

// When prune(node, parent) is true the node is yielded but not descended into
export function* walk(node, parent = null, prune = null) {
  if (!node || typeof node.type !== 'string') return;
  yield [node, parent];
  if (prune?.(node, parent)) return;
  for (const key of Object.keys(node)) {
    if (SKIP_KEYS.has(key)) continue;
    const value = node[key];
    if (Array.isArray(value)) {
      for (const child of value) if (child && typeof child.type === 'string') yield* walk(child, node, prune);
    } else if (value && typeof value.type === 'string') {
      yield* walk(value, node, prune);
    }
  }
}

export function patternNames(pattern, out = []) {
  if (!pattern) return out;
  if (pattern.type === 'Identifier') out.push(pattern.name);
  else if (pattern.type === 'VariableDeclaration') pattern.declarations.forEach((d) => patternNames(d.id, out));
  else if (pattern.type === 'ObjectPattern') pattern.properties.forEach((p) => patternNames(p.value ?? p.argument, out));
  else if (pattern.type === 'ArrayPattern') pattern.elements.forEach((e) => patternNames(e, out));
  else if (pattern.type === 'RestElement') patternNames(pattern.argument, out);
  else if (pattern.type === 'AssignmentPattern') patternNames(pattern.left, out);
  return out;
}

export function stringValue(node) {
  if (node?.type === 'Literal' && typeof node.value === 'string') return node.value;
  if (node?.type === 'TemplateLiteral' && node.expressions.length === 0) return node.quasis[0].value.cooked;
  return null;
}

// ─── CLI and output ─────────────────────────────────────────────────────────
export function usageError(message) {
  console.error(`error: ${message}`);
  process.exit(2);
}

// Common arguments: --root <dir>; ignore enables --ignore <glob> (repeatable); paths enables positional
// arguments. Anything else exits 2. Baseline arguments no longer exist: scripts/guard.py owns the ratchet.
export function parseArgs(argv, { ignore = false, paths = false } = {}) {
  const args = { root: REPO_ROOT, ignores: [], paths: [] };
  const valueOf = (i, flag) => {
    if (i >= argv.length) usageError(`${flag} requires a value`);
    return argv[i];
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--root') args.root = path.resolve(valueOf(++i, arg));
    else if (ignore && arg === '--ignore') args.ignores.push(valueOf(++i, arg));
    else if (paths && !arg.startsWith('-')) args.paths.push(arg);
    else usageError(`unknown argument: ${arg}`);
  }
  return args;
}

const compare = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

// From the second occurrence of the same (rule, key) on, append ~2 ~3. Numbering follows order of
// appearance, so adding entries elsewhere never renumbers existing keys.
export function dedupeKeys(items) {
  const seen = new Map();
  return items.map((item) => {
    const id = `${item.rule ?? item.metric}\0${item.key}`;
    const n = (seen.get(id) || 0) + 1;
    seen.set(id, n);
    return n > 1 ? { ...item, key: `${item.key} ~${n}` } : item;
  });
}

const byKey = (a, b) => compare(a.key, b.key) || compare(a.rule ?? a.metric, b.rule ?? b.metric);
const ruleItem = ({ rule, key, path: file, line, message }) => ({ rule, key, path: file, line, message });

/**
 * Print a guard-ratchet/detector@2 document: fill defaults, sort every array, print one JSON object.
 * `guard` is the guard name and the tool name is always check-<guard>.mjs. coverage needs planned and
 * scanned; the rest are numeric counters. Exit code stays 0 once the scan ran, even with findings;
 * scripts/guard.py decides what fails.
 */
export function emit({
  guard, coverage: { planned, scanned, ...counters }, parseFailures = [], unsupported = [],
  hard = [], advisory = [], findings = [], metrics = [],
}) {
  const doc = {
    schema: SCHEMA,
    guard,
    tool: { name: `check-${guard}.mjs`, version: TOOL_VERSION },
    coverage: { planned, scanned, unit: 'files', ...counters },
    parse_failures: [...parseFailures].sort(),
    unsupported: unsupported.map(({ path: file, message }) => ({ path: file, message }))
      .sort((a, b) => compare(a.path, b.path) || compare(a.message, b.message)),
    hard: hard.map(ruleItem).sort(byKey),
    advisory: advisory.map(ruleItem).sort(byKey),
    findings: findings.map(({ count = 1, ...rest }) => {
      const { rule, key, path: file, line, message } = ruleItem(rest);
      return { rule, key, count, path: file, line, ...(message === undefined ? {} : { message }) };
    }).sort(byKey),
    metrics: metrics.map(({ metric, key, path: file, line, value }) => ({ metric, key, path: file, line, value }))
      .sort(byKey),
  };
  process.stdout.write(`${JSON.stringify(doc, null, 2)}\n`);
}

// ─── Intentional-retention markers ──────────────────────────────────────────
const ALLOW_GUARDS = ['dead-code', 'duplication', 'perf-shape', 'tests'];
const ALLOW_RE = /^\s*\*?\s*guard-allow\(([^)]*)\)\s*(?::\s*(.*?))?\s*$/s;

// The largest statement/expression node starting on each line, with its parent
function lineStarts(tree) {
  const byLine = new Map();
  for (const [node, parent] of walk(tree)) {
    if (node === tree || !node.loc) continue;
    const line = node.loc.start.line;
    const size = node.range[1] - node.range[0];
    const prev = byLine.get(line);
    if (!prev || size > prev.size) byLine.set(line, { node, parent, size });
  }
  return byLine;
}

function siblingsOf(node, parent) {
  if (!parent) return null;
  for (const value of Object.values(parent)) {
    if (Array.isArray(value) && value.includes(node)) return value;
  }
  return null;
}

// Line range [start, end] a marker covers: the first node plus the sibling nodes right after it with no blank line between
function coverage(tree, comment, byLine) {
  let line = comment.loc.end.line + 1;
  while (line <= tree.loc.end.line && !byLine.has(line)) line += 1;
  const hit = byLine.get(line);
  if (!hit) return null;
  let end = hit.node.loc.end.line;
  const siblings = siblingsOf(hit.node, hit.parent) ?? [];
  for (const next of siblings.slice(siblings.indexOf(hit.node) + 1)) {
    if (next.loc.start.line !== end + 1) break;
    end = next.loc.end.line;
  }
  return [line, end];
}

class AllowMarkers {
  constructor(markers, invalid) {
    this.markers = markers;
    this.invalid = invalid;
  }

  // Whether a finding location is covered by a marker; covering markers are recorded as used
  covers(rel, line) {
    const hits = this.markers.filter((m) => m.rel === rel && line >= m.range[0] && line <= m.range[1]);
    hits.forEach((m) => { m.used = true; });
    return hits.length > 0;
  }

  // Call after detection. advisory: every valid marker; hard: malformed markers and markers whose range has no violation left
  items() {
    const advisory = this.markers.map((m) => ({
      rule: 'guard-allow', key: `${m.rel}#${m.reason}`, path: m.rel, line: m.line, message: m.reason,
    }));
    const unused = this.markers.filter((m) => !m.used).map((m) => ({
      rel: m.rel, line: m.line, kind: `unused:${m.reason}`, message: `the covered code no longer has a ${m.guard} violation; delete this marker`,
    }));
    const hard = [...this.invalid, ...unused].map((p) => ({
      rule: 'guard-allow-invalid', key: `${p.rel}#${p.kind}`, path: p.rel, line: p.line, message: p.message,
    }));
    return { advisory: dedupeKeys(advisory), hard: dedupeKeys(hard) };
  }
}

/** Collect the markers for `guard` in the parsed files and return an AllowMarkers */
export function collectAllowMarkers(parsed, guard) {
  const markers = [];
  const invalid = [];
  for (const file of parsed) {
    const byLine = lineStarts(file.tree);
    for (const comment of file.tree.comments || []) {
      const match = ALLOW_RE.exec(comment.value);
      if (!match) continue;
      const line = comment.loc.start.line;
      const name = match[1].trim();
      const reason = (match[2] ?? '').trim();
      const range = coverage(file.tree, comment, byLine);
      const problem = (kind, message) => invalid.push({ rel: file.rel, line, kind, message });
      if (!ALLOW_GUARDS.includes(name)) problem(`unknown-guard:${name}`, `guard name \`${name}\` does not exist (available: ${ALLOW_GUARDS.join(', ')})`);
      else if (name !== guard) continue;
      else if (!reason) problem(`missing-reason:${name}`, `marker has no reason: write \`guard-allow(${name}): why this is deliberate\``);
      else if (!range) problem(`no-target:${name}`, 'no code after the marker to cover');
      else markers.push({ rel: file.rel, line, guard, reason, range, used: false });
    }
  }
  return new AllowMarkers(markers, invalid);
}
