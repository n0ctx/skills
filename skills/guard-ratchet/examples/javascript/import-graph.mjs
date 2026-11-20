/**
 * In-repository module reference graph, used by check-dead-code / check-cycles / check-architecture
 * and api-surface.
 *
 * Reference sources: the string literals of import / export from, require('...') and import('...')
 * (including React.lazy), plus the test helper freshImport('repo-root-relative path'). Relative paths
 * resolve to actual files (.js/.jsx/.mjs/.cjs appended, directories get index). When the argument of
 * import() is an expression, only string literals in it that look like repo-root-relative paths are
 * recognised (for example import(pathToFileURL(path.resolve(ROOT, 'backend/x.js')).href)); for
 * freshImport(suite.path), which takes its path from an object property, every `path: 'repo path'`
 * property value in the same file is recognised. Nothing else is guessed.
 *
 * For a module object loaded by import() / freshImport, usage decides which exports are used:
 *   const { a, b } = await freshImport('x')   -> a, b
 *   const mod = await import('x'); mod.a      -> a
 *   mod['a']                                  -> a
 *   mod[suite.createName]                     -> the string values of every `createName: '...'` property in the file
 * When the module object is passed to a function, spread, or indexed with a key that has no matching
 * property value, every export counts as used.
 * A bare package specifier is an external dependency; if the repository uses path aliases, add their
 * resolution per the repository's conventions before deploying.
 */

import path from 'node:path';
import { CODE_SUFFIXES, parseFiles, patternNames, stringValue, walk } from './guard-common.mjs';

export const ALL = '*';
// Functions in backend/tests/helpers/test-env.js that load modules dynamically by repo-root-relative path
const ROOT_IMPORTERS = new Set(['freshImport', 'freshImportUncached']);

export function resolveFile(fileSet, base) {
  const clean = path.posix.normalize(base.replace(/[?#].*$/, ''));
  if (clean.startsWith('../')) return null;
  const suffixes = [...CODE_SUFFIXES];
  const candidates = [clean, ...suffixes.map((s) => clean + s), ...suffixes.map((s) => `${clean}/index${s}`)];
  return candidates.find((c) => fileSet.has(c)) ?? null;
}

const moduleName = (node) => node.name ?? node.value;

function declarationNames(decl) {
  if (decl.type === 'VariableDeclaration') return decl.declarations.flatMap((d) => patternNames(d.id));
  return decl.id ? [decl.id.name] : [];
}

function importNames(node) {
  return node.specifiers.map((s) => {
    if (s.type === 'ImportDefaultSpecifier') return 'default';
    if (s.type === 'ImportNamespaceSpecifier') return ALL;
    return moduleName(s.imported);
  });
}

const relative = (rel, spec) => (typeof spec === 'string' && spec.startsWith('.')
  ? path.posix.join(path.posix.dirname(rel), spec) : null);

// Resolve a relative specifier to a file in fileSet; null for a bare package or when nothing resolves
export function resolveSpecifier(fileSet, rel, spec) {
  const base = relative(rel, spec);
  return base && resolveFile(fileSet, base);
}

const CODE_PATH_RE = /^[\w.-]+(\/[\w.-]+)+\.(js|jsx|mjs|cjs)$/;

// When the import() argument is an expression: its string literals that look like repo-root-relative paths
function embeddedPaths(source) {
  return [...walk(source)].map(([n]) => stringValue(n)).filter((v) => v && CODE_PATH_RE.test(v));
}

function parentMap(tree) {
  const parents = new Map();
  for (const [node, parent] of walk(tree)) parents.set(node, parent);
  return parents;
}

// Values of `key: 'string'` properties in this file; null when there are none
function propertyStrings(tree, key) {
  const values = [];
  for (const [node] of walk(tree)) {
    if (node.type !== 'Property' || node.computed || moduleName(node.key) !== key) continue;
    const value = stringValue(node.value);
    if (value !== null) values.push(value);
  }
  return values.length ? values : null;
}

// Export names that the key in mod[key] can stand for; null when unrecognised
function computedNames(tree, key) {
  const literal = stringValue(key);
  if (literal !== null) return [literal];
  if (key.type === 'MemberExpression' && !key.computed) return propertyStrings(tree, key.property.name);
  return null;
}

function patternKeys(pattern, tree) {
  const names = [];
  for (const prop of pattern.properties) {
    if (prop.type === 'RestElement') return [ALL];
    const name = prop.computed ? computedNames(tree, prop.key) : [moduleName(prop.key)];
    if (!name) return [ALL];
    names.push(...name);
  }
  return names;
}

// Export names taken from the module object called `name` in this file
function memberNames(tree, parents, name) {
  const names = new Set();
  for (const [node, parent] of walk(tree)) {
    if (node.type !== 'Identifier' || node.name !== name) continue;
    if (parent?.type === 'MemberExpression' && parent.object === node) {
      const picked = parent.computed ? computedNames(tree, parent.property) : [parent.property.name];
      if (!picked) return [ALL];
      picked.forEach((n) => names.add(n));
    } else if (parent?.type === 'VariableDeclarator' && parent.init === node && parent.id.type === 'ObjectPattern') {
      patternKeys(parent.id, tree).forEach((n) => names.add(n));
    } else if ((parent?.type === 'VariableDeclarator' && parent.id === node)
        || (parent?.type === 'AssignmentExpression' && parent.left === node)
        || (parent?.type === 'MemberExpression' && parent.property === node && !parent.computed)
        || (parent?.type === 'Property' && parent.key === node && !parent.computed && !parent.shorthand)) {
      continue;
    } else {
      return [ALL];
    }
  }
  return [...names];
}

// How a dynamic-load result is captured decides which exports are used
function loadedNames(tree, parents, loadNode) {
  let node = loadNode;
  let parent = parents.get(node);
  while (parent?.type === 'AwaitExpression') {
    node = parent;
    parent = parents.get(node);
  }
  if (parent?.type === 'VariableDeclarator' && parent.init === node) {
    if (parent.id.type === 'ObjectPattern') return patternKeys(parent.id, tree);
    if (parent.id.type === 'Identifier') return memberNames(tree, parents, parent.id.name);
  }
  if (parent?.type === 'AssignmentExpression' && parent.right === node && parent.left.type === 'Identifier') {
    return memberNames(tree, parents, parent.left.name);
  }
  return [ALL];
}

// freshImport argument: a literal path, or a repo path taken by property name such as suite.path
function rootImportTargets(tree, arg) {
  const literal = stringValue(arg);
  if (literal !== null) return [literal];
  if (arg?.type === 'MemberExpression' && !arg.computed) {
    return (propertyStrings(tree, arg.property.name) ?? []).filter((v) => CODE_PATH_RE.test(v));
  }
  return [];
}

// Returns { refs: [{ base, names, lazy, specifier, line }], exports: [{ name, line }] }; base is the
// repo-relative path to resolve, lazy means the module loads only when execution gets there
// (import() / freshImport) and so is not a load-time cycle
function moduleShape(rel, tree) {
  const refs = [];
  const exports = [];
  const ref = (node, base, names, lazy = false, specifier = base) => refs.push({
    base, names, lazy, specifier, line: node.loc.start.line,
  });
  const exported = (node, names) => names.forEach((name) => exports.push({ name, line: node.loc.start.line }));
  const parents = parentMap(tree);
  for (const [node] of walk(tree)) {
    if (node.type === 'ImportDeclaration') {
      const specifier = node.source.value;
      ref(node, relative(rel, specifier), importNames(node), false, specifier);
    }
    else if (node.type === 'ExportNamedDeclaration') {
      if (node.declaration) exported(node, declarationNames(node.declaration));
      exported(node, node.specifiers.map((s) => moduleName(s.exported)));
      if (node.source) {
        const specifier = node.source.value;
        ref(node, relative(rel, specifier), node.specifiers.map((s) => moduleName(s.local)), false, specifier);
      }
    } else if (node.type === 'ExportAllDeclaration') {
      const specifier = node.source.value;
      ref(node, relative(rel, specifier), [ALL], false, specifier);
      if (node.exported) exported(node, [moduleName(node.exported)]);
    } else if (node.type === 'ExportDefaultDeclaration') exported(node, ['default']);
    else if (node.type === 'ImportExpression') {
      const literal = stringValue(node.source);
      const names = loadedNames(tree, parents, node);
      if (literal !== null) ref(node, relative(rel, literal), names, true, literal);
      else embeddedPaths(node.source).forEach((base) => ref(node, base, names, true, base));
    } else if (node.type === 'CallExpression' && node.callee.type === 'Identifier' && node.arguments.length === 1) {
      if (node.callee.name === 'require') {
        const specifier = stringValue(node.arguments[0]);
        ref(node, relative(rel, specifier), [ALL], false, specifier);
      }
      else if (ROOT_IMPORTERS.has(node.callee.name)) {
        const names = loadedNames(tree, parents, node);
        rootImportTargets(tree, node.arguments[0]).forEach((base) => ref(node, base, names, true, base));
      }
    }
  }
  return { refs, exports };
}

// Returns the resolved modules and unresolvedStaticImports, which lists deterministic in-repo
// references that cannot be resolved. scan may carry the parseFiles result for the same files so an
// existing detector can reuse its parse.
export function buildImportGraph(root, rels, scan = null) {
  const fileSet = new Set(rels);
  const { parsed, parseFailures } = scan ?? parseFiles(root, rels);
  const modules = new Map();
  const unresolvedStaticImports = [];
  for (const { rel, tree } of parsed) {
    const { refs, exports } = moduleShape(rel, tree);
    const resolved = [];
    for (const { base, names, lazy, specifier, line } of refs) {
      const target = base && resolveFile(fileSet, base);
      if (!target) {
        if (base !== null) unresolvedStaticImports.push({ source: rel, target: base, specifier, lazy });
        continue;
      }
      if (target !== rel) resolved.push({ target, names, lazy, line });
    }
    const seen = new Set();
    modules.set(rel, { exports: exports.filter((e) => !seen.has(e.name) && seen.add(e.name)), refs: resolved });
  }
  unresolvedStaticImports.sort((a, b) => {
    const left = `${a.source}\0${a.target}\0${a.specifier}`;
    const right = `${b.source}\0${b.target}\0${b.specifier}`;
    return left < right ? -1 : left > right ? 1 : 0;
  });
  return { fileSet, parsed, parseFailures, modules, unresolvedStaticImports };
}
