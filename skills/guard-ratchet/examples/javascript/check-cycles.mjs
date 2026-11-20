#!/usr/bin/env node
/**
 * Circular-dependency detector: load-time cycles among production code, one finding per cycle.
 *
 * Scans all production code in the repository (tests excluded). Edges come from import /
 * export from / require; import() loads only when execution reaches it, so it is no load-time
 * cycle and not an edge. Every cycle is emitted as a finding (rule: cycle, key: the sorted
 * members); whether it counts as a hard rule is up to the scripts/guard.py policy. Literal
 * in-repo references that cannot be resolved go into unsupported.
 *
 * Usage:
 *   node check-cycles.mjs [--root <dir>]
 *
 * Output: a detector@2 JSON document. Exit codes: 0 scan completed / 1 crash / 2 usage error.
 */

import { collectCodeFiles, emit, isTestPath, parseArgs } from './guard-common.mjs';
import { buildImportGraph } from './import-graph.mjs';

// Tarjan strongly connected components: returns the components with more than one member (the cycles), members sorted by path
function findCycles(edges) {
  let counter = 0;
  const index = new Map();
  const low = new Map();
  const stack = [];
  const onStack = new Set();
  const cycles = [];
  const connect = (v) => {
    index.set(v, counter);
    low.set(v, counter);
    counter += 1;
    stack.push(v);
    onStack.add(v);
    for (const w of edges.get(v) || []) {
      if (!index.has(w)) {
        connect(w);
        low.set(v, Math.min(low.get(v), low.get(w)));
      } else if (onStack.has(w)) low.set(v, Math.min(low.get(v), index.get(w)));
    }
    if (low.get(v) !== index.get(v)) return;
    const members = [];
    let w;
    do {
      w = stack.pop();
      onStack.delete(w);
      members.push(w);
    } while (w !== v);
    if (members.length > 1) cycles.push(members.sort());
  };
  for (const v of edges.keys()) if (!index.has(v)) connect(v);
  return cycles.sort();
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const rels = collectCodeFiles(args.root).filter((rel) => !isTestPath(rel));
  const { parsed, parseFailures, modules, unresolvedStaticImports } = buildImportGraph(args.root, rels);
  const edges = new Map([...modules].map(([rel, { refs }]) => [
    rel, [...new Set(refs.filter((r) => !r.lazy).map((r) => r.target))],
  ]));
  emit({
    guard: 'cycles',
    coverage: {
      planned: rels.length,
      scanned: parsed.length,
      modules: modules.size,
      edges: [...edges.values()].reduce((sum, targets) => sum + targets.length, 0),
    },
    parseFailures,
    unsupported: unresolvedStaticImports.map(({ source, specifier }) => ({
      path: source, message: `cannot resolve static import ${specifier}`,
    })),
    findings: findCycles(edges).map((members) => ({
      rule: 'cycle',
      key: members.join(' <-> '),
      path: members[0],
      line: 1,
      message: `these modules import each other in a cycle: ${members.join(' <-> ')}`,
    })),
  });
}

main();
