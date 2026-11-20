"""Built-in guards that need no external tool. All are language-agnostic.

Diff guards (judge only what changed against base; no baseline):
  secrets       high-confidence credentials in added lines, committed secret files
  test-changes  deleted tests, weakened assertions, rewritten expectations, untested changes
  deps          (deps.py) dependency sources, version pins, lockfile sync, registries
  migrations    edits to already-merged migrations, destructive operations in new ones
  diff-coverage (coverage.py) coverage of changed lines
  mutation      (coverage.py) mutation score of changed lines
  generated     generated files that differ from what the generator produces
Scan guards (whole tree, baselined):
  suppressions  lint/type/coverage/security suppressions and skipped tests, per file
  size          non-blank lines per code file (metric file-size, judged by policy thresholds)
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re

from . import coverage, deps
from . import policy as pol
from .context import Context
from .model import Item, Scan

# ─── secrets ─────────────────────────────────────────────────────────────────
SECRET_PATTERNS = [
    ('private-key', re.compile(r'-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY(?: BLOCK)?-----')),
    ('aws-access-key-id', re.compile(r'\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b')),
    ('github-token', re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b')),
    ('github-fine-grained-token', re.compile(r'\bgithub_pat_[A-Za-z0-9_]{50,}\b')),
    ('gitlab-token', re.compile(r'\bglpat-[A-Za-z0-9_-]{20,}\b')),
    ('slack-token', re.compile(r'\bxox[abprs]-[A-Za-z0-9-]{10,}\b')),
    ('slack-webhook', re.compile(r'https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]{20,}')),
    ('stripe-live-key', re.compile(r'\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b')),
    ('google-api-key', re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b')),
    ('openai-key', re.compile(r'\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{16,}T3BlbkFJ[A-Za-z0-9_-]{16,}')),
    ('anthropic-key', re.compile(r'\bsk-ant-(?:api|admin)\d{2}-[A-Za-z0-9_-]{60,}')),
    ('npm-token', re.compile(r'\bnpm_[A-Za-z0-9]{36}\b')),
    ('pypi-token', re.compile(r'\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}')),
    ('sendgrid-key', re.compile(r'\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b')),
]
# Lower confidence: reported as advisory evidence, never blocking.
SECRET_HINTS = [
    ('url-credentials', re.compile(r'\b[a-z][a-z0-9+.-]*://[^\s:/@"\'<>]+:([^\s:/@"\'<>]{6,})@[^\s/"\'<>]+')),
]
PLACEHOLDER = re.compile(r'example|xxxx|\*\*\*\*|placeholder|dummy|changeme|your[_-]?(?:key|token)|<[^>]+>|\$\{', re.IGNORECASE)
SECRET_FILES = ['.env', '.env.*', '*.pem', '*.key', 'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519', '*.p12', '*.pfx',
                '*.jks', '*.keystore', '*.kdbx', 'credentials', '.pypirc', '.netrc', '.git-credentials']
SECRET_FILE_OK = re.compile(r'\.(example|sample|template|dist|defaults?|tmpl|tpl)$|\.pub$', re.IGNORECASE)


def _mask(value: str) -> str:
    return value[:4] + '…' + f'({len(value)} chars)'


def _secret_name(rel: str) -> bool:
    name = os.path.basename(rel)
    return not SECRET_FILE_OK.search(name) and any(fnmatch.fnmatchcase(name, p) for p in SECRET_FILES)


def _secret_file(ctx: Context, rel: str) -> bool:
    if not _secret_name(rel):
        return False
    name = os.path.basename(rel)
    if name.endswith(('.pem', '.key')):
        text = ctx.read(rel) or ''
        return 'PRIVATE KEY' in text
    if name == 'credentials':
        return '/.aws/' in f'/{rel}' or 'aws_secret_access_key' in (ctx.read(rel) or '')
    return True


def secrets(ctx: Context, guard: dict) -> Scan:
    scan = Scan(guard['name'], tool={'name': 'guard-ratchet/secrets'})
    changed = [c for p, c in sorted(ctx.changes.files.items()) if c.status in ('A', 'M', 'R')
               and not pol.excluded(ctx.policy, p)]
    for change in changed:
        # A rename counts as adding: `git mv .env.example .env` commits a real .env.
        fresh = change.status == 'A' or (change.status == 'R' and not _secret_name(change.old_path or ''))
        if fresh and _secret_file(ctx, change.path):
            scan.hard.append(Item('secret-file', change.path, path=change.path,
                                  message='file type that normally holds credentials is committed; '
                                          'keep it out of git (and rotate what it contains)', mode='hard'))
        for lineno, text in change.added:
            for name, regex in SECRET_PATTERNS:
                for match in regex.finditer(text):
                    value = match.group(0)
                    if PLACEHOLDER.search(value):
                        continue
                    digest = hashlib.sha256(value.encode()).hexdigest()[:12]
                    scan.hard.append(Item(name, f'{change.path}#{name}#{digest}', path=change.path, line=lineno,
                                          message=f'{name} {_mask(value)} added; remove it and rotate the credential',
                                          mode='hard'))
            for name, regex in SECRET_HINTS:
                match = regex.search(text)
                if match and not PLACEHOLDER.search(match.group(0)) and 'localhost' not in match.group(0) \
                        and '127.0.0.1' not in match.group(0):
                    scan.advisory.append(Item(name, f'{change.path}#{name}', path=change.path, line=lineno,
                                              message='URL with an embedded password added', mode='advisory'))
    scan.coverage = {'scanned': len(changed), 'unit': 'changed files'}
    return scan


# ─── suppressions ────────────────────────────────────────────────────────────
SUPPRESSIONS = {
    'suppress-lint': r'eslint-disable|stylelint-disable|biome-ignore|oxlint-disable|deno-lint-ignore|'
                     r'(?i:#\s*(?:(?:ruff|flake8)\s*:\s*)?noqa\b)|pylint:\s*(?:disable|skip-file)|rubocop:todo|HLint:\s*ignore|'
                     r'tslint:disable|#!?\[cfg_attr\([^\]]*\ballow\(|'
                     r'//\s*ignore(?:_for_file)?:|#!?\[expect\(|\[SuppressMessage\(|@nowarn\b|scalafix:off|'
                     r'//\s*nolint\b|lint:ignore|#!?\[allow\(|@SuppressWarnings\b|@Suppress\(|swiftlint:disable|'
                     r'rubocop:disable|#pragma\s+warning\s+disable|\bNOLINT(?:NEXTLINE|BEGIN)?\b|phpcs:ignore|'
                     r'@phpstan-ignore|\bnoinspection\b|CHECKSTYLE:OFF|shellcheck\s+disable|credo:disable',
    'suppress-type': r'@ts-ignore|@ts-nocheck|@ts-expect-error|#\s*type:\s*ignore|#\s*pyright:\s*ignore|'
                     r'#\s*mypy:\s*(?:ignore-errors|disable-error-code)|#\s*pyright:\s*(?:basic|report\w+\s*=\s*false)|'
                     r'#\s*pyre-(?:ignore|fixme)\b|#\s*pytype:\s*disable|'
                     r'@psalm-suppress|\$FlowFixMe|\$FlowIgnore|@SuppressLint\b',
    'suppress-coverage': r'istanbul\s+ignore|c8\s+ignore|v8\s+ignore|pragma:\s*no\s*(?:cover|branch)|'
                         r'#\[coverage\(off\)\]|@codeCoverageIgnore|LCOV_EXCL|ExcludeFromCodeCoverage|:nocov:',
    'suppress-security': r'\bnosec\b|\bnosem(?:grep)?\b|gitleaks:allow|\bNOSONAR\b|lgtm\[|codeql\[|trivy:ignore|'
                         r'checkov:skip|tfsec:ignore|bandit:\s*skip|zizmor:\s*ignore',
    'guard-allow': r'guard-allow\(',
}
TEST_SUPPRESSIONS = {
    'test-skip': r'\b(?:it|test|describe|context|suite|specify)\.skip\b|\b(?:xit|xtest|xdescribe|xcontext|xspecify)\s*\(|'
                 r'@pytest\.mark\.(?:skip|skipif|xfail)\b|\bpytest\.(?:skip|xfail)\s*\(|'
                 r'@unittest\.(?:skip|skipIf|skipUnless|expectedFailure)\b|\bself\.skipTest\s*\(|'
                 r'\bt\.Skip(?:Now|f)?\s*\(|#\[ignore\b|@Disabled\b|@Ignore\b|\[Ignore\b|\bSkip\s*=\s*"|'
                 r'\b(?:test|it)\.(?:fixme|failing)\b|\bXCTSkip|\bmarkTestSkipped\b|\bskip\s*\(\s*["\']',
    'test-focus': r'\b(?:it|test|describe|context|suite|specify)\.only\b|\b(?:fit|fdescribe|fcontext)\s*\(|'
                  r'\bonly:\s*true\b|\bfocus:\s*true\b|\bF(?:It|Describe|Context)\(',
}
_COMPILED = {k: re.compile(v) for k, v in {**SUPPRESSIONS, **TEST_SUPPRESSIONS}.items()}


def suppressions(ctx: Context, guard: dict) -> Scan:
    """Inline suppressions are the cheapest way to make a failing check pass. Counting them per file
    and ratcheting the count turns every new one into an explicit, reviewable decision."""
    scan = Scan(guard['name'], tool={'name': 'guard-ratchet/suppressions'})
    files = ctx.code_files()
    for rel in files:
        text = ctx.read(rel)
        if text is None:
            continue
        is_test = ctx.kind(rel) == 'test'
        for family, regex in _COMPILED.items():
            if family in TEST_SUPPRESSIONS and not is_test:
                continue
            count = sum(1 for _ in regex.finditer(text))
            if not count:
                continue
            if family == 'test-focus':
                scan.hard.append(Item(family, rel, count, path=rel, mode='hard',
                                      message=f'{count} focused test marker(s): the rest of the suite silently stops running'))
            else:
                scan.findings.append(Item(family, rel, count, path=rel, mode=guard.get('mode', 'ratchet')))
    scan.coverage = {'scanned': len(files), 'unit': 'files'}
    return scan


# ─── size ────────────────────────────────────────────────────────────────────
def size(ctx: Context, guard: dict) -> Scan:
    scan = Scan(guard['name'], tool={'name': 'guard-ratchet/size'})
    files = ctx.code_files()
    for rel in files:
        text = ctx.read(rel)
        if text is None:
            continue
        lines = sum(1 for line in text.splitlines() if line.strip())
        scan.metrics.append({'metric': 'file-size', 'key': rel, 'path': rel, 'value': lines})
    scan.coverage = {'scanned': len(files), 'unit': 'files'}
    return scan


# ─── test changes ────────────────────────────────────────────────────────────
ASSERTION = re.compile(r'\bassert\w*\b|\bexpect\s*\(|\.should\b|\bshould\.|\bt\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\b|'
                       r'\brequire\.\w+\(|\bXCTAssert\w*|\bassert_(?:eq|ne)!|\bassert!|\bverify\s*\(|\bAssert\.\w+|'
                       r'\bassertThat\b|\bmust\.\w+|\bt\.assert\w*|\bshould_|\bexpect_that\b|\brefute\w*\b')
LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`[^`]*`|\b\d+(?:\.\d+)?\b|\b(?:true|false|True|False|nil|None|null)\b')


def _shape(line: str) -> str:
    return LITERAL.sub('<lit>', line.strip())


def test_change_signals(ctx: Context) -> dict:
    """Evidence about how tests changed. Shared with the risk classifier, which raises the tier
    when assertions were weakened or expectations rewritten."""
    out = {'deleted': [], 'moved_out': {}, 'reduced': [], 'rewritten': [], 'untested': []}
    source_changed = 0
    tests_touched = False
    for path, change in sorted(ctx.changes.files.items()):
        old = change.old_path if change.status == 'R' else None
        if old and pol.is_code(old, ctx.policy) and not pol.excluded(ctx.policy, old) and ctx.base_kind(old) == 'test' \
                and ctx.kind(path) != 'test':
            # Moving a test out of the test paths takes it out of the test run as surely as deleting it.
            tests_touched = True
            out['deleted'].append(old)
            out['moved_out'][old] = path
            continue
        if not pol.is_code(path, ctx.policy) or pol.excluded(ctx.policy, path):
            continue
        kind = ctx.base_kind(path) if change.status == 'D' else ctx.kind(path)
        if kind == 'test':
            tests_touched = True
            if change.status == 'D':
                out['deleted'].append(path)
                continue
            removed = [(n, t) for n, t in change.removed if ASSERTION.search(t)]
            added = [(n, t) for n, t in change.added if ASSERTION.search(t)]
            if len(removed) > len(added):
                out['reduced'].append((path, len(removed), len(added), removed[:3]))
            added_shapes = {}
            for n, t in added:
                added_shapes.setdefault(_shape(t), []).append((n, t))
            for n, t in removed:
                twin = next((a for a in added_shapes.get(_shape(t), []) if a[1].strip() != t.strip()), None)
                if twin:
                    out['rewritten'].append((path, twin[0], t.strip(), twin[1].strip()))
        elif kind in ('logic', 'ui', 'model') and change.status != 'D':
            source_changed += len(change.added)
    out['source_lines'] = source_changed
    out['tests_touched'] = tests_touched
    return out


def test_changes(ctx: Context, guard: dict) -> Scan:
    scan = Scan(guard['name'], tool={'name': 'guard-ratchet/test-changes'})
    signals = test_change_signals(ctx)
    for path in signals['deleted']:
        target = signals['moved_out'].get(path)
        what = f'test file moved out of the test paths to {target}' if target else 'test file deleted'
        scan.hard.append(Item('test-file-deleted', path, path=target or path, mode='hard',
                              message=f'{what}; if the behavior it covered is gone too, '
                                      'record an exception with the reason'))
    for path, removed, added, sample in signals['reduced']:
        lines = '; '.join(f'-{n}: {t.strip()[:80]}' for n, t in sample)
        scan.advisory.append(Item('assertions-reduced', path, path=path, mode='advisory',
                                  message=f'{removed} assertion lines removed, {added} added ({lines})'))
    if signals['source_lines']:
        for path, line, old, new in signals['rewritten']:
            scan.advisory.append(Item('expectation-changed', path, path=path, line=line, mode='advisory',
                                      message=f'expected value changed alongside implementation changes: '
                                              f'`{old[:100]}` -> `{new[:100]}`; confirm the new expectation is '
                                              f'the requirement, not the new behavior'))
    default = pol.OPTION_DEFAULTS['test-changes']['min']['untested_lines']
    threshold = guard['min'].get('untested_lines', default) if isinstance(guard.get('min'), dict) else default
    if signals['source_lines'] >= threshold and not signals['tests_touched']:
        scan.advisory.append(Item('no-test-change', 'changeset', mode='advisory',
                                  message=f"{signals['source_lines']} source lines added without touching any test"))
    scan.coverage = {'scanned': len(ctx.changes.files), 'unit': 'changed files'}
    return scan


# ─── migrations ──────────────────────────────────────────────────────────────
DESTRUCTIVE = [
    ('drop-table', r'\bDROP\s+TABLE\b|\bop\.drop_table\b|\bdrop_table\b|\bmigrations\.DeleteModel\b|\bdropTable\b|'
                   r'\bSchema::drop'),
    ('drop-column', r'\bDROP\s+COLUMN\b|\bop\.drop_column\b|\bremove_column\b|\bmigrations\.RemoveField\b|'
                    r'\bdropColumn\b|\bremoveColumn\b'),
    ('truncate', r'\bTRUNCATE\b'),
    ('delete-all', r'\bDELETE\s+FROM\s+[\w."`]+\s*(?:;|$)'),
    ('rename', r'\bRENAME\s+(?:COLUMN|TO)\b|new_column_name\s*=|\brename_column\b|\bmigrations\.Rename(?:Field|Model)\b|'
               r'\brenameColumn\b|\brename_table\b'),
    ('type-change', r'\bALTER\s+COLUMN\b.*\bTYPE\b|\bMODIFY\s+COLUMN\b|\bchange_column\b|\bmigrations\.AlterField\b|'
                    r'\btype_\s*='),
    ('not-null-without-default', r'\bADD\s+(?:COLUMN\s+)?[\w"`]+\s+(?:(?!\bDEFAULT\b)[^,;])*\bNOT\s+NULL\b(?![^,;]*\bDEFAULT\b)|'
                                 r'\bSET\s+NOT\s+NULL\b'),
]
_DESTRUCTIVE = [(name, re.compile(rx, re.IGNORECASE)) for name, rx in DESTRUCTIVE]


def _is_migration(ctx: Context, path: str) -> bool:
    return 'migration' in pol.roles_of(ctx.policy, path) and not path.endswith(('.md', '.txt', '.rst')) \
        and os.path.basename(path) not in ('__init__.py', '.gitkeep')


def migrations(ctx: Context, guard: dict) -> Scan:
    """A migration that already reached the base branch may have run in some environment; editing it
    forks the schema history. Destructive operations cannot be judged automatically: reported as
    evidence for review (and the migration role already forces the strict tier)."""
    scan = Scan(guard['name'], tool={'name': 'guard-ratchet/migrations'})
    touched = 0
    for path, change in sorted(ctx.changes.files.items()):
        old = change.old_path if change.status == 'R' else path
        if pol.excluded(ctx.policy, path) and (not old or pol.excluded(ctx.policy, old)):
            continue
        if not (_is_migration(ctx, path) or (old and _is_migration(ctx, old))):
            continue
        touched += 1
        if change.status in ('M', 'D', 'R'):
            verb = {'M': 'edited', 'D': 'deleted', 'R': 'renamed'}[change.status]
            scan.hard.append(Item(f'migration-{verb}', old, path=path, mode='hard',
                                  message=f'migration already on the base branch was {verb}; add a new migration instead'))
        if change.status in ('A', 'M', 'R'):
            for lineno, text in change.added:
                for name, regex in _DESTRUCTIVE:
                    if regex.search(text):
                        scan.advisory.append(Item(f'destructive-{name}', f'{path}#{name}', path=path, line=lineno,
                                                  mode='advisory',
                                                  message=f'{name}: `{text.strip()[:120]}` — check data loss, locking '
                                                          f'and rollback before merging'))
    scan.coverage = {'scanned': touched, 'unit': 'migration files changed'}
    return scan


# ─── generated code ──────────────────────────────────────────────────────────
def _digests(ctx: Context, patterns) -> dict[str, str]:
    from .gitx import tracked_files
    out = {}
    for rel in tracked_files(ctx.root):
        if pol.any_match(rel, patterns):
            with open(os.path.join(ctx.root, rel), 'rb') as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return out


def generated(ctx: Context, guard: dict) -> Scan:
    """Run the generator and compare its outputs with what is committed. The regenerated files are
    left in place on purpose: they are the fix."""
    scan = Scan(guard['name'], tool={'name': 'guard-ratchet/generated'})
    outputs = guard.get('outputs') or []
    if not outputs:
        scan.integrity.append('generated guard needs `outputs` globs')
        return scan
    before = _digests(ctx, outputs)
    code, out, err = ctx.run(ctx.expand(guard['run']), guard.get('timeout', 600))
    if code != 0:
        scan.integrity.append(f'generator exited {code}: {(err or out).strip()[-500:]}')
        return scan
    after = _digests(ctx, outputs)
    for rel in sorted(set(before) | set(after)):
        if before.get(rel) != after.get(rel):
            state = 'missing from the commit' if rel not in before else 'no longer generated' if rel not in after else 'stale'
            scan.hard.append(Item('generated-drift', rel, path=rel, mode='hard',
                                  message=f'generated file is {state}; the regenerated version is now in the '
                                          f'working tree: review and commit it'))
    scan.coverage = {'scanned': len(after), 'unit': 'generated files'}
    if not after:
        scan.integrity.append(f'no files match outputs {outputs} after running the generator')
    return scan


DIFF_BUILTINS = {'secrets': secrets, 'test-changes': test_changes, 'migrations': migrations, 'deps': deps.check,
                 'diff-coverage': coverage.diff_coverage, 'mutation': coverage.mutation, 'generated': generated}
SCAN_BUILTINS = {'suppressions': suppressions, 'size': size}
