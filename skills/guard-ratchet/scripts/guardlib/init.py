"""`guard.py init`: profile a repository and propose a policy that fits it.

The proposal is deterministic for a given repository and tool set. Thresholds come from the code
kind and language defaults in policy.DEFAULTS, never from the current code's distribution: a
threshold fitted to today's code would encode today's problems as the norm.

Guards that need a tool are proposed only when the repository already uses the tool (config or
dependency) or the tool is installed; everything else is listed as a recommendation with the
reason, so the agent can install it (with the user's consent) and rerun init.
"""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter

from . import gitx
from . import policy as pol

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _text(root: str, rel: str) -> str:
    try:
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def profile(root: str) -> dict:
    eff = pol.effective({})
    files = gitx.tracked_files(root)
    kinds, langs = Counter(), Counter()
    for rel in files:
        if pol.is_code(rel):
            kind = pol.kind_by_path(eff, rel)
            kinds[kind] += 1
            if kind not in pol.EXEMPT_KINDS:
                langs[pol.language(rel)] += 1
    npm = _read_json(os.path.join(root, 'package.json'))
    npm_deps = {**npm.get('dependencies', {}), **npm.get('devDependencies', {})}
    pyproject = _text(root, 'pyproject.toml')
    py_reqs = pyproject + ''.join(_text(root, f) for f in files if os.path.basename(f).startswith('requirements')
                                  and f.endswith('.txt'))
    names = {os.path.basename(f) for f in files}
    has = lambda *globs: any(pol.any_match(f, globs) for f in files)
    return {
        'files': len(files),
        'languages': dict(langs.most_common()),
        'kinds': dict(sorted(kinds.items())),
        'npm': npm_deps,
        'npm_scripts': npm.get('scripts', {}),
        'python_text': py_reqs,
        'eslint': has('eslint.config.*', '.eslintrc*', '**/eslint.config.*') or 'eslint' in npm_deps,
        'tsconfig': has('tsconfig.json') and 'typescript' in npm_deps,
        'ruff': has('ruff.toml', '.ruff.toml') or '[tool.ruff' in pyproject or 'ruff' in py_reqs,
        'mypy': has('mypy.ini', '.mypy.ini') or '[tool.mypy' in pyproject,
        'pytest': 'pytest' in py_reqs or has('pytest.ini', 'conftest.py', '**/conftest.py'),
        'pytest_cov': 'pytest-cov' in py_reqs,
        'go': 'go.mod' in names,
        'cargo': 'Cargo.toml' in names,
        'lockfiles': sorted(f for f in files if os.path.basename(f) in (
            'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock', 'uv.lock', 'Pipfile.lock', 'go.sum',
            'Cargo.lock', 'Gemfile.lock', 'composer.lock', 'gradle.lockfile', 'packages.lock.json', 'pubspec.lock',
            'mix.lock', 'requirements.txt')),
        'manifests': any('deps' in pol.roles_of(eff, f) for f in files),
        'migrations': any('migration' in pol.roles_of(eff, f) for f in files),
        'workflows': has('.github/workflows/*.y*ml'),
        'tools': {t: shutil.which(t) is not None for t in
                  ('lizard', 'semgrep', 'gitleaks', 'osv-scanner', 'zizmor', 'ruff', 'mypy', 'gotestsum', 'golangci-lint')},
    }


def _js_tests(p: dict, guards: list, recs: list) -> None:
    deps = p['npm']
    if 'vitest' in deps:
        coverage = '@vitest/coverage-v8' in deps or '@vitest/coverage-istanbul' in deps
        run = 'cd {root} && npx --no-install vitest run --reporter=junit --outputFile={out}'
        if coverage:
            run += ' --coverage --coverage.reporter=lcov --coverage.reportsDirectory={tmp}/js-coverage --coverage.all'
        guards.append({'name': 'tests', 'run': run, 'parse': 'junit', 'tier': 'standard', 'timeout': 1800,
                       'note': 'test inventory: removed or newly skipped tests fail; failing tests are hard'})
        if coverage:
            guards.append({'name': 'diff-coverage', 'builtin': 'diff-coverage', 'input': '{tmp}/js-coverage/lcov.info',
                           'min': {'logic': 80}, 'tier': 'standard'})
    elif 'jest' in deps and 'jest-junit' in deps:
        guards.append({'name': 'tests', 'run': 'cd {root} && JEST_JUNIT_OUTPUT_FILE={out} npx --no-install jest --ci '
                       '--reporters=default --reporters=jest-junit --coverage --coverageReporters=lcov '
                       '--coverageDirectory={tmp}/js-coverage', 'parse': 'junit', 'tier': 'standard',
                       'timeout': 1800})
        guards.append({'name': 'diff-coverage', 'builtin': 'diff-coverage', 'input': '{tmp}/js-coverage/lcov.info',
                       'min': {'logic': 80}, 'tier': 'standard'})
    elif 'jest' in deps:
        recs.append('jest: add jest-junit (devDependency) so the test inventory guard can read results')
    elif 'node --test' in json.dumps(p['npm_scripts']):
        guards.append({'name': 'tests', 'run': 'cd {root} && node --test --test-reporter=junit '
                       '--test-reporter-destination={out}', 'parse': 'junit', 'tier': 'standard', 'timeout': 1800})
    if '@stryker-mutator/core' in deps:
        guards.append({'name': 'mutation', 'builtin': 'mutation', 'tier': 'strict',
                       'run': 'npx --no-install stryker run --reporters json', 'input': 'reports/mutation/mutation.json',
                       'min_score': 60, 'timeout': 3600})


def _python(p: dict, guards: list, recs: list) -> None:
    if p['ruff'] or p['tools']['ruff']:
        guards.append({'name': 'ruff', 'run': 'cd {root} && ruff check --output-format sarif --output-file {out} .',
                       'parse': 'sarif', 'tier': 'fast', 'requires': ['ruff'], 'version': 'ruff --version',
                       'config_files': ['**/ruff.toml', '**/.ruff.toml', '**/pyproject.toml']})
    if p['mypy']:
        guards.append({'name': 'mypy', 'run': 'cd {root} && mypy --no-error-summary --show-error-codes .',
                       'parse': 'mypy', 'tier': 'standard', 'requires': ['mypy'], 'version': 'mypy --version',
                       'config_files': ['**/mypy.ini', '**/.mypy.ini', '**/pyproject.toml', '**/setup.cfg']})
    if p['pytest']:
        run = 'cd {root} && python3 -m pytest -q -p no:cacheprovider --junitxml={out}'
        if p['pytest_cov']:
            run += ' --cov --cov-report=xml:{tmp}/coverage.xml'
        guards.append({'name': 'tests', 'run': run, 'parse': 'junit', 'tier': 'standard', 'timeout': 1800,
                       'note': 'test inventory: removed or newly skipped tests fail; failing tests are hard'})
        if p['pytest_cov']:
            guards.append({'name': 'diff-coverage', 'builtin': 'diff-coverage', 'input': '{tmp}/coverage.xml',
                           'min': {'logic': 80}, 'tier': 'standard'})
        else:
            recs.append('pytest: add pytest-cov to enable the diff-coverage guard')


def propose(root: str, p: dict) -> tuple[dict, list[str]]:
    guards, recs = [], []
    guards.append({'name': 'secrets', 'builtin': 'secrets', 'tier': 'fast'})
    guards.append({'name': 'suppressions', 'builtin': 'suppressions', 'tier': 'fast'})
    guards.append({'name': 'size', 'builtin': 'size', 'tier': 'fast'})
    guards.append({'name': 'test-changes', 'builtin': 'test-changes', 'tier': 'fast'})
    if p['manifests']:
        guards.append({'name': 'deps', 'builtin': 'deps', 'tier': 'fast', 'when': ['deps']})
    if p['migrations']:
        guards.append({'name': 'migrations', 'builtin': 'migrations', 'tier': 'fast', 'when': ['migration']})
    if p['tools']['lizard']:
        guards.append({'name': 'complexity', 'tier': 'fast', 'requires': ['lizard'], 'version': 'lizard --version',
                       'run': f'lizard --csv -x "*/node_modules/*" -x "*/vendor/*" -x "*/.git/*" '
                              f'-x "*/{pol.DEFAULTS["runner"]}/*" {{root}}',
                       'parse': 'lizard', 'note': 'fn-complexity and fn-length, judged by thresholds per code kind'})
    else:
        recs.append('complexity: install lizard (pipx install lizard) for function complexity/length in ~30 languages')
    if p['eslint']:
        guards.append({'name': 'eslint', 'run': 'cd {root} && npx --no-install eslint -f json .', 'parse': 'eslint',
                       'tier': 'fast', 'version': 'npx --no-install eslint --version',
                       'config_files': ['**/eslint.config.*', '**/.eslintrc*', '**/.eslintignore']})
    if p['tsconfig']:
        guards.append({'name': 'typecheck', 'run': 'cd {root} && npx --no-install tsc --noEmit --pretty false -p .',
                       'parse': 'tsc', 'tier': 'standard', 'version': 'npx --no-install tsc --version',
                       'config_files': ['**/tsconfig*.json', '**/jsconfig*.json']})
    _js_tests(p, guards, recs)
    _python(p, guards, recs)
    if p['go']:
        guards.append({'name': 'go-vet', 'run': 'cd {root} && go vet ./... 2>&1', 'parse': 'gcc', 'tier': 'fast',
                       'requires': ['go'], 'version': 'go version', 'ok_exit': [0, 1]})
        if p['tools']['gotestsum']:
            guards.append({'name': 'tests', 'run': 'cd {root} && gotestsum --junitfile {out} -- '
                           '-coverprofile={tmp}/go.cover ./...', 'parse': 'junit', 'tier': 'standard',
                           'requires': ['gotestsum'], 'timeout': 1800})
            guards.append({'name': 'diff-coverage', 'builtin': 'diff-coverage', 'input': '{tmp}/go.cover',
                           'min': {'logic': 80}, 'tier': 'standard'})
        else:
            recs.append('go: install gotestsum to enable the test inventory and diff-coverage guards')
    if p['cargo']:
        guards.append({'name': 'build', 'run': 'cd {root} && cargo check --locked --all-targets --quiet',
                       'parse': 'exit', 'tier': 'fast', 'requires': ['cargo']})
    bundled = {'python', 'javascript', 'typescript'} & set(p['languages'])
    if p['tools']['semgrep'] and bundled:
        rules = os.path.join(pol.DEFAULTS['runner'], 'rules', 'semgrep')
        guards.append({'name': 'semgrep', 'tier': 'standard', 'requires': ['semgrep'], 'version': 'semgrep --version',
                       'run': f'semgrep scan --metrics=off --disable-version-check --quiet --config {rules} '
                              '--sarif --output {out} {root}',
                       'parse': 'sarif', 'config_files': ['**/.semgrepignore', f'{rules}/*.yaml']})
    elif bundled:
        recs.append('security/stability: install semgrep to run the bundled rule pack (rules/semgrep)')
    others = sorted(set(p['languages']) - {'python', 'javascript', 'typescript'})
    if others:
        recs.append(f"security/stability for {', '.join(others)}: the bundled Semgrep rules cover Python and "
                    f"JavaScript/TypeScript only; add the language's own analyzer (references/language-recipes.md) "
                    f"or vendored Semgrep rules for it")
    if p['tools']['gitleaks']:
        guards.append({'name': 'gitleaks', 'tier': 'fast', 'requires': ['gitleaks'], 'version': 'gitleaks version',
                       'run': 'gitleaks dir {root} --no-banner --redact --exit-code 0 --report-format sarif '
                              '--report-path {out}', 'parse': 'sarif', 'config_files': ['**/.gitleaks.toml', '**/.gitleaksignore']})
    if p['lockfiles']:
        if p['tools']['osv-scanner']:
            guards.append({'name': 'vulns', 'tier': 'standard', 'when': ['deps'], 'requires': ['osv-scanner'],
                           'version': 'osv-scanner --version',
                           'run': 'osv-scanner scan source -r --format sarif --output-file {out} {root}',
                           'parse': 'sarif', 'ok_exit': [0, 1],
                           'note': 'runs when dependencies change; schedule `check --full` to catch new advisories'})
        else:
            recs.append('dependencies: install osv-scanner for known-vulnerability checks on lockfiles')
    if p['workflows']:
        if p['tools']['zizmor']:
            guards.append({'name': 'workflows', 'tier': 'standard', 'when': ['ci'], 'requires': ['zizmor'],
                           'version': 'zizmor --version', 'run': 'zizmor --offline --format sarif {root}/.github/workflows',
                           'parse': 'sarif', 'ok_exit': [0, 10, 11, 12, 13, 14]})
        else:
            recs.append('CI: install zizmor to audit GitHub Actions workflows (injection, permissions, pinning)')
    return {'version': 2, 'runner': pol.DEFAULTS['runner'], 'guards': guards}, recs


def install_runner(root: str, runner: str) -> list[str]:
    """Copy guard.py, guardlib/ and the rule packs into the repository (a copy, so CI does not depend
    on where the skill happens to be installed)."""
    target = os.path.join(root, runner)
    if os.path.realpath(target) == os.path.realpath(SCRIPT_DIR):
        return []
    copied = []
    os.makedirs(target, exist_ok=True)
    shutil.copy2(os.path.join(SCRIPT_DIR, 'guard.py'), os.path.join(target, 'guard.py'))
    copied.append(f'{runner}/guard.py')
    code_only = shutil.ignore_patterns('__pycache__', '*.pyc')

    def rules_only(folder, names):  # rule files only: the rule tests are deliberately vulnerable code
        return [n for n in names if not os.path.isdir(os.path.join(folder, n)) and not n.endswith(('.yaml', '.yml'))]
    for name, src, ignore in (('guardlib', os.path.join(SCRIPT_DIR, 'guardlib'), code_only),
                              ('rules', os.path.join(SKILL_DIR, 'rules'), rules_only)):
        dst = os.path.join(target, name)
        if os.path.isdir(src):
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst, ignore=ignore)
            copied.append(f'{runner}/{name}/')
    return copied
