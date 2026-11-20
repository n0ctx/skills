"""Public API surface of Python packages, one line per symbol, for the snapshot guard.

`guard.py pyapi src/mypkg` prints lines such as
  mypkg.client:Client
  mypkg.client:Client.get(self, url, *, timeout=30)
  mypkg.util:parse(text: str) -> dict
Public = not underscored, and listed in __all__ when the module defines a literal __all__.
Signatures include annotations and literal defaults, so changing a parameter shows up as one
line removed and one added: the snapshot guard treats the removal as a breaking change.
"""

from __future__ import annotations

import ast
import os
import sys


def _module_name(root: str, path: str) -> str:
    rel = os.path.relpath(path, os.path.dirname(root.rstrip('/')))
    parts = rel[:-3].split(os.sep)
    if parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts)


def _signature(fn) -> str:
    text = ast.unparse(fn.args)
    ret = f' -> {ast.unparse(fn.returns)}' if fn.returns else ''
    prefix = 'async ' if isinstance(fn, ast.AsyncFunctionDef) else ''
    return f'{prefix}({text}){ret}'


def _all_names(tree) -> set[str] | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__all__' for t in node.targets):
            try:
                return set(ast.literal_eval(node.value))
            except ValueError:
                return None
    return None


def surface(paths: list[str]) -> tuple[list[str], list[str]]:
    lines, errors = [], []
    for root in paths:
        files = [root] if root.endswith('.py') else sorted(
            os.path.join(d, f) for d, dirs, fs in os.walk(root) for f in fs
            if f.endswith('.py') and not any(p.startswith(('_', '.', 'test')) and p != '__init__.py'
                                             for p in os.path.relpath(os.path.join(d, f), root).split(os.sep)))
        for path in files:
            try:
                with open(path, encoding='utf-8') as fh:
                    tree = ast.parse(fh.read(), filename=path)
            except (SyntaxError, UnicodeDecodeError) as err:
                errors.append(f'{path}: {err}')
                continue
            module = _module_name(root, path)
            exported = _all_names(tree)

            def public(name):
                return name in exported if exported is not None else not name.startswith('_')
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and public(node.name):
                    lines.append(f'{module}:{node.name}{_signature(node)}')
                elif isinstance(node, ast.ClassDef) and public(node.name):
                    bases = ', '.join(ast.unparse(b) for b in node.bases)
                    lines.append(f'{module}:{node.name}({bases})' if bases else f'{module}:{node.name}')
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                                (not item.name.startswith('_') or item.name == '__init__'):
                            lines.append(f'{module}:{node.name}.{item.name}{_signature(item)}')
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for t in targets:
                        if isinstance(t, ast.Name) and public(t.id) and t.id != '__all__':
                            lines.append(f'{module}:{t.id}')
    return sorted(set(lines)), errors


def main(paths: list[str]) -> int:
    lines, errors = surface(paths)
    for e in errors:
        print(f'pyapi: cannot parse {e}', file=sys.stderr)
    if errors:
        return 1
    sys.stdout.write(''.join(f'{line}\n' for line in lines))
    return 0
