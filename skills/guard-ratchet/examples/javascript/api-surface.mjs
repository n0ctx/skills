#!/usr/bin/env node
/**
 * API-surface producer for the runner's API-snapshot guard: prints the public export surface of
 * the given entry modules, one line per item, sorted. The runner snapshots and diffs the lines.
 *
 * Re-exports inside the repository (`export * from`, `export { x } from`, and `export { x }` of an
 * imported binding) are followed with import-graph's resolution, so the surface is what a consumer
 * of the entry module sees. Lines always carry the entry's own path:
 *   <entry>#<name>(<params>)          function; params are names, `...rest`, `x=` for a default,
 *                                     `{a,b}` / `[a,b]` for destructuring
 *   <entry>#<Name> class              class, plus one line per public member:
 *   <entry>#<Name>.<method>(<params>) `static ` / `get ` / `set ` prefix the method name; private
 *                                     (#x) members and class fields are not part of the surface
 *   <entry>#<name> const              anything else
 *
 * The surface fails closed: a file that cannot be parsed, an entry that does not exist, a re-export
 * that cannot be followed (unresolved path, external package, name the target does not export)
 * prints a message to stderr and exits 1, instead of printing a smaller surface. CommonJS
 * `module.exports` is not understood.
 *
 * Usage:
 *   node api-surface.mjs [--root <dir>] <entry.js>...
 *
 * Exit codes: 0 printed / 1 cannot produce a trustworthy surface / 2 usage error.
 */

import path from 'node:path';
import { collectCodeFiles, parseArgs, parseFiles, patternNames, usageError } from './guard-common.mjs';
import { resolveSpecifier } from './import-graph.mjs';

class SurfaceError extends Error {}

const FUNCTION_TYPES = new Set(['FunctionDeclaration', 'FunctionExpression', 'ArrowFunctionExpression']);

// ─── Parameter rendering ────────────────────────────────────────────────────
const sourceOf = (file, node) => file.text.slice(node.range[0], node.range[1]);

function propertyName(file, prop) {
  if (prop.computed) return `[${sourceOf(file, prop.key)}]`;
  return prop.key.name ?? String(prop.key.value);
}

function pattern(file, node) {
  switch (node.type) {
    case 'Identifier': return node.name;
    case 'AssignmentPattern': return `${pattern(file, node.left)}=`;
    case 'RestElement': return `...${pattern(file, node.argument)}`;
    case 'ArrayPattern': return `[${node.elements.map((e) => (e ? pattern(file, e) : '')).join(',')}]`;
    case 'ObjectPattern': return `{${node.properties.map((p) => objectMember(file, p)).join(',')}}`;
    default: throw new SurfaceError(`${file.rel}: unsupported parameter pattern ${node.type}`);
  }
}

// An object-pattern member renders as its property key: the local alias is not part of the API
function objectMember(file, prop) {
  if (prop.type === 'RestElement') return pattern(file, prop);
  const withDefault = prop.value.type === 'AssignmentPattern';
  const value = withDefault ? prop.value.left : prop.value;
  const key = propertyName(file, prop);
  return `${value.type === 'Identifier' ? key : `${key}:${pattern(file, value)}`}${withDefault ? '=' : ''}`;
}

const params = (file, fn) => fn.params.map((p) => pattern(file, p)).join(',');

// ─── Shapes ─────────────────────────────────────────────────────────────────
// A shape is { kind: 'function', params } | { kind: 'class', members: [string] } | { kind: 'const' }
function methodLabel(file, member) {
  const prefix = `${member.static ? 'static ' : ''}${member.kind === 'get' || member.kind === 'set' ? `${member.kind} ` : ''}`;
  return `${prefix}${propertyName(file, member)}(${params(file, member.value)})`;
}

function classShape(file, node) {
  const members = node.body.body
    .filter((m) => m.type === 'MethodDefinition' && m.key.type !== 'PrivateIdentifier')
    .map((m) => methodLabel(file, m));
  return { kind: 'class', members };
}

function valueShape(file, node) {
  if (FUNCTION_TYPES.has(node?.type)) return { kind: 'function', params: params(file, node) };
  if (node?.type === 'ClassExpression' || node?.type === 'ClassDeclaration') return classShape(file, node);
  return { kind: 'const' };
}

// Top-level declarations of a module: name -> shape
function declarations(file) {
  const out = new Map();
  for (const stmt of file.tree.body) {
    const decl = stmt.type === 'ExportNamedDeclaration' || stmt.type === 'ExportDefaultDeclaration'
      ? stmt.declaration : stmt;
    if (decl?.type === 'FunctionDeclaration' || decl?.type === 'ClassDeclaration') {
      if (decl.id) out.set(decl.id.name, valueShape(file, decl));
    } else if (decl?.type === 'VariableDeclaration') {
      for (const d of decl.declarations) {
        if (d.id.type === 'Identifier') out.set(d.id.name, valueShape(file, d.init));
        else patternNames(d.id).forEach((name) => out.set(name, { kind: 'const' }));
      }
    }
  }
  return out;
}

// ─── Module exports ─────────────────────────────────────────────────────────
class Surface {
  constructor(root) {
    this.root = root;
    this.fileSet = new Set(collectCodeFiles(root));
    this.files = new Map();
    this.exportCache = new Map();
  }

  load(rel) {
    if (!this.files.has(rel)) {
      const { parsed, parseFailures } = parseFiles(this.root, [rel]);
      if (parseFailures.length) throw new SurfaceError(`${rel}: cannot parse`);
      this.files.set(rel, { ...parsed[0], decls: declarations(parsed[0]) });
    }
    return this.files.get(rel);
  }

  target(rel, specifier) {
    const target = resolveSpecifier(this.fileSet, rel, specifier);
    if (!target) throw new SurfaceError(`${rel}: cannot resolve re-export from '${specifier}'`);
    return target;
  }

  // The shape of `name` exported by module `rel`
  exported(rel, name, trail) {
    const shape = this.exports(rel, trail).get(name);
    if (!shape) throw new SurfaceError(`${rel}: does not export '${name}'`);
    return shape;
  }

  // The shape of a top-level binding of `file`: a declaration, or an imported binding to follow
  binding(file, name, trail) {
    if (file.decls.has(name)) return file.decls.get(name);
    for (const stmt of file.tree.body) {
      if (stmt.type !== 'ImportDeclaration') continue;
      const spec = stmt.specifiers.find((s) => s.local.name === name);
      if (!spec) continue;
      if (spec.type === 'ImportNamespaceSpecifier') return { kind: 'const' };
      const imported = spec.type === 'ImportDefaultSpecifier' ? 'default' : spec.imported.name ?? spec.imported.value;
      return this.exported(this.target(file.rel, stmt.source.value), imported, trail);
    }
    throw new SurfaceError(`${file.rel}: cannot find the binding '${name}' it exports`);
  }

  // Map name -> shape of everything module `rel` exports. Explicit exports win over `export *`.
  exports(rel, trail = []) {
    if (this.exportCache.has(rel)) return this.exportCache.get(rel);
    if (trail.includes(rel)) throw new SurfaceError(`${rel}: re-export cycle ${[...trail, rel].join(' -> ')}`);
    const file = this.load(rel);
    const next = [...trail, rel];
    const named = new Map();
    const stars = [];
    for (const stmt of file.tree.body) {
      if (stmt.type === 'ExportNamedDeclaration') this.addNamed(file, stmt, named, next);
      else if (stmt.type === 'ExportDefaultDeclaration') {
        const { declaration } = stmt;
        const local = declaration.type === 'Identifier' ? this.binding(file, declaration.name, next) : null;
        named.set('default', local ?? valueShape(file, declaration));
      } else if (stmt.type === 'ExportAllDeclaration') {
        const target = this.target(rel, stmt.source.value);
        if (stmt.exported) named.set(stmt.exported.name ?? stmt.exported.value, { kind: 'const' });
        else stars.push(target);
      }
    }
    for (const target of stars) {
      for (const [name, shape] of this.exports(target, next)) {
        if (name !== 'default' && !named.has(name)) named.set(name, shape);
      }
    }
    this.exportCache.set(rel, named);
    return named;
  }

  addNamed(file, stmt, named, trail) {
    if (stmt.declaration) {
      const { declaration } = stmt;
      const names = declaration.type === 'VariableDeclaration'
        ? declaration.declarations.flatMap((d) => patternNames(d.id)) : [declaration.id.name];
      names.forEach((name) => named.set(name, file.decls.get(name) ?? { kind: 'const' }));
      return;
    }
    const target = stmt.source ? this.target(file.rel, stmt.source.value) : null;
    for (const spec of stmt.specifiers) {
      const local = spec.local.name ?? spec.local.value;
      const exported = spec.exported.name ?? spec.exported.value;
      named.set(exported, target ? this.exported(target, local, trail) : this.binding(file, local, trail));
    }
  }
}

// ─── Output ─────────────────────────────────────────────────────────────────
function lines(entry, exports) {
  const out = [];
  for (const [name, shape] of exports) {
    if (shape.kind === 'function') out.push(`${entry}#${name}(${shape.params})`);
    else if (shape.kind === 'class') {
      out.push(`${entry}#${name} class`, ...shape.members.map((m) => `${entry}#${name}.${m}`));
    } else out.push(`${entry}#${name} const`);
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2), { paths: true });
  if (!args.paths.length) usageError('no entry module given: node api-surface.mjs [--root <dir>] <entry.js>...');
  const surface = new Surface(args.root);
  const out = new Set();
  try {
    for (const given of args.paths) {
      const entry = path.relative(args.root, path.resolve(args.root, given)).split(path.sep).join('/');
      if (!surface.fileSet.has(entry)) throw new SurfaceError(`${given}: not a scanned source file under ${args.root}`);
      lines(entry, surface.exports(entry)).forEach((line) => out.add(line));
    }
  } catch (err) {
    if (!(err instanceof SurfaceError)) throw err;
    console.error(`api-surface: ${err.message}`);
    process.exit(1);
  }
  process.stdout.write([...out].sort().map((line) => `${line}\n`).join(''));
}

main();
