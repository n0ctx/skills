"""Built-in dependency guard: what changed in manifests and lockfiles, judged deterministically.

Blocking (hard):
  dep-source      dependency pulled from git, a URL or a local path instead of a registry
  dep-unpinned    version spec that accepts anything (*, latest, empty)
  dep-index       new package index / registry source (dependency-confusion vector)
  lock-registry   lockfile entry resolved from a host outside the allowed registries
  lockfile-stale  manifest dependencies changed but the sibling lockfile did not
  lockfile-removed
Advisory (evidence for review):
  dep-added, dep-alias, dep-open-range, install-script, lock-integrity-missing, not-analyzed

Known vulnerabilities are not checked here: that needs a vulnerability database, so it is the job
of osv-scanner (or the ecosystem's audit tool) configured as a separate guard.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse

from . import policy as pol
from .context import Context
from .model import Item, Scan

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

DEFAULT_REGISTRIES = ['registry.npmjs.org', 'registry.yarnpkg.com', 'pypi.org', 'files.pythonhosted.org',
                      'proxy.golang.org', 'crates.io', 'static.crates.io', 'index.crates.io', 'rubygems.org',
                      'repo.packagist.org', 'repo.maven.apache.org', 'repo1.maven.org', 'api.nuget.org']
NPM_SECTIONS = ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies')
LOCKS = {
    'package.json': ('package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lock', 'bun.lockb'),
    'pyproject.toml': ('poetry.lock', 'uv.lock', 'pdm.lock'),
    'Pipfile': ('Pipfile.lock',),
    'go.mod': ('go.sum',),
    'Cargo.toml': ('Cargo.lock',),
    'Gemfile': ('Gemfile.lock',),
    'composer.json': ('composer.lock',),
}
NOT_ANALYZED = ('pom.xml', 'build.gradle', 'build.gradle.kts', 'libs.versions.toml', 'Package.swift', 'pubspec.yaml',
                'mix.exs', 'Podfile', 'Directory.Packages.props')
GIT_OR_URL = re.compile(r'^(git\+|git:|github:|gitlab:|bitbucket:|https?:|file:|link:|ssh:)|^[\w.-]+/[\w.-]+(#.*)?$')
WILDCARD = {'*', 'latest', 'x', '', 'X', 'next'}


class Collector:
    def __init__(self, guard: dict):
        self.scan = Scan(guard['name'], tool={'name': 'guard-ratchet/deps'})
        self.registries = set(DEFAULT_REGISTRIES) | set(guard.get('registries') or [])

    def hard(self, rule: str, key: str, path: str, message: str) -> None:
        self.scan.hard.append(Item(rule, key, path=path, message=message, mode='hard'))

    def note(self, rule: str, key: str, path: str, message: str) -> None:
        if any(i.rule == rule and i.key == key for i in self.scan.advisory):
            return
        self.scan.advisory.append(Item(rule, key, path=path, message=message, mode='advisory'))

    def host_ok(self, url: str) -> bool:
        host = urllib.parse.urlparse(url).hostname or ''
        return any(host == r or host.endswith('.' + r) for r in self.registries)


def _changed_names(base: dict, cur: dict) -> tuple[dict, dict, set]:
    added = {k: v for k, v in cur.items() if k not in base}
    changed = {k: v for k, v in cur.items() if k in base and base[k] != v}
    removed = set(base) - set(cur)
    return added, changed, removed


def _spec_problems(out: Collector, path: str, name: str, spec: str, section: str) -> None:
    key = f'{path}#{name}'
    spec = str(spec).strip()
    if spec.startswith('npm:'):
        out.note('dep-alias', key, path, f'{name} is an alias for {spec[4:]}: confirm the real package is intended')
    elif spec.startswith('workspace:'):
        return
    elif GIT_OR_URL.match(spec):
        out.hard('dep-source', key, path, f'{name} comes from `{spec}`, not the registry: unreviewable and '
                                          f'mutable; publish it or vendor it')
    elif spec in WILDCARD:
        if section == 'peerDependencies':
            return  # "any version the host app has" is the normal peer contract
        out.hard('dep-unpinned', key, path, f'{name}@{spec or "(empty)"} accepts any version')
    elif section != 'peerDependencies' and re.match(r'^>=?\s*\d', spec) and '<' not in spec:
        out.note('dep-open-range', key, path, f'{name}@{spec} has no upper bound')


# ─── npm ─────────────────────────────────────────────────────────────────────
def _npm_manifest(out: Collector, path: str, base_text: str | None, text: str) -> bool:
    try:
        cur = json.loads(text)
        base = json.loads(base_text) if base_text else {}
    except json.JSONDecodeError as err:
        out.scan.integrity.append(f'{path} is not valid JSON: {err}')
        return False
    any_change = False
    for section in NPM_SECTIONS:
        added, changed, removed = _changed_names(base.get(section) or {}, cur.get(section) or {})
        any_change |= bool(added or changed or removed)
        for name, spec in sorted({**added, **changed}.items()):
            _spec_problems(out, path, name, spec, section)
        for name, spec in sorted(added.items()):
            out.note('dep-added', f'{path}#{name}', path, f'new {section} entry {name}@{spec}: '
                                                         f'check that it is needed, maintained and correctly named')
    # overrides (npm), resolutions (yarn) and pnpm.overrides replace versions anywhere in the tree.
    for section, base_map, cur_map in (
            ('overrides', _flat_overrides(base.get('overrides')), _flat_overrides(cur.get('overrides'))),
            ('resolutions', _flat_overrides(base.get('resolutions')), _flat_overrides(cur.get('resolutions'))),
            ('pnpm.overrides', _flat_overrides((base.get('pnpm') or {}).get('overrides')),
             _flat_overrides((cur.get('pnpm') or {}).get('overrides')))):
        added, changed, removed = _changed_names(base_map, cur_map)
        any_change |= bool(added or changed or removed)
        for name, spec in sorted({**added, **changed}.items()):
            if spec.startswith('$'):
                continue  # npm "$name": use the version declared in dependencies
            _spec_problems(out, path, name, spec, section)
            out.note('dep-override', f'{path}#{name}', path, f'{section} pins {name} to {spec} for the whole tree')
    return any_change


def _flat_overrides(value, prefix: str = '') -> dict[str, str]:
    out = {}
    for name, spec in (value or {}).items() if isinstance(value, dict) else ():
        key = f'{prefix}>{name}' if prefix else name
        if isinstance(spec, dict):
            out.update(_flat_overrides(spec, key))
        elif isinstance(spec, str):
            out[key.replace('>.', '') if name == '.' else key] = spec
    return out


def _npm_lock(out: Collector, path: str, base_text: str | None, text: str) -> None:
    try:
        cur = json.loads(text).get('packages') or {}
        base = (json.loads(base_text).get('packages') or {}) if base_text else {}
    except (json.JSONDecodeError, AttributeError) as err:
        out.scan.integrity.append(f'{path} is not a valid npm lockfile: {err}')
        return
    for pkg, meta in sorted(cur.items()):
        if not pkg or not isinstance(meta, dict) or base.get(pkg) == meta or meta.get('link'):
            continue
        name = pkg.split('node_modules/')[-1]
        resolved = meta.get('resolved') or ''
        key = f'{path}#{name}'
        if resolved and (not resolved.startswith(('http://', 'https://')) or not out.host_ok(resolved)):
            out.hard('lock-registry', key, path, f'{name} resolves to `{resolved}`, outside the allowed registries')
        elif resolved and not meta.get('integrity'):
            out.note('lock-integrity-missing', key, path, f'{name} has no integrity hash')
        if meta.get('hasInstallScript') and pkg not in base:
            out.note('install-script', key, path, f'new package {name} runs an install script')


def _text_lock(out: Collector, path: str, added: list[tuple[int, str]]) -> None:
    """yarn.lock / pnpm-lock.yaml: check hosts of newly added resolution URLs."""
    for _, line in added:
        match = re.search(r'(?:resolved|tarball):?\s+"?([^"\s,}]+)', line)
        if match and match.group(1).startswith(('http://', 'https://', 'git', 'file:')):
            url = match.group(1)
            if not url.startswith(('http://', 'https://')) or not out.host_ok(url):
                out.hard('lock-registry', f'{path}#{url}', path, f'lockfile resolves `{url}` outside the allowed registries')


# ─── Python ──────────────────────────────────────────────────────────────────
REQ_NAME = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9._-]*)')


def _in_repo_path(manifest: str, line: str) -> bool:
    match = re.match(r'^(?:(?:-e|--editable)\s+)?(\.{1,2}(?:/\S*)?|[\w.-]+/\S*)(?:\[[^\]]*\])?$', line)
    if not match or re.match(r'^[a-z+]+:', match.group(1)) \
            or re.search(r'\.(whl|zip|tar\.gz|tgz|tar\.bz2|egg)$', match.group(1), re.I):
        return False  # a committed archive is a binary nobody reviews
    target = os.path.normpath(os.path.join(os.path.dirname(manifest), match.group(1)))
    return target != '..' and not target.startswith('../') and not os.path.isabs(target)


def _requirements(out: Collector, path: str, base_text: str | None, text: str) -> bool:
    base_lines = {l.strip() for l in (base_text or '').splitlines()}
    lines = [l.strip() for l in text.splitlines()]
    pinned = sum(1 for l in lines if '==' in l)
    reqs = [l for l in lines if l and not l.startswith('#')]
    for line in reqs:
        if line in base_lines:
            continue
        line = line.split(' #')[0].strip()
        if re.match(r'^(-r|--requirement|-c|--constraint)\b', line):
            continue  # includes another requirements file, which is judged on its own when it changes
        if re.match(r'^(--extra-index-url|--index-url|-i\b|--trusted-host|-f\b|--find-links)', line):
            out.hard('dep-index', f'{path}#{line.split()[0]}', path, f'`{line}` adds a package source')
        elif _in_repo_path(path, line):
            # `-e .` / `./packages/x`: a package from this repository, reviewed with it.
            out.note('dep-local', f'{path}#{line[:60]}', path, f'`{line}` installs a package from this repository')
        elif line.startswith(('-e', '--editable')) or re.search(r'(^|\s|@\s*)(git\+|https?://|file:|\.{0,2}/)', line):
            out.hard('dep-source', f'{path}#{line[:60]}', path, f'`{line}` installs from outside the index')
        elif line.startswith('-'):
            continue
        else:
            name = REQ_NAME.match(line)
            name = name.group(1) if name else line
            out.note('dep-added', f'{path}#{name}', path, f'requirement `{line}` added or changed')
            if pinned * 2 > len(reqs) and '==' not in line and '===' not in line:
                out.note('dep-open-range', f'{path}#{name}', path, f'`{line}` is not pinned while the file pins with ==')
    return set(reqs) != {l for l in base_lines if l and not l.startswith('#')}


def _pep508(out: Collector, path: str, items, base_items) -> None:
    for spec in sorted(set(items) - set(base_items)):
        name = REQ_NAME.match(spec)
        name = name.group(1) if name else spec
        if re.search(r'@\s*(git\+|https?:|file:)', spec):
            out.hard('dep-source', f'{path}#{name}', path, f'`{spec}` is a direct reference, not a registry release')
        out.note('dep-added', f'{path}#{name}', path, f'dependency `{spec}` added or changed')


def _toml(text: str | None, out: Collector, path: str) -> dict:
    if not text:
        return {}
    if tomllib is None:
        if 'Python 3.11+ (tomllib) to analyze TOML manifests' not in out.scan.missing:
            out.scan.missing.append('Python 3.11+ (tomllib) to analyze TOML manifests')
        out.note('not-analyzed', path, path, f'{path} changed; parsing TOML manifests needs Python 3.11+ (tomllib). '
                                             f'Run the guards with a newer Python, or rely on osv-scanner and the '
                                             f'ecosystem lock check')
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        out.scan.integrity.append(f'{path} is not valid TOML: {err}')
        return {}


def _pyproject_deps(doc: dict) -> list[str]:
    project = doc.get('project') or {}
    items = list(project.get('dependencies') or [])
    for group in (project.get('optional-dependencies') or {}).values():
        items += group
    for group in (doc.get('dependency-groups') or {}).values():
        items += [g for g in group if isinstance(g, str)]
    return items


def _pyproject(out: Collector, path: str, base_text: str | None, text: str) -> bool:
    cur, base = _toml(text, out, path), _toml(base_text, out, path)
    _pep508(out, path, _pyproject_deps(cur), _pyproject_deps(base))
    poetry = ((cur.get('tool') or {}).get('poetry') or {})
    base_poetry = ((base.get('tool') or {}).get('poetry') or {})
    groups = [('dependencies', poetry.get('dependencies') or {}, base_poetry.get('dependencies') or {})]
    for gname, group in (poetry.get('group') or {}).items():
        groups.append((gname, group.get('dependencies') or {},
                       ((base_poetry.get('group') or {}).get(gname) or {}).get('dependencies') or {}))
    for _, deps_now, deps_base in groups:
        added, changed, _ = _changed_names(deps_base, deps_now)
        for name, spec in sorted({**added, **changed}.items()):
            if isinstance(spec, dict) and any(k in spec for k in ('git', 'url', 'path')):
                out.hard('dep-source', f'{path}#{name}', path, f'{name} comes from {spec}, not the index')
            elif spec in ('*', '') or (isinstance(spec, dict) and spec.get('version') == '*'):
                out.hard('dep-unpinned', f'{path}#{name}', path, f'{name} accepts any version')
            if name in added and name != 'python':
                out.note('dep-added', f'{path}#{name}', path, f'poetry dependency {name} added')
    uv = (cur.get('tool') or {}).get('uv') or {}
    base_uv = (base.get('tool') or {}).get('uv') or {}
    for name, src in sorted((uv.get('sources') or {}).items()):
        if (base_uv.get('sources') or {}).get(name) != src and isinstance(src, dict) \
                and any(k in src for k in ('git', 'url', 'path')) and not src.get('workspace'):
            out.hard('dep-source', f'{path}#{name}', path, f'{name} comes from {src}, not the index')
    for table, base_table in ((uv.get('index') or [], base_uv.get('index') or []),
                              (poetry.get('source') or [], base_poetry.get('source') or [])):
        for index in table:
            if index not in base_table:
                out.hard('dep-index', f"{path}#{index.get('name') or index.get('url')}", path,
                         f"new package index {index.get('url')}")
    return sorted(_pyproject_deps(cur)) != sorted(_pyproject_deps(base)) or poetry != base_poetry or uv != base_uv


# ─── Go / Rust / Ruby / PHP ──────────────────────────────────────────────────
def _gomod(out: Collector, path: str, base_text: str | None, text: str) -> bool:
    def parse(t):
        req, rep, block = set(), set(), None
        for line in (t or '').splitlines():
            line = line.split('//')[0].strip()
            if line.endswith('('):
                block = line.split()[0]
                continue
            if line == ')':
                block = None
                continue
            if line.startswith(('require ', 'replace ')):
                block_kind, line = line.split(None, 1)
                (req if block_kind == 'require' else rep).add(line.strip())
            elif block in ('require', 'replace') and line:
                (req if block == 'require' else rep).add(line)
        return req, rep
    req, rep = parse(text)
    base_req, base_rep = parse(base_text)
    for line in sorted(rep - base_rep):
        target = line.split('=>', 1)[-1].strip()
        if target.startswith(('.', '/')):
            out.hard('dep-source', f'{path}#{line.split()[0]}', path, f'replace to a local path `{line}`')
        else:
            out.note('dep-replace', f'{path}#{line.split()[0]}', path, f'module replaced: `{line}`')
    for line in sorted(req - base_req):
        out.note('dep-added', f'{path}#{line.split()[0]}', path, f'require `{line}` added or changed')
    return req != base_req or rep != base_rep


def _cargo_tables(doc: dict) -> dict:
    out = {}
    for section in ('dependencies', 'dev-dependencies', 'build-dependencies'):
        out.update({f'{section}.{k}': v for k, v in (doc.get(section) or {}).items()})
    for target, tdoc in (doc.get('target') or {}).items():
        for section in ('dependencies', 'dev-dependencies', 'build-dependencies'):
            out.update({f'{target}.{section}.{k}': v for k, v in (tdoc.get(section) or {}).items()})
    out.update({f'workspace.{k}': v for k, v in ((doc.get('workspace') or {}).get('dependencies') or {}).items()})
    # [patch.<registry>] and [replace] swap a registry crate for another source everywhere in the graph.
    for registry, table in (doc.get('patch') or {}).items():
        out.update({f'patch.{registry}.{k}': v for k, v in (table or {}).items()})
    out.update({f'replace.{k}': v for k, v in (doc.get('replace') or {}).items()})
    return out


def _cargo(out: Collector, path: str, base_text: str | None, text: str) -> bool:
    cur, base = _cargo_tables(_toml(text, out, path)), _cargo_tables(_toml(base_text, out, path))
    added, changed, removed = _changed_names(base, cur)
    for name, spec in sorted({**added, **changed}.items()):
        short = name.rsplit('.', 1)[-1]
        if isinstance(spec, dict) and 'git' in spec:
            out.hard('dep-source', f'{path}#{short}', path, f'{short} comes from git {spec["git"]}')
        version = spec if isinstance(spec, str) else (spec or {}).get('version') if isinstance(spec, dict) else None
        if version == '*':
            out.hard('dep-unpinned', f'{path}#{short}', path, f'{short} = "*" accepts any version')
        if name in added:
            out.note('dep-added', f'{path}#{short}', path, f'crate {short} added')
    return bool(added or changed or removed)


def _gemfile(out: Collector, path: str, added: list[tuple[int, str]]) -> bool:
    """Gemfile is Ruby code; only added lines are checked."""
    changed = False
    for _, line in added:
        stripped = line.strip()
        if re.match(r'^source\s+["\']', stripped) and 'rubygems.org' not in stripped:
            out.hard('dep-index', f'{path}#{stripped[:60]}', path, f'new gem source `{stripped}`')
        elif re.match(r'^gem\s', stripped):
            changed = True
            name = re.findall(r'["\']([^"\']+)["\']', stripped)
            name = name[0] if name else stripped
            if re.search(r'\b(git|github|gist|bitbucket|path):|:(git|github|gist|bitbucket|path)\s*=>', stripped):
                out.hard('dep-source', f'{path}#{name}', path, f'gem {name} comes from outside rubygems')
            out.note('dep-added', f'{path}#{name}', path, f'gem line `{stripped}` added or changed')
    return changed


PLATFORM_PACKAGE = re.compile(r'^(php(-[\w-]+)?|hhvm|ext-.+|lib-.+|composer(-plugin|-runtime)?-api)$')


def _composer(out: Collector, path: str, base_text: str | None, text: str) -> bool:
    try:
        cur = json.loads(text)
        base = json.loads(base_text) if base_text else {}
    except json.JSONDecodeError as err:
        out.scan.integrity.append(f'{path} is not valid JSON: {err}')
        return False
    changed_any = False
    for section in ('require', 'require-dev'):
        added, changed, removed = _changed_names(base.get(section) or {}, cur.get(section) or {})
        changed_any |= bool(added or changed or removed)
        for name, spec in sorted({**added, **changed}.items()):
            if spec in ('*', '', 'dev-master', 'dev-main') and not PLATFORM_PACKAGE.match(name):
                out.hard('dep-unpinned', f'{path}#{name}', path, f'{name}:{spec} accepts any version')
            if name in added:
                out.note('dep-added', f'{path}#{name}', path, f'package {name}:{spec} added')
    if cur.get('repositories') != base.get('repositories'):
        out.hard('dep-index', f'{path}#repositories', path, 'composer repositories added or changed')
    return changed_any


# ─── entry point ─────────────────────────────────────────────────────────────
def check(ctx: Context, guard: dict) -> Scan:
    out = Collector(guard)
    analyzed = 0
    changed_manifests = []
    for path, change in sorted(ctx.changes.files.items()):
        name = os.path.basename(path)
        if pol.excluded(ctx.policy, path):
            continue
        if change.status == 'D':
            sibling = next((m for m, locks in LOCKS.items() if name in locks), None)
            if sibling and os.path.exists(os.path.join(ctx.root, os.path.dirname(path), sibling)):
                out.hard('lockfile-removed', path, path, f'{name} deleted while {sibling} remains: installs stop being reproducible')
            continue
        text = ctx.read(path)
        if text is None:
            continue
        base_text = ctx.base_text(change.old_path or path) if change.status != 'A' else None
        deps_changed = None
        if name == 'package.json':
            deps_changed = _npm_manifest(out, path, base_text, text)
        elif name in ('package-lock.json', 'npm-shrinkwrap.json'):
            _npm_lock(out, path, base_text, text)
        elif name in ('yarn.lock', 'pnpm-lock.yaml'):
            _text_lock(out, path, change.added)
        elif re.match(r'^(requirements|constraints).*\.txt$', name) or path.startswith('requirements/') and name.endswith('.txt'):
            deps_changed = _requirements(out, path, base_text, text)
        elif name == 'pyproject.toml':
            deps_changed = _pyproject(out, path, base_text, text)
        elif name == 'go.mod':
            deps_changed = _gomod(out, path, base_text, text)
        elif name == 'Cargo.toml':
            deps_changed = _cargo(out, path, base_text, text)
        elif name == 'Gemfile':
            deps_changed = _gemfile(out, path, change.added)
        elif name == 'composer.json':
            deps_changed = _composer(out, path, base_text, text)
        elif name in NOT_ANALYZED or name.endswith('.csproj'):
            out.note('not-analyzed', path, path, f'{name} changed; the built-in deps guard does not parse it. '
                                                 f'Rely on osv-scanner and the ecosystem lock check for it')
            continue
        else:
            continue
        analyzed += 1
        if deps_changed and name in LOCKS:
            changed_manifests.append(path)
    for path in changed_manifests:
        folder = os.path.dirname(path)
        for lock in LOCKS[os.path.basename(path)]:
            lock_path = f'{folder}/{lock}' if folder else lock
            if os.path.exists(os.path.join(ctx.root, lock_path)) and lock_path not in ctx.changes.files:
                out.hard('lockfile-stale', lock_path, path,
                         f'{path} dependencies changed but {lock_path} did not; regenerate the lockfile')
    out.scan.coverage = {'scanned': analyzed, 'unit': 'manifests and lockfiles changed'}
    return out.scan
