#!/usr/bin/env node
/**
 * Architecture-boundary reference detector: finds a few fixed forbidden dependencies with the
 * in-repo dependency graph.
 *
 * The directories in the rules are only examples. When porting to a real repository, confirm the
 * module boundaries first, then replace ARCH_RULES. Every violation is emitted as a finding (rule is
 * the rule name, key is `source module -> target module`, one finding per module pair); whether the
 * rule is hard or tolerates legacy is up to the scripts/guard.py policy.
 *
 * Usage:
 *   node check-architecture.mjs [--root <dir>]
 *
 * Scans production code, excluding tests, dependencies, build output, coverage, data and
 * dot-directories. Variable dynamic imports are not part of the static graph; literal in-repo
 * references that cannot be resolved go into unsupported.
 * Output: a detector@2 JSON document. Exit codes: 0 scan completed / 1 crash / 2 usage error.
 */

import { collectCodeFiles, emit, isTestPath, parseArgs } from './guard-common.mjs';
import { buildImportGraph } from './import-graph.mjs';

// Only illustrates how to write rules; replace with the real repository's directory conventions before use.
const ARCH_RULES = [
  { rule: 'forbidden-dependency', from: /^frontend\//, to: /^backend\/db\// },
  { rule: 'forbidden-dependency', from: /^backend\/routes\//, to: /^backend\/db\// },
  {
    rule: 'internal-api-import',
    from: /^features\/[^/]+\//,
    to: /^features\/[^/]+\/(?:internal|src|private)\//,
    crossFeature: true,
  },
];

function featureName(rel) {
  const match = /^features\/([^/]+)\//.exec(rel);
  return match?.[1] ?? null;
}

function violates(rule, source, target) {
  if (!rule.from.test(source) || !rule.to.test(target)) return false;
  if (rule.crossFeature && featureName(source) === featureName(target)) return false;
  return true;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const rels = collectCodeFiles(args.root).filter((rel) => !isTestPath(rel));
  const graph = buildImportGraph(args.root, rels);
  const findings = new Map();
  const edges = new Set();
  for (const [source, mod] of graph.modules) {
    for (const { target, line } of mod.refs) {
      const key = `${source} -> ${target}`;
      edges.add(key);
      for (const rule of ARCH_RULES) {
        const id = `${rule.rule}\0${key}`;
        if (violates(rule, source, target) && !findings.has(id)) {
          findings.set(id, { rule: rule.rule, key, path: source, line });
        }
      }
    }
  }
  emit({
    guard: 'architecture',
    coverage: { planned: rels.length, scanned: graph.parsed.length, modules: graph.modules.size, edges: edges.size },
    parseFailures: graph.parseFailures,
    unsupported: graph.unresolvedStaticImports.map(({ source, specifier }) => ({
      path: source, message: `cannot resolve static import ${specifier}`,
    })),
    findings: [...findings.values()],
  });
}

main();
