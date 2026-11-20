#!/usr/bin/env node
/**
 * Dead-code detector: files nobody references and exports nobody references.
 *
 * It looks at two things only:
 *   1. files that no other file statically references (finding: dead-file, key: the file path);
 *   2. exported names that no other file references (finding: dead-export, key: `path#exportName`).
 * Variables unused inside a function are left to ESLint.
 *
 * How references are recognised is in import-graph.mjs. References from test files count as use;
 * test files themselves and the following entries are not reported:
 *   frontend/src/main.jsx, scripts referenced by frontend/index.html, backend/server.js,
 *   in-repo files named in any package.json main / bin / scripts, hooks/*.js (loaded by directory
 *   through hook-loader), *.config.{js,mjs,cjs} (loaded by filename convention by eslint / vite /
 *   vitest), and the files in CONVENTION_ENTRIES that are loaded by path string or kept for copying.
 * Files in PUBLIC_API are the agreed external surface: once the file itself is referenced, its
 * exports are not reported one by one.
 * Other deliberately retained exports carry `// guard-allow(dead-code): reason` next to the export;
 * the rules are in guard-common.mjs.
 *
 * Usage:
 *   node check-dead-code.mjs [--root <dir>]
 *
 * Output: a detector@2 JSON document. An unreadable package.json and an unresolvable literal
 * in-repo reference go into unsupported. Exit codes: 0 scan completed / 1 crash / 2 usage error.
 */

import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { collectAllowMarkers, collectCodeFiles, collectFiles, emit, isTestPath, parseArgs } from './guard-common.mjs';
import { ALL, buildImportGraph, resolveFile } from './import-graph.mjs';

const ENTRY_FILES = ['frontend/src/main.jsx', 'backend/server.js'];
const HTML_ENTRIES = ['frontend/index.html'];
const HOOK_FILE_RE = /^hooks\/[^/]+\.js$/;
const CONFIG_FILE_RE = /(^|\/)[^/]+\.config\.(js|mjs|cjs)$/;
// Entries not loaded through import: Electron loads the preload by path; hook examples and the shell template are kept for copying and never referenced
const CONVENTION_ENTRIES = [
  /^desktop\/src\/preload\.js$/,
  /^hooks\/examples\/[^/]+\.js$/,
  /^frontend\/src\/shells\/template\//,
];
// Agreed external surface: the component library's single export, the card-writing assistant's only integration point (see CLAUDE.md), and each shell package's entry
const PUBLIC_API = [
  /^frontend\/src\/components\/index\.js$/,
  /^frontend\/src\/core\/features\/assistant\/index\.js$/,
  /^frontend\/src\/shells\/[^/]+\/index\.js$/,
];

// ─── Entries ────────────────────────────────────────────────────────────────
// Returns { entries, unsupported }; an unreadable package.json goes into unsupported instead of silently meaning "no entries"
function packageEntries(root, fileSet) {
  const entries = [];
  const unsupported = [];
  for (const rel of collectFiles(root, '', (name) => name === 'package.json')) {
    const dir = path.posix.dirname(rel);
    let pkg;
    try {
      pkg = JSON.parse(readFileSync(path.join(root, rel), 'utf8'));
    } catch (err) {
      unsupported.push({ path: rel, message: `cannot read package.json: ${err.message}` });
      continue;
    }
    const bins = typeof pkg.bin === 'string' ? [pkg.bin] : Object.values(pkg.bin || {});
    const words = Object.values(pkg.scripts || {})
      .flatMap((cmd) => cmd.split(/\s+/))
      .map((w) => w.replace(/^['"]|['"]$/g, ''))
      .filter((w) => w && !w.startsWith('-'));
    for (const target of [pkg.main, ...bins, ...words]) {
      if (typeof target !== 'string') continue;
      const hit = resolveFile(fileSet, path.posix.join(dir, target));
      if (hit) entries.push(hit);
    }
  }
  return { entries, unsupported };
}

function htmlEntries(root, fileSet) {
  const entries = [];
  for (const rel of HTML_ENTRIES) {
    const abs = path.join(root, rel);
    if (!existsSync(abs)) continue;
    const dir = path.posix.dirname(rel);
    for (const [, src] of readFileSync(abs, 'utf8').matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/g)) {
      const hit = resolveFile(fileSet, path.posix.join(dir, src.replace(/^\//, '')));
      if (hit) entries.push(hit);
    }
  }
  return entries;
}

function collectEntries(root, rels, fileSet, packageFiles) {
  return new Set([
    ...ENTRY_FILES.filter((rel) => fileSet.has(rel)),
    ...htmlEntries(root, fileSet),
    ...packageFiles,
    ...rels.filter((rel) => HOOK_FILE_RE.test(rel) || CONFIG_FILE_RE.test(rel) || isTestPath(rel)
      || CONVENTION_ENTRIES.some((re) => re.test(rel))),
  ]);
}

// ─── Summary ────────────────────────────────────────────────────────────────
function main() {
  const { root } = parseArgs(process.argv.slice(2));
  const rels = collectCodeFiles(root);
  const { fileSet, parsed, parseFailures, modules, unresolvedStaticImports } = buildImportGraph(root, rels);
  const allow = collectAllowMarkers(parsed, 'dead-code');
  const referencedBy = new Map();
  const usedNames = new Map();
  const edges = new Set();
  for (const [rel, { refs }] of modules) {
    for (const { target, names } of refs) {
      edges.add(`${rel} -> ${target}`);
      if (!referencedBy.has(target)) referencedBy.set(target, new Set());
      referencedBy.get(target).add(rel);
      if (!usedNames.has(target)) usedNames.set(target, new Set());
      names.forEach((n) => usedNames.get(target).add(n));
    }
  }

  const packages = packageEntries(root, fileSet);
  const entries = collectEntries(root, rels, fileSet, packages.entries);
  const findings = rels.filter((rel) => !entries.has(rel) && !referencedBy.has(rel))
    .map((rel) => ({ rule: 'dead-file', key: rel, path: rel, line: 1, message: 'no other file references this file' }));
  for (const [rel, { exports: declared }] of modules) {
    if (entries.has(rel) || !referencedBy.has(rel) || PUBLIC_API.some((re) => re.test(rel))) continue;
    const used = usedNames.get(rel);
    if (used.has(ALL)) continue;
    findings.push(...declared
      .filter(({ name, line }) => !used.has(name) && !allow.covers(rel, line))
      .map(({ name, line }) => ({
        rule: 'dead-export', key: `${rel}#${name}`, path: rel, line, message: 'no other file references this export',
      })));
  }

  emit({
    guard: 'dead-code',
    coverage: { planned: rels.length, scanned: parsed.length, modules: modules.size, edges: edges.size },
    parseFailures,
    unsupported: [
      ...packages.unsupported,
      ...unresolvedStaticImports.map(({ source, specifier }) => ({
        path: source, message: `cannot resolve static import ${specifier}`,
      })),
    ],
    ...allow.items(),
    findings,
  });
}

main();
