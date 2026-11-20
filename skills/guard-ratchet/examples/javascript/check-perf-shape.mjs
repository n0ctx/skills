#!/usr/bin/env node
/**
 * Run-shape detector: looks at code shape only; no complexity annotation, no timing.
 *
 * Scans production code (tests excluded) in frontend/src, backend, assistant/server and
 * assistant/client/src. A loop means for / for-of / for-in / while / do-while and a forEach
 * callback; the per-item query rule also treats array-iteration callbacks such as
 * map / filter / reduce as loop bodies.
 *
 * hard (writing that should never be accepted):
 *   deep-loop: loops nested three deep where the innermost loop body references an outer loop
 *     variable. Two levels are not reported.
 *
 * findings (existing offenders are compared by scripts/guard.py):
 *   loop-query: inside a loop body, a call to .prepare(, a .get( / .all( / .run( on a prepared
 *     Statement, or a call to a query function imported from backend/db/queries/ that really
 *     touches the database (querying once and matching in memory is not in a loop, so it is not
 *     reported; pure functions in the query directory that never touch the database are not queries).
 *     Exception: in a transaction, running a Statement prepared outside the loop once per item
 *     is the batch-write pattern better-sqlite3 recommends and is not reported. "In a transaction"
 *     means inside a .transaction( callback, or inside a function that, in this file, is only
 *     called from transaction callbacks.
 *   unbounded-select: a SELECT with neither WHERE nor LIMIT in backend/app, backend/routes or
 *     backend/services (except backend/services/import-export.js).
 *
 * Deliberate patterns the detector cannot tell apart (one-off migrations, per-item writes with a
 * small fixed bound on the field count) carry `// guard-allow(perf-shape): reason` next to the
 * statement; the rules are in guard-common.mjs.
 *
 * Usage:
 *   node check-perf-shape.mjs [--root <dir>]
 *
 * Output: a detector@2 JSON document. Exit codes: 0 scan completed / 1 crash / 2 usage error.
 */

import path from 'node:path';
import { buildImportGraph } from './import-graph.mjs';
import {
  collectAllowMarkers, collectCodeFiles, dedupeKeys, emit, isTestPath, parseArgs, parseFiles, patternNames, stringValue, walk,
} from './guard-common.mjs';

const SCAN_DIRS = ['frontend/src', 'backend', 'assistant/server', 'assistant/client/src'];
const SQL_DIRS = ['backend/app/', 'backend/routes/', 'backend/services/'];
const SQL_EXEMPT = new Set(['backend/services/import-export.js']);
const MAX_LOOP_DEPTH = 3;

const LOOP_STATEMENTS = new Set(['ForStatement', 'ForInStatement', 'ForOfStatement', 'WhileStatement', 'DoWhileStatement']);
const FUNCTION_TYPES = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression']);
const STATEMENT_METHODS = new Set(['get', 'all', 'run']);
const ITERATION_METHODS = new Set(['map', 'flatMap', 'filter', 'reduce', 'some', 'every', 'find', 'findIndex']);
const QUERY_DIR = 'backend/db/queries/';
const DB_MODULE = 'backend/db/index.js';
const DB_METHODS = new Set(['prepare', 'exec', 'transaction', 'pragma']);

// ─── AST helpers ────────────────────────────────────────────────────────────
// comments / tokens are the parser's attached comment and token lists, not syntax-tree nodes
const SKIP_KEYS = new Set(['loc', 'range', 'parent', 'comments', 'tokens']);

function* children(node) {
  for (const key of Object.keys(node)) {
    if (SKIP_KEYS.has(key)) continue;
    const value = node[key];
    if (Array.isArray(value)) {
      for (const child of value) if (child && typeof child.type === 'string') yield child;
    } else if (value && typeof value.type === 'string') {
      yield value;
    }
  }
}

const isMethodCall = (node, names) => node?.type === 'CallExpression'
  && node.callee.type === 'MemberExpression' && !node.callee.computed && names.has(node.callee.property.name);

function isForEach(node) {
  return isMethodCall(node, new Set(['forEach'])) && FUNCTION_TYPES.has(node.arguments[0]?.type);
}

// Loop node -> { body, vars }; vars are the loop variables this level declares
function loopOf(node) {
  if (isForEach(node)) return { body: node.arguments[0], vars: node.arguments[0].params.flatMap((p) => patternNames(p)) };
  if (!LOOP_STATEMENTS.has(node.type)) return null;
  if (node.type === 'ForStatement') {
    const init = node.init?.type === 'AssignmentExpression' ? node.init.left : node.init;
    return { body: node.body, vars: patternNames(init) };
  }
  return { body: node.body, vars: patternNames(node.left) };
}

function functionName(node, parent) {
  if (node.id?.name) return node.id.name;
  if (parent?.type === 'VariableDeclarator' && parent.id.type === 'Identifier') return parent.id.name;
  if ((parent?.type === 'MethodDefinition' || parent?.type === 'Property') && parent.key) {
    return parent.key.name || parent.key.value || null;
  }
  return null;
}

// Referenced variable names (excluding property names such as the b in a.b or in { b: 1 })
function referencedNames(root) {
  const names = new Set();
  for (const [node, parent] of walk(root)) {
    if (node.type !== 'Identifier') continue;
    if (parent?.type === 'MemberExpression' && parent.property === node && !parent.computed) continue;
    if ((parent?.type === 'Property' || parent?.type === 'MethodDefinition')
        && parent.key === node && !parent.computed && !parent.shorthand) continue;
    names.add(node.name);
  }
  return names;
}

// Statement variable names obtained from .prepare(...) in the file
function statementNames(tree) {
  const names = new Set();
  for (const [node] of walk(tree)) {
    if (node.type === 'VariableDeclarator' && node.id.type === 'Identifier'
        && isMethodCall(node.init, new Set(['prepare']))) names.add(node.id.name);
  }
  return names;
}

function importTarget(file, node) {
  if (node.type !== 'ImportDeclaration' || !node.source.value.startsWith('.')) return null;
  const target = path.posix.join(path.posix.dirname(file.rel), node.source.value);
  return target.endsWith('.js') ? target : `${target}.js`;
}

// ─── Which query-layer exports really touch the database ────────────────────
// Returns Map<query file, Set<export names that touch the database>>. Using the db module directly,
// calling prepare/exec/transaction, or calling a local function or another query file's export that
// touches the database all count as access; an export of unrecognised shape always counts as access.
function queryShape(file) {
  const imports = new Map();
  const namespaces = new Map();
  const dbLocals = new Set();
  const locals = new Map();
  const exported = new Map();
  for (const node of file.tree.body) {
    const target = importTarget(file, node);
    if (target) {
      for (const spec of node.specifiers) {
        if (target === DB_MODULE) dbLocals.add(spec.local.name);
        else if (target.startsWith(QUERY_DIR)) {
          if (spec.type === 'ImportNamespaceSpecifier') namespaces.set(spec.local.name, { target });
          else imports.set(spec.local.name, { target, name: spec.imported?.name ?? 'default' });
        }
      }
    }
    const decl = node.type === 'ExportNamedDeclaration' ? node.declaration : node;
    if (decl?.type === 'FunctionDeclaration') {
      locals.set(decl.id.name, decl);
      if (decl !== node) exported.set(decl.id.name, decl.id.name);
    } else if (decl?.type === 'VariableDeclaration') {
      for (const d of decl.declarations) {
        const fn = FUNCTION_TYPES.has(d.init?.type) ? d.init : null;
        for (const name of patternNames(d.id)) {
          locals.set(name, fn);
          if (decl !== node) exported.set(name, name);
        }
      }
    }
    if (node.type === 'ExportNamedDeclaration' && !node.declaration) {
      for (const spec of node.specifiers) {
        const local = spec.local.name;
        if (node.source) imports.set(`#reexport:${spec.exported.name}`, { target: importTarget(file, node), name: local });
        exported.set(spec.exported.name, node.source ? `#reexport:${spec.exported.name}` : local);
      }
    } else if (node.type === 'ExportDefaultDeclaration') {
      const decl = node.declaration;
      const local = decl.id?.name ?? (decl.type === 'Identifier' ? decl.name : '#default');
      if (FUNCTION_TYPES.has(decl.type)) locals.set(local, decl);
      else if (!locals.has(local)) locals.set(local, null);
      exported.set('default', local);
    }
  }
  return { imports, namespaces, dbLocals, locals, exported, statements: statementNames(file.tree) };
}

const DB_READ = 'db-read';
const DB_WRITE = 'db-write';
const ALL_DB_EFFECTS = new Set([DB_READ, DB_WRITE]);

function sqlEffects(node) {
  const text = sqlText(node);
  if (text === null) return new Set(ALL_DB_EFFECTS);
  if (/^\s*(SELECT|EXPLAIN)\b/i.test(text)) return new Set([DB_READ]);
  if (/^\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|VACUUM|ATTACH|DETACH)\b/i.test(text)) {
    return new Set([DB_WRITE]);
  }
  return new Set(ALL_DB_EFFECTS);
}

function directEffects(fnNode, shape) {
  const effects = new Set();
  const nodes = [...walk(fnNode)];
  const parents = new Map(nodes.map(([node, parent]) => [node, parent]));
  for (const [node, parent] of nodes) {
    if (node.type === 'Identifier' && shape.dbLocals.has(node.name)) {
      const call = parent?.type === 'MemberExpression' && parent.object === node ? parents.get(parent) : null;
      const isDatabaseCall = call?.type === 'CallExpression' && call.callee === parent;
      if (!isDatabaseCall) ALL_DB_EFFECTS.forEach((effect) => effects.add(effect));
    }
    if (node.type !== 'CallExpression' || node.callee.type !== 'MemberExpression') continue;
    const { object, property } = node.callee;
    const method = node.callee.computed ? stringValue(property) : property.name;
    const dbObject = object.type === 'Identifier' && shape.dbLocals.has(object.name);
    const prepared = object.type === 'CallExpression' && isMethodCall(object, new Set(['prepare']));
    const statement = object.type === 'Identifier' && shape.statements.has(object.name);

    if (['get', 'all'].includes(method) && (dbObject || prepared || statement)) effects.add(DB_READ);
    else if (method === 'run' && (dbObject || prepared || statement)) effects.add(DB_WRITE);
    else if (DB_METHODS.has(method)) sqlEffects(node.arguments[0]).forEach((effect) => effects.add(effect));
    else if (dbObject) ALL_DB_EFFECTS.forEach((effect) => effects.add(effect));
  }
  return effects;
}

function calledNames(fnNode, shape) {
  const names = new Set();
  for (const [node] of walk(fnNode)) {
    if (node.type !== 'CallExpression') continue;
    if (node.callee.type === 'Identifier') names.add(node.callee.name);
    else if (node.callee.type === 'MemberExpression' && !node.callee.computed
        && node.callee.object.type === 'Identifier' && shape.namespaces.has(node.callee.object.name)) {
      names.add(`${node.callee.object.name}.${node.callee.property.name}`);
    }
  }
  return names;
}

function dbEffectsByExport(parsed) {
  const shapes = new Map(parsed.filter((f) => f.rel.startsWith(QUERY_DIR)).map((f) => [f.rel, queryShape(f)]));
  const effects = new Map();
  for (const [rel, shape] of shapes) {
    const localEffects = new Map();
    for (const [name, fn] of shape.locals) {
      localEffects.set(name, fn ? directEffects(fn, shape) : new Set(ALL_DB_EFFECTS));
    }
    effects.set(rel, localEffects);
  }

  const importedEffects = (shape, local, seen = new Set()) => {
    let ref = shape.imports.get(local);
    if (!ref) {
      const dot = local.indexOf('.');
      const namespace = dot > 0 ? shape.namespaces.get(local.slice(0, dot)) : null;
      if (namespace) ref = { target: namespace.target, name: local.slice(dot + 1) };
    }
    if (!ref) return new Set();
    const refKey = `${ref.target}:${ref.name}`;
    if (seen.has(refKey)) return new Set(ALL_DB_EFFECTS);
    const other = shapes.get(ref.target);
    if (!other) return new Set(ALL_DB_EFFECTS);
    const resolved = other.exported.get(ref.name);
    if (resolved === undefined) return new Set(ALL_DB_EFFECTS);
    const known = effects.get(ref.target).get(resolved);
    if (known) return known;
    if (other.imports.has(resolved)) return importedEffects(other, resolved, new Set([...seen, refKey]));
    return new Set(ALL_DB_EFFECTS);
  };

  let changed = true;
  while (changed) {
    changed = false;
    for (const [rel, shape] of shapes) {
      const localEffects = effects.get(rel);
      for (const [name, fn] of shape.locals) {
        if (!fn) continue;
        const current = localEffects.get(name);
        const calls = calledNames(fn, shape);
        for (const callee of calls) {
          const calledEffects = localEffects.get(callee) ?? importedEffects(shape, callee);
          for (const effect of calledEffects) {
            if (!current.has(effect)) {
              current.add(effect);
              changed = true;
            }
          }
        }
      }
    }
  }

  const result = new Map();
  for (const [rel, shape] of shapes) {
    const exportedEffects = new Map();
    for (const [name, local] of shape.exported) {
      exportedEffects.set(name, effects.get(rel).get(local) ?? importedEffects(shape, local));
    }
    result.set(rel, exportedEffects);
  }
  let dbReadExports = 0;
  let dbWriteExports = 0;
  for (const exports of result.values()) {
    for (const effectSet of exports.values()) {
      if (effectSet.has(DB_READ)) dbReadExports += 1;
      if (effectSet.has(DB_WRITE)) dbWriteExports += 1;
    }
  }
  return { byExport: result, dbReadExports, dbWriteExports };
}

// Local names imported from the query layer that have a database effect; namespace imports check each export.
function queryImports(file, effectsByExport) {
  const names = new Set();
  const namespaces = new Set();
  for (const node of file.tree.body) {
    const target = importTarget(file, node);
    if (!target?.startsWith(QUERY_DIR)) continue;
    const effects = effectsByExport.get(target);
    for (const spec of node.specifiers) {
      if (spec.type === 'ImportNamespaceSpecifier') {
        if (!effects) namespaces.add(`${spec.local.name}.*`);
        else for (const [name, effectSet] of effects) {
          if (effectSet.size) namespaces.add(`${spec.local.name}.${name}`);
        }
      } else if (!effects || effects.get(spec.imported?.name ?? 'default')?.size) names.add(spec.local.name);
    }
  }
  return { names, namespaces };
}

// ─── Transaction context ────────────────────────────────────────────────────
// Transaction callbacks, and unexported functions that in this file are only called from transaction callbacks
function transactionalFunctions(tree) {
  const tx = new Set();
  const declared = new Map();
  const exported = new Set();
  for (const [node, parent] of walk(tree)) {
    if (isMethodCall(node, new Set(['transaction'])) && FUNCTION_TYPES.has(node.arguments[0]?.type)) tx.add(node.arguments[0]);
    const name = node.type === 'FunctionDeclaration' ? node.id?.name
      : FUNCTION_TYPES.has(node.type) && parent?.type === 'VariableDeclarator' && parent.id.type === 'Identifier' ? parent.id.name : null;
    if (name) declared.set(name, node);
    if (node.type === 'ExportNamedDeclaration' && node.declaration) {
      patternNames(node.declaration.type === 'VariableDeclaration' ? node.declaration : node.declaration.id)
        .forEach((n) => exported.add(n));
    }
    if (node.type === 'ExportNamedDeclaration' && !node.source) node.specifiers.forEach((sp) => exported.add(sp.local.name));
  }
  const calls = [];
  for (const [node] of walk(tree)) {
    if (node.type === 'CallExpression' && node.callee.type === 'Identifier' && declared.has(node.callee.name)) calls.push(node);
  }
  const inside = (node) => [...tx].some((fn) => fn.range[0] <= node.range[0] && node.range[1] <= fn.range[1]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const [name, fn] of declared) {
      if (tx.has(fn) || exported.has(name)) continue;
      const sites = calls.filter((c) => c.callee.name === name);
      if (sites.length && sites.every(inside)) {
        tx.add(fn);
        changed = true;
      }
    }
  }
  return tx;
}

// ─── Rules ──────────────────────────────────────────────────────────────────
function loopQueryCall(node, { stmtNames, queries }) {
  const { callee } = node;
  if (callee.type === 'Identifier' && queries.names.has(callee.name)) return callee.name;
  if (callee.type === 'MemberExpression' && !callee.computed && callee.object.type === 'Identifier'
      && (queries.namespaces.has(`${callee.object.name}.${callee.property.name}`)
        || queries.namespaces.has(`${callee.object.name}.*`))) return `${callee.object.name}.${callee.property.name}`;
  if (isMethodCall(node, new Set(['prepare']))) {
    const obj = node.callee.object;
    return obj.type === 'Identifier' ? `${obj.name}.prepare` : '.prepare';
  }
  if (isMethodCall(node, STATEMENT_METHODS) && node.callee.object.type === 'Identifier'
      && stmtNames.has(node.callee.object.name)) {
    return `${node.callee.object.name}.${node.callee.property.name}`;
  }
  return null;
}

function sqlText(node) {
  if (node.type === 'Literal' && typeof node.value === 'string') return node.value;
  if (node.type === 'TemplateLiteral') return node.quasis.map((q) => q.value.cooked ?? '').join(' ${} ');
  return null;
}

function unfilteredSelects(text) {
  return text.split(';')
    .filter((stmt) => /\bSELECT\b[\s\S]*\bFROM\b/i.test(stmt) && !/\b(WHERE|LIMIT)\b/i.test(stmt))
    .map((stmt) => stmt.replace(/\s+/g, ' ').trim().slice(0, 80));
}

function checkDeepLoop(loopNode, body, outerLoops, state, ctx) {
  const outerVars = new Set(outerLoops.flatMap((l) => l.vars));
  const used = [...referencedNames(body)].filter((n) => outerVars.has(n)).sort();
  if (!used.length) return;
  ctx.found.deepLoops.push({
    rule: 'deep-loop',
    key: `${ctx.file.rel}#${state.fn}#${used.join(',')}`,
    path: ctx.file.rel,
    line: loopNode.loc.start.line,
    message: `loops nested ${outerLoops.length + 1} deep and the innermost references outer loop variable(s) ${used.join(', ')}; build an index by key first, then iterate once`,
  });
}

// Per-item writes of a prepared Statement inside a transaction (a .prepare that is itself in a loop is reported separately)
function isBatchWrite(node, state, ctx) {
  return state.inTx && isMethodCall(node, new Set(['run'])) && node.callee.object.type === 'Identifier'
    && ctx.stmtNames.has(node.callee.object.name);
}

function inspectNode(node, state, ctx) {
  if ((state.loops.length || state.perItem) && node.type === 'CallExpression' && !isBatchWrite(node, state, ctx)) {
    const call = loopQueryCall(node, ctx);
    if (call && !ctx.allow.covers(ctx.file.rel, node.loc.start.line)) {
      ctx.found.loopQueries.push({
        rule: 'loop-query',
        key: `${ctx.file.rel}#${state.fn}#${call}`,
        path: ctx.file.rel,
        line: node.loc.start.line,
        message: `per-item query ${call} inside a loop; query once and match in memory`,
      });
    }
  }
  if (!ctx.sqlScope) return;
  const text = sqlText(node);
  if (text) {
    unfilteredSelects(text).forEach((sql) => ctx.found.selects.push({
      rule: 'unbounded-select',
      key: `${ctx.file.rel}#${state.fn}#${sql}`,
      path: ctx.file.rel,
      line: node.loc.start.line,
      message: 'SELECT has neither WHERE nor LIMIT; add a condition or move it into the query layer',
    }));
  }
}

function visit(node, parent, state, ctx) {
  const next = FUNCTION_TYPES.has(node.type)
    ? { ...state, fn: functionName(node, parent) ?? state.fn, inTx: state.inTx || ctx.txFunctions.has(node) }
    : state;
  inspectNode(node, next, ctx);
  const loop = loopOf(node);
  const iterator = isMethodCall(node, ITERATION_METHODS) && FUNCTION_TYPES.has(node.arguments[0]?.type)
    ? node.arguments[0] : null;
  for (const child of children(node)) {
    if (child === iterator) {
      visit(child, node, { ...next, perItem: true }, ctx);
      continue;
    }
    if (!loop || child !== loop.body) {
      visit(child, node, next, ctx);
      continue;
    }
    const loops = [...next.loops, { vars: loop.vars }];
    if (loops.length >= MAX_LOOP_DEPTH) checkDeepLoop(node, child, next.loops, next, ctx);
    visit(child, node, { ...next, loops }, ctx);
  }
}

// ─── Summary ────────────────────────────────────────────────────────────────
function main() {
  const { root } = parseArgs(process.argv.slice(2));
  const rels = SCAN_DIRS.flatMap((dir) => collectCodeFiles(root, dir)).filter((rel) => !isTestPath(rel));
  const graph = buildImportGraph(root, rels, parseFiles(root, rels));
  const { parsed, parseFailures, modules, unresolvedStaticImports } = graph;
  const found = { deepLoops: [], loopQueries: [], selects: [] };
  const allow = collectAllowMarkers(parsed, 'perf-shape');
  const queryEffects = dbEffectsByExport(parsed);
  for (const file of parsed) {
    const sqlScope = SQL_DIRS.some((dir) => file.rel.startsWith(dir)) && !SQL_EXEMPT.has(file.rel);
    const ctx = {
      file, found, sqlScope, allow,
      stmtNames: statementNames(file.tree),
      queries: queryImports(file, queryEffects.byExport),
      txFunctions: transactionalFunctions(file.tree),
    };
    visit(file.tree, null, { loops: [], perItem: false, inTx: false, fn: '(top-level)' }, ctx);
  }
  const edges = new Set([...modules].flatMap(([source, mod]) => mod.refs.map(({ target }) => `${source} -> ${target}`)));
  const marks = allow.items();
  emit({
    guard: 'perf-shape',
    coverage: {
      planned: rels.length,
      scanned: parsed.length,
      modules: modules.size,
      edges: edges.size,
      db_read_exports: queryEffects.dbReadExports,
      db_write_exports: queryEffects.dbWriteExports,
    },
    parseFailures,
    unsupported: unresolvedStaticImports.map(({ source, specifier }) => ({
      path: source, message: `cannot resolve static import ${specifier}`,
    })),
    hard: [...dedupeKeys(found.deepLoops), ...marks.hard],
    advisory: marks.advisory,
    findings: [...dedupeKeys(found.loopQueries), ...dedupeKeys(found.selects)],
  });
}

main();
