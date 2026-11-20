"""Real tools through the runner. Each test is skipped when its tool is not installed, so the suite
stays runnable anywhere; CI installs the pinned tools and runs all of them.
"""

from __future__ import annotations

import json
import os
import shutil
import unittest

from helpers import RepoCase, problems, status

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS = os.path.join(SKILL, 'examples', 'javascript')
RULES = os.path.join(SKILL, 'rules', 'semgrep')


def need(*tools):
    missing = [t for t in tools if shutil.which(t) is None]
    return unittest.skipIf(missing, f'not installed: {", ".join(missing)}')


def branchy(name: str, branches: int) -> str:
    body = '\n'.join(f'    if x == {i}:\n        return {i}' for i in range(branches))
    return f'def {name}(x):\n{body}\n    return -1\n'


class RealTools(RepoCase):
    def start(self, files, guards):
        repo = self.repo(files, commit=False)
        repo.policy(guards)
        repo.commit('init')
        code, report, err = repo.guard('update')
        self.assertEqual(code, 0, json.dumps(report, indent=1) if isinstance(report, dict) else err)
        repo.commit('baselines')
        repo.branch()
        return repo

    @need('lizard')
    def test_lizard_complexity_by_kind(self):
        guard = {'name': 'complexity', 'run': 'lizard --csv {root}', 'parse': 'lizard', 'tier': 'fast',
                 'version': 'lizard --version'}
        repo = self.start({'src/legacy.py': branchy('legacy', 30), 'src/ok.py': branchy('ok', 3)}, [guard])
        baseline = json.loads(repo.read('guards/baselines/complexity.json'))
        self.assertEqual(baseline['entries']['fn-complexity'], {'src/legacy.py#legacy': 31})
        repo.write({'src/new.py': branchy('fresh', 25), 'tests/test_big.py': branchy('test_table', 40),
                    'src/legacy.py': branchy('legacy', 32)})
        _, report = repo.guard('check')[:2]
        self.assertEqual([p['key'] for p in problems(report, 'complexity', 'new')], ['src/new.py#fresh'])
        self.assertEqual([p['key'] for p in problems(report, 'complexity', 'worse')], ['src/legacy.py#legacy'])

    @need('ruff')
    def test_ruff_sarif(self):
        guard = {'name': 'ruff', 'run': 'cd {root} && ruff check --output-format sarif --output-file {out} .',
                 'parse': 'sarif', 'tier': 'fast', 'version': 'ruff --version', 'config_files': ['ruff.toml']}
        repo = self.start({'src/a.py': 'import os\n', 'ruff.toml': '[lint]\nselect = ["F"]\n'}, [guard])
        self.assertEqual(json.loads(repo.read('guards/baselines/ruff.json'))['entries'], {'F401': {'src/a.py': 1}})
        repo.write({'src/b.py': 'import sys\n', 'src/a.py': 'x = 1\n'})
        code, report, _ = repo.guard('check')
        self.assertEqual(code, 1)
        self.assertEqual([p['key'] for p in problems(report, 'ruff', 'new')], ['src/b.py'])
        self.assertEqual([p['key'] for p in problems(report, 'ruff', 'stale')], ['src/a.py'])
        # Silencing the rule in ruff's own config is a rule change, not an improvement.
        repo.write({'src/b.py': 'import sys\n', 'ruff.toml': '[lint]\nselect = ["E"]\n'})
        code, report, _ = repo.guard('check')
        self.assertTrue(problems(report, 'ruff', 'rule-change', blocking=True))
        code, report, _ = repo.guard('update', '--rules-changed')
        self.assertEqual(code, 1)
        self.assertEqual([p['key'] for p in problems(report, 'ruff', 'rule-change')], ['src/a.py'])

    @need('semgrep')
    def test_bundled_semgrep_rules(self):
        guard = {'name': 'semgrep', 'tier': 'fast', 'parse': 'sarif',
                 'run': f'semgrep scan --metrics=off --disable-version-check --quiet --config {RULES} --sarif '
                        '--output {out} {root}'}
        repo = self.start({'src/ok.py': 'import yaml\n\ndef f(s):\n    return yaml.safe_load(s)\n'}, [guard])
        repo.write({'src/bad.py': 'import yaml\n\ndef f(s):\n    return yaml.load(s, Loader=yaml.Loader)\n',
                    'src/net.js': 'export async function get(u) { return fetch(u); }\n'})
        code, report, _ = repo.guard('check')
        self.assertEqual(code, 1)
        rules = sorted(p['rule'].split('.gr.')[-1] for p in problems(report, 'semgrep', 'new'))
        self.assertEqual(rules, ['js.fetch-without-timeout', 'py.unsafe-deserialization'])

    @need('gitleaks')
    def test_gitleaks_and_builtin_secrets_agree(self):
        guards = [{'name': 'gitleaks', 'tier': 'fast', 'parse': 'sarif', 'run': 'gitleaks dir {root} --no-banner '
                   '--redact --exit-code 0 --report-format sarif --report-path {out}'},
                  {'name': 'secrets', 'builtin': 'secrets', 'tier': 'fast'}]
        repo = self.start({'src/a.py': 'x = 1\n'}, guards)
        token = 'ghp_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'
        repo.write({'src/conf.py': f'TOKEN = "{token}"\n'})
        code, report, _ = repo.guard('check')
        self.assertEqual(code, 1)
        self.assertTrue(problems(report, 'gitleaks', 'new'))
        hard = problems(report, 'secrets', 'hard')
        self.assertEqual(hard[0]['rule'], 'github-token')
        self.assertNotIn(token, json.dumps(report))  # never echo the secret

    @need('zizmor')
    def test_zizmor_workflow_audit(self):
        guard = {'name': 'workflows', 'tier': 'fast', 'parse': 'sarif', 'ok_exit': [0, 10, 11, 12, 13, 14],
                 'run': 'zizmor --offline --format sarif {root}/.github/workflows'}
        safe = 'name: ci\non: push\npermissions: {}\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n'
        repo = self.start({'.github/workflows/ci.yml': safe}, [guard])
        risky = ('name: ci\non: pull_request_target\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n'
                 '      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n'
                 '      - run: echo "${{ github.event.pull_request.title }}"\n')
        repo.write({'.github/workflows/ci.yml': risky})
        code, report, _ = repo.guard('check')
        self.assertEqual(code, 1)
        self.assertTrue(problems(report, 'workflows', 'new'))
        self.assertTrue(problems(report, 'protected', 'protected'))  # CI files are protected as well

    @need('pytest')
    def test_pytest_inventory_and_diff_coverage(self):
        pytest = shutil.which('pytest')
        guards = [{'name': 'tests', 'parse': 'junit', 'tier': 'fast',
                   'run': f'cd {{root}} && {pytest} -q -p no:cacheprovider --junitxml={{out}} --cov=src '
                          '--cov-report=xml:{tmp}/coverage.xml'},
                  {'name': 'diff-coverage', 'builtin': 'diff-coverage', 'input': '{tmp}/coverage.xml', 'tier': 'fast',
                   'min': {'logic': 80}}]
        code_py = 'def add(a, b):\n    return a + b\n'
        test_py = 'from src.calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n\ndef test_zero():\n    assert add(0, 0) == 0\n'
        files = {'src/__init__.py': '', 'src/calc.py': code_py, 'tests/__init__.py': '', 'tests/test_calc.py': test_py,
                 'pyproject.toml': '[tool.pytest.ini_options]\npythonpath = ["."]\n', '.gitignore': '.coverage\n'}
        repo = self.start(files, guards)
        repo.write({'src/calc.py': code_py + '\ndef div(a, b):\n    if b == 0:\n        raise ValueError("b")\n    return a / b\n',
                    'tests/test_calc.py': test_py.replace('\ndef test_zero():\n    assert add(0, 0) == 0\n', '')})
        code, report, _ = repo.guard('check')
        self.assertEqual(code, 1, json.dumps(report, indent=1))
        self.assertEqual([(p['rule'], p['key']) for p in problems(report, 'tests', 'lost')],
                         [('active', 'tests.test_calc::test_zero'), ('present', 'tests.test_calc::test_zero')])
        self.assertEqual([p['rule'] for p in problems(report, 'diff-coverage', 'hard')], ['diff-coverage'])


@unittest.skipIf(shutil.which('node') is None or not os.path.isdir(os.path.join(JS, 'node_modules')),
                 'node or examples/javascript/node_modules missing (npm ci)')
class JavaScriptDetectors(RepoCase):
    def test_reference_detectors_through_the_runner(self):
        guards = [{'name': 'complexity', 'run': f'node {JS}/check-complexity.mjs --root {{root}}', 'tier': 'fast'},
                  {'name': 'cycles', 'run': f'node {JS}/check-cycles.mjs --root {{root}}', 'tier': 'fast',
                   'mode': 'hard'}]
        repo = self.repo({'src/a.js': 'export function a(x) { return x ? 1 : 0; }\n'}, commit=False)
        repo.policy(guards)
        repo.commit()
        self.assertEqual(repo.guard('update')[0], 0)
        repo.commit('baselines')
        repo.branch()
        branches = '\n'.join(f'  if (x === {i}) return {i};' for i in range(24))
        repo.write({'src/b.js': f'import {{ a }} from "./a.js";\nexport function big(x) {{\n{branches}\n  return a(x);\n}}\n',
                    'src/a.js': 'import { big } from "./b.js";\nexport function a(x) { return x ? big(1) : 0; }\n'})
        code, report, _ = repo.guard('check')
        self.assertEqual(code, 1)
        self.assertEqual([p['key'] for p in problems(report, 'complexity', 'new')], ['src/b.js#big'])
        self.assertEqual([p['key'] for p in problems(report, 'cycles', 'hard')], ['src/a.js <-> src/b.js'])
        self.assertEqual(status(report, 'cycles'), 'fail')


if __name__ == '__main__':
    unittest.main()
