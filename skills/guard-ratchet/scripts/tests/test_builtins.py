"""Built-in guard tests: secrets, suppressions, size, test-changes, migrations, generated, deps,
diff-coverage and mutation.

Each test builds a throwaway git repo, commits a baseline on main, branches, applies the change to the
working tree (no commit needed: the change set compares the working tree with the merge-base) and calls the
built-in directly. Assertions are on the Scan: `hard` blocks, `advisory` is evidence, `integrity` means the
scan cannot be trusted, `findings`/`metrics` feed the ratchet.

Secret-looking strings are assembled at runtime from random characters so this file never contains a
credential-shaped literal.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import string
import sys
import tempfile
import time
import unittest
from typing import ClassVar

import helpers
from helpers import RepoCase, git

from guardlib import builtins, coverage, deps, gitx
from guardlib import policy as pol
from guardlib.context import Context

NEEDS_TOML = unittest.skipIf(sys.version_info < (3, 11), 'TOML manifests need Python 3.11+ (tomllib)')

ALNUM = string.ascii_letters + string.digits
UPPER_DIGITS = string.ascii_uppercase + string.digits
URLSAFE = ALNUM + '_-'


def rnd(seed: int, n: int, alphabet: str = ALNUM) -> str:
    rng = random.Random(seed)
    return ''.join(rng.choice(alphabet) for _ in range(n))


def fixture(name: str) -> str:
    with open(os.path.join(helpers.FIXTURES, name), encoding='utf-8') as fh:
        return fh.read()


def numbered_file(n: int) -> str:
    return ''.join(f'value_{i} = {i}\n' for i in range(1, n + 1))


def rules(items):
    return [i.rule for i in items]


def keys(items):
    return [i.key for i in items]


class BuiltinCase(RepoCase):
    """RepoCase plus helpers to build a Context and run one built-in against a change."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='guard-tmp-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def ctx(self, repo, **policy_extra) -> Context:
        _, policy = pol.load(repo.root, json.dumps({'version': 2, 'guards': [], **policy_extra}))
        base = gitx.resolve_base(repo.root, 'main')
        return Context(repo.root, repo.root, policy, gitx.changeset(repo.root, base), self.tmp)

    def scan(self, fn, base=None, change=None, guard=None, history=(), policy=None):
        """Baseline `base` on main; branch; commit each dict in `history`; leave `change` uncommitted."""
        repo = self.repo(base or {'README.md': 'hello\n'})
        repo.branch()
        for files in history:
            repo.write(files)
            repo.commit('branch work')
        if change:
            repo.write(change)
        return fn(self.ctx(repo, **(policy or {})), {'name': 'g', **(guard or {})})

    def scan_repo(self, repo, fn, guard=None, policy=None):
        return fn(self.ctx(repo, **(policy or {})), {'name': 'g', **(guard or {})})


# ─── secrets ─────────────────────────────────────────────────────────────────
def secret_samples() -> dict[str, str]:
    return {
        'private-key': '-----BEGIN ' + 'RSA PRIVATE KEY-----',
        'aws-access-key-id': 'AKIA' + rnd(1, 16, UPPER_DIGITS),
        'github-token': 'ghp_' + rnd(2, 36),
        'github-fine-grained-token': 'github_pat_' + rnd(3, 60, ALNUM + '_'),
        'gitlab-token': 'glpat-' + rnd(4, 24, URLSAFE),
        'slack-token': 'xoxb-' + rnd(5, 24, ALNUM + '-'),
        'slack-webhook': 'https://hooks.slack.com/services/T' + rnd(6, 9, UPPER_DIGITS) + '/B'
                         + rnd(7, 9, UPPER_DIGITS) + '/' + rnd(8, 24),
        'stripe-live-key': 'sk_live_' + rnd(9, 26),
        'google-api-key': 'AIza' + rnd(10, 35, URLSAFE),
        'openai-key': 'sk-' + rnd(11, 20, URLSAFE) + 'T3BlbkFJ' + rnd(12, 20, URLSAFE),
        'anthropic-key': 'sk-ant-api03-' + rnd(13, 90, URLSAFE),
        'npm-token': 'npm_' + rnd(14, 36),
        'pypi-token': 'pypi-AgEIcHlwaS5vcmc' + rnd(15, 70, URLSAFE),
        'sendgrid-key': 'SG.' + rnd(16, 22, URLSAFE) + '.' + rnd(17, 43, URLSAFE),
    }


class SecretsTest(BuiltinCase):
    def secrets(self, base=None, change=None, **kw):
        return self.scan(builtins.secrets, base, change, **kw)

    def test_samples_are_not_accidentally_placeholders(self):
        for name, value in secret_samples().items():
            self.assertFalse(builtins.PLACEHOLDER.search(value), name)
        self.assertEqual(set(secret_samples()), {n for n, _ in builtins.SECRET_PATTERNS})

    def test_every_credential_pattern_is_detected_in_an_added_line(self):
        for name, value in secret_samples().items():
            with self.subTest(name):
                scan = self.secrets(change={'src/conf.py': f'KEY = "{value}"\n'})
                self.assertEqual(rules(scan.hard), [name])
                item = scan.hard[0]
                self.assertEqual((item.path, item.line, item.mode), ('src/conf.py', 1, 'hard'))
                self.assertNotIn(value, item.message, 'the message must not repeat the secret')
                self.assertNotIn(value, item.key, 'the key must not embed the secret')
                self.assertEqual(scan.integrity, [])

    def test_untracked_new_file_is_scanned(self):
        value = secret_samples()['github-token']
        repo = self.repo({'README.md': 'x\n'})
        repo.branch()
        repo.write({'new/dir/token.txt': f'token={value}\n'})
        scan = self.scan_repo(repo, builtins.secrets)
        self.assertEqual(rules(scan.hard), ['github-token'])
        self.assertEqual(scan.hard[0].path, 'new/dir/token.txt')

    def test_secret_added_in_a_branch_commit_is_still_reported(self):
        value = secret_samples()['npm-token']
        scan = self.secrets(history=[{'src/a.py': f'T = "{value}"\n'}])
        self.assertEqual(rules(scan.hard), ['npm-token'])

    def test_key_is_stable_across_line_moves_and_distinguishes_values(self):
        samples = secret_samples()
        value, other = samples['aws-access-key-id'], 'AKIA' + rnd(99, 16, UPPER_DIGITS)
        at_top = self.secrets(change={'src/a.py': f'K = "{value}"\n'})
        moved = self.secrets(change={'src/a.py': '\n' * 40 + f'K = "{value}"\n'})
        different = self.secrets(change={'src/a.py': f'K = "{other}"\n'})
        self.assertEqual(keys(at_top.hard), keys(moved.hard))
        self.assertNotEqual(at_top.hard[0].line, moved.hard[0].line)
        self.assertNotEqual(keys(at_top.hard), keys(different.hard))
        self.assertRegex(at_top.hard[0].key, r'^src/a\.py#aws-access-key-id#[0-9a-f]{12}$')

    def test_placeholders_and_documented_examples_are_ignored(self):
        text = '\n'.join([
            'AWS_EXAMPLE = "AKIAIOSFODNN7EXAMPLE"',
            'GH = "ghp_' + 'x' * 36 + '"',
            'AWS_X = "AKIA' + 'X' * 16 + '"',
            'STRIPE = "sk_live_' + '*' * 4 + 'abcdefghijklmnopqrstuvwx"',
            'DUMMY = "ghp_' + 'dummy' * 8 + '"',
            'NPM = "npm_' + 'changeme' * 5 + '"',
        ]) + '\n'
        scan = self.secrets(change={'docs/setup.py': text})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_near_misses_are_ignored(self):
        text = '\n'.join([
            'SHORT_AWS = "AKIA' + rnd(1, 15, UPPER_DIGITS) + '"',
            'LONG_BLOB = "AKIA' + rnd(2, 17, UPPER_DIGITS) + '"',
            'SHORT_GH = "ghp_' + rnd(3, 30) + '"',
            'LOWER = "akia' + rnd(4, 16, string.ascii_lowercase) + '"',
            'PREFIXED = "xAKIA' + rnd(5, 16, UPPER_DIGITS) + '"',
        ]) + '\n'
        scan = self.secrets(change={'src/a.py': text})
        self.assertEqual(scan.hard, [])

    def test_secret_already_on_base_is_not_reported_again(self):
        value = secret_samples()['gitlab-token']
        base = {'src/old.py': f'T = "{value}"\n', 'src/b.py': 'x = 1\n'}
        scan = self.secrets(base=base, change={'src/b.py': 'x = 2\n', 'src/old.py': f'T = "{value}"\n# kept\n'})
        self.assertEqual(scan.hard, [])

    def test_removed_secret_and_deleted_file_are_clean(self):
        value = secret_samples()['gitlab-token']
        base = {'src/old.py': f'T = "{value}"\n', 'src/gone.py': f'T = "{value}"\n'}
        scan = self.secrets(base=base, change={'src/old.py': 'T = None\n', 'src/gone.py': None})
        self.assertEqual(scan.hard, [])

    def test_pure_rename_of_a_file_holding_a_secret_adds_nothing(self):
        value = secret_samples()['github-token']
        repo = self.repo({'src/old.py': f'T = "{value}"\n'})
        repo.branch()
        git(repo.root, 'mv', 'src/old.py', 'src/new.py')
        self.assertEqual(self.scan_repo(repo, builtins.secrets).hard, [])

    def test_excluded_paths_are_not_scanned(self):
        value = secret_samples()['github-token']
        scan = self.secrets(change={'legacy/a.py': f'T = "{value}"\n'}, policy={'exclude': ['legacy/**']})
        self.assertEqual((scan.hard, scan.coverage['scanned']), ([], 0))

    def test_url_credentials_are_advisory_only(self):
        text = 'DB = "postgres://admin:s3cr3tPassw0rd@db.internal.corp/app"\nB = "postgres://admin:s3cr3tPassw0rd@db.internal.corp/b"\n'
        scan = self.secrets(change={'src/conf.py': text})
        self.assertEqual(scan.hard, [])
        self.assertEqual(rules(scan.advisory), ['url-credentials', 'url-credentials'])
        self.assertEqual(set(keys(scan.advisory)), {'src/conf.py#url-credentials'})
        self.assertEqual([i.line for i in scan.advisory], [1, 2])

    def test_url_without_a_real_password_is_ignored(self):
        text = 'LOCAL = "postgres://admin:s3cr3tPassw0rd@localhost/app"\nLOOPBACK = "redis://admin:s3cr3tPassw0rd@127.0.0.1:6379"\nEXAMPLE = "https://user:password123@example.com/x"\nTEMPLATE = "postgres://user:${DB_PASSWORD}@db.internal.corp/app"\nANGLE = "https://user:<password>@db.internal.corp/app"\nSHORT = "https://user:pw@db.internal.corp/app"\nPLAIN = "https://db.internal.corp:8443/app"' + '\n'
        scan = self.secrets(change={'src/conf.py': text})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_files_that_normally_hold_credentials_are_hard(self):
        pem = '-----BEGIN ' + 'PRIVATE KEY-----\nabc\n'
        change = {
            '.env': 'A=1\n', 'config/.env.production': 'A=1\n', 'deploy/server.pem': pem, 'keys/server.key': pem,
            'id_rsa': 'x\n', 'home/.netrc': 'machine h\n', 'release.keystore': 'bin\n', 'vault.kdbx': 'bin\n',
            '.aws/credentials': '[default]\n', 'creds/credentials': 'aws_secret_access_key = abc\n',
        }
        scan = self.secrets(change=change)
        flagged = {i.key for i in scan.hard if i.rule == 'secret-file'}
        self.assertEqual(flagged, set(change))

    def test_template_public_and_non_secret_look_alikes_are_not_flagged(self):
        change = {
            '.env.example': 'A=\n', '.env.sample': 'A=\n', '.env.template': 'A=\n', '.env.dist': 'A=\n',
            '.env.defaults': 'A=\n', 'ca.pem': '-----BEGIN CERTIFICATE-----\nabc\n', 'public.key': 'ssh-rsa AAAA\n',
            'id_rsa.pub': 'ssh-rsa AAAA\n', 'src/credentials': 'class Credentials: pass\n', 'environment.py': 'x = 1\n',
        }
        scan = self.secrets(change=change)
        self.assertEqual([i for i in scan.hard if i.rule == 'secret-file'], [])

    def test_copied_env_file_is_flagged(self):
        repo = self.repo({'.env.example': 'A=\n'})
        repo.branch()
        shutil.copy(os.path.join(repo.root, '.env.example'), os.path.join(repo.root, '.env'))
        scan = self.scan_repo(repo, builtins.secrets)
        self.assertEqual(keys(scan.hard), ['.env'])

    def test_gitignored_env_file_is_not_part_of_the_change(self):
        scan = self.secrets(change={'.gitignore': '.env\n', '.env': 'A=1\n'})
        self.assertEqual(scan.hard, [])

    def test_secret_file_already_on_base_is_not_reported_as_new(self):
        scan = self.secrets(base={'.env': 'A=1\n'}, change={'.env': 'A=2\n'})
        self.assertEqual([i for i in scan.hard if i.rule == 'secret-file'], [])

    def test_env_file_created_by_renaming_a_template_is_flagged(self):
        repo = self.repo({'.env.example': 'A=\n'})
        repo.branch()
        git(repo.root, 'mv', '.env.example', '.env')
        scan = self.scan_repo(repo, builtins.secrets)
        self.assertEqual(keys(scan.hard), ['.env'])

    def test_coverage_counts_changed_files_not_deleted_ones(self):
        scan = self.secrets(base={'a.py': 'a\n', 'b.py': 'b\n'}, change={'a.py': 'a2\n', 'b.py': None, 'c.py': 'c\n'})
        self.assertEqual(scan.coverage, {'scanned': 2, 'unit': 'changed files'})


# ─── suppressions ────────────────────────────────────────────────────────────
SUPPRESSION_CASES = [
    ('src/a.py', 'x = 1  # noqa: E501\n', 'suppress-lint'),
    ('src/a.js', '// eslint-disable-next-line no-console\n', 'suppress-lint'),
    ('src/a.py', 'import os  # pylint: disable=unused-import\n', 'suppress-lint'),
    ('src/a.go', '//nolint:errcheck\n', 'suppress-lint'),
    ('src/a.rs', '#[allow(dead_code)]\nfn f() {}\n', 'suppress-lint'),
    ('src/a.rs', '#![allow(unused)]\n', 'suppress-lint'),
    ('src/a.rs', '#[expect(dead_code)]\nfn f() {}\n', 'suppress-lint'),
    ('src/a.py', 'import os  # NOQA\n', 'suppress-lint'),
    ('src/a.py', '# ruff: noqa\n', 'suppress-lint'),
    ('src/a.py', '# flake8: noqa\n', 'suppress-lint'),
    ('src/a.dart', '// ignore_for_file: avoid_print\n', 'suppress-lint'),
    ('src/A.cs', '[SuppressMessage("Style", "IDE0001")]\n', 'suppress-lint'),
    ('src/a.py', '# mypy: disable-error-code="attr-defined"\n', 'suppress-type'),
    ('src/a.py', '# pyright: reportMissingImports=false\n', 'suppress-type'),
    ('src/a.py', 'x = f()  # pyre-ignore[16]\n', 'suppress-type'),
    ('src/a.py', '# pytype: disable=attribute-error\n', 'suppress-type'),
    ('src/a.py', '# pylint: skip-file\n', 'suppress-lint'),
    ('src/a.ts', '// tslint:disable-next-line\n', 'suppress-lint'),
    ('src/a.rs', '#[cfg_attr(feature = "x", allow(dead_code))]\n', 'suppress-lint'),
    ('src/a.py', 'eval(x)  # nosem\n', 'suppress-security'),
    ('src/A.java', '@SuppressWarnings("unchecked")\n', 'suppress-lint'),
    ('src/a.ts', '// @ts-ignore\n', 'suppress-type'),
    ('src/a.ts', '// @ts-expect-error\n', 'suppress-type'),
    ('src/a.py', 'x = 1  # type: ignore[attr-defined]\n', 'suppress-type'),
    ('src/a.py', 'def f():  # pragma: no cover\n    pass\n', 'suppress-coverage'),
    ('src/a.js', '/* istanbul ignore next */\n', 'suppress-coverage'),
    ('src/a.go', '// LCOV_EXCL_LINE\n', 'suppress-coverage'),
    ('src/a.py', 'os.system(cmd)  # nosec\n', 'suppress-security'),
    ('src/a.js', '// nosemgrep: some-rule\n', 'suppress-security'),
    ('src/a.py', 'x = 1  # guard-allow(because)\n', 'guard-allow'),
]
TEST_ONLY_CASES = [
    ('tests/test_a.py', '@pytest.mark.skip(reason="later")\ndef test_a(): pass\n', 'test-skip'),
    ('tests/test_a.py', 'class T:\n    @unittest.skip("later")\n    def test_a(self): pass\n', 'test-skip'),
    ('tests/test_a.py', 'class T:\n    @unittest.expectedFailure\n    def test_a(self): pass\n', 'test-skip'),
    ('tests/test_a.py', 'def test_a():\n    pytest.skip("no gpu")\n', 'test-skip'),
    ('web/a.test.js', 'it.skip("works", () => {});\n', 'test-skip'),
    ('web/a.test.js', 'xdescribe("suite", () => {});\n', 'test-skip'),
    ('pkg/a_test.go', 'func TestA(t *testing.T) { t.Skip("flaky") }\n', 'test-skip'),
    ('src/test/java/ATest.java', '@Disabled\nclass ATest {}\n', 'test-skip'),
]
FOCUS_CASES = [
    ('web/a.test.js', 'it.only("works", () => {});\n'),
    ('web/a.test.js', 'fdescribe("suite", () => {});\n'),
    ('web/a.test.js', 'describe.only("suite", () => {});\n'),
]


class SuppressionsTest(BuiltinCase):
    def suppressions(self, files, **kw):
        return self.scan(builtins.suppressions, change=files, **kw)

    def test_each_suppression_family_is_counted(self):
        for path, text, family in SUPPRESSION_CASES:
            with self.subTest(path=path, family=family, text=text):
                scan = self.suppressions({path: text})
                self.assertEqual([(i.rule, i.key, i.count) for i in scan.findings], [(family, path, 1)])
                self.assertEqual(scan.hard, [])

    def test_test_only_families_are_counted_in_test_files(self):
        for path, text, family in TEST_ONLY_CASES:
            with self.subTest(path=path, text=text):
                scan = self.suppressions({path: text})
                self.assertEqual([(i.rule, i.key) for i in scan.findings], [(family, path)])

    def test_skip_markers_in_non_test_files_are_ignored(self):
        change = {
            'src/helpers.py': '# docs: use @pytest.mark.skip(reason="x") or pytest.skip("y") in tests\nx = 1\n',
            'src/app.js': '// it.skip("not a test file")\nconst a = 1;\n',
            'src/runner.go': 'func f(t *testing.T) { t.Skip("not a _test file") }\n',
            'src/Thing.java': '@Disabled\nclass Thing {}\n',
        }
        scan = self.suppressions(change)
        self.assertEqual((scan.findings, scan.hard), ([], []))

    def test_focus_markers_in_tests_are_hard(self):
        for path, text in FOCUS_CASES:
            with self.subTest(text=text):
                scan = self.suppressions({path: text})
                self.assertEqual([(i.rule, i.key, i.count, i.mode) for i in scan.hard], [('test-focus', path, 1, 'hard')])
                self.assertEqual(scan.findings, [])

    def test_focus_markers_in_non_test_files_are_ignored(self):
        scan = self.suppressions({'src/app.js': 'it.only("x", () => {});\n'})
        self.assertEqual((scan.hard, scan.findings), ([], []))

    def test_count_is_per_file_and_per_family(self):
        text = 'a = 1  # noqa\nb = 2  # noqa\nc = 3  # type: ignore\n'
        scan = self.suppressions({'src/a.py': text, 'src/b.py': 'd = 4  # noqa\n'})
        got = {(i.rule, i.key): i.count for i in scan.findings}
        self.assertEqual(got, {('suppress-lint', 'src/a.py'): 2, ('suppress-type', 'src/a.py'): 1,
                               ('suppress-lint', 'src/b.py'): 1})

    def test_whole_tree_is_scanned_including_unchanged_files(self):
        scan = self.scan(builtins.suppressions, base={'src/old.py': 'x = 1  # noqa\n'}, change={'src/new.py': 'y = 1\n'})
        self.assertEqual(keys(scan.findings), ['src/old.py'])

    def test_deleted_files_are_not_scanned(self):
        scan = self.scan(builtins.suppressions, base={'src/old.py': 'x = 1  # noqa\n'}, change={'src/old.py': None})
        self.assertEqual(scan.findings, [])

    def test_guard_mode_is_applied_to_findings(self):
        scan = self.suppressions({'src/a.py': 'x = 1  # noqa\n'}, guard={'mode': 'budget'})
        self.assertEqual([i.mode for i in scan.findings], ['budget'])
        self.assertEqual([i.mode for i in self.suppressions({'src/a.py': 'x = 1  # noqa\n'}).findings], ['ratchet'])

    def test_generated_vendor_docs_and_excluded_files_are_not_scanned(self):
        change = {
            'vendor/lib/a.py': 'x = 1  # noqa\n',
            'node_modules/pkg/index.js': '// eslint-disable\n',
            'src/gen.py': '# @generated by tool\nx = 1  # noqa\n',
            'src/schema.generated.ts': '// @ts-ignore\n',
            'README.md': 'use `# noqa` sparingly, and `eslint-disable` too\n',
            'config.json': '{"note": "# noqa"}\n',
            'legacy/old.py': 'x = 1  # noqa\n',
        }
        scan = self.suppressions(change, policy={'exclude': ['legacy/**']})
        self.assertEqual(scan.findings, [])

    def test_look_alikes_are_not_suppressions(self):
        text = 'noqa = 1\nskipped = True\nignore_errors = False\nmy_type_ignore = 2\nallow = 3\n'
        self.assertEqual(self.suppressions({'src/a.py': text}).findings, [])
        test_text = 'def test_a():\n    assert test.skipped\n    assert it.only_one\n'
        self.assertEqual(self.suppressions({'tests/test_a.py': test_text}).findings, [])

    def test_keys_are_paths_without_line_numbers(self):
        scan = self.suppressions({'src/a.py': '\n' * 30 + 'x = 1  # noqa\n'})
        self.assertEqual(keys(scan.findings), ['src/a.py'])

    def test_coverage_counts_code_files(self):
        scan = self.suppressions({'src/a.py': 'a = 1\n', 'src/b.js': 'b = 1\n', 'notes.txt': 'n\n'})
        self.assertEqual(scan.coverage, {'scanned': 2, 'unit': 'files'})


# ─── size ────────────────────────────────────────────────────────────────────
class SizeTest(BuiltinCase):
    def test_counts_non_blank_lines_per_code_file(self):
        files = {
            'src/a.py': 'x = 1\n\n   \ny = 2\n\n\n',
            'src/b.js': 'a\nb\nc',                       # no trailing newline
            'src/c.py': 'p = 1\r\n\r\nq = 2\r\n',        # CRLF
            'src/empty.py': '',
            'tests/test_a.py': 'import unittest\n',
        }
        scan = self.scan(builtins.size, change=files)
        sizes = {m['key']: m['value'] for m in scan.metrics}
        self.assertEqual(sizes, {'src/a.py': 2, 'src/b.js': 3, 'src/c.py': 2, 'src/empty.py': 0,
                                 'tests/test_a.py': 1})
        self.assertTrue(all(m['metric'] == 'file-size' and m['path'] == m['key'] for m in scan.metrics))
        self.assertEqual(scan.coverage, {'scanned': 5, 'unit': 'files'})

    def test_non_code_generated_vendor_excluded_and_deleted_files_are_skipped(self):
        base = {'src/gone.py': 'a = 1\n'}
        change = {'README.md': 'a\nb\n', 'data.json': '{}\n', 'vendor/x/a.py': 'a = 1\n', 'src/gone.py': None,
                  'src/gen.py': '# DO NOT EDIT\nx = 1\n', 'legacy/a.py': 'a = 1\n', 'src/ok.py': 'a = 1\n'}
        scan = self.scan(builtins.size, base=base, change=change, policy={'exclude': ['legacy/**']})
        self.assertEqual([m['key'] for m in scan.metrics], ['src/ok.py'])

    def test_uncommitted_edits_are_measured(self):
        scan = self.scan(builtins.size, base={'src/a.py': 'a = 1\n'}, change={'src/a.py': 'a = 1\nb = 2\nc = 3\n'})
        self.assertEqual(scan.metrics[0]['value'], 3)

    def test_untracked_files_are_measured(self):
        scan = self.scan(builtins.size, change={'new/deep/mod.py': 'a = 1\nb = 2\n'})
        self.assertEqual({m['key']: m['value'] for m in scan.metrics}, {'new/deep/mod.py': 2})


# ─── test-changes ────────────────────────────────────────────────────────────
CALC = 'def add(a, b):\n    return a + b\n'
CALC_TEST = ('import unittest\nfrom src.calc import add\n\n\nclass T(unittest.TestCase):\n'
             '    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n        self.assertEqual(add(2, 2), 4)\n')
JS_TEST = 'import { add } from "./add";\ntest("add", () => {\n  expect(add(1, 2)).toBe(3);\n  expect(add(2, 2)).toBe(4);\n});\n'
TC_BASE = {'src/calc.py': CALC, 'tests/test_calc.py': CALC_TEST, 'web/add.test.ts': JS_TEST, 'docs/guide.md': 'guide\n'}


class TestChangesTest(BuiltinCase):
    def tc(self, change=None, base=None, **kw):
        return self.scan(builtins.test_changes, base or TC_BASE, change, **kw)

    def moved_scan(self, *git_args, edit=None):
        repo = self.repo(TC_BASE)
        repo.branch()
        git(repo.root, 'mv', *git_args)
        if edit:
            repo.write(edit)
        return self.scan_repo(repo, builtins.test_changes)

    def test_deleted_tests_in_any_language_are_hard(self):
        base = {**TC_BASE, 'tests/a_test.gleam': 'pub fn a_test() { 1 }\n', 'tests/t.bqn': 'x\n'}
        scan = self.tc({'tests/a_test.gleam': None, 'tests/t.bqn': None}, base=base, policy={'languages': {'.bqn': 'bqn'}})
        self.assertEqual(sorted(i.key for i in scan.hard), ['tests/a_test.gleam', 'tests/t.bqn'])

    def test_deleted_test_file_is_hard(self):
        scan = self.tc({'tests/test_calc.py': None})
        self.assertEqual([(i.rule, i.key, i.path, i.mode) for i in scan.hard],
                         [('test-file-deleted', 'tests/test_calc.py', 'tests/test_calc.py', 'hard')])

    def test_deleting_js_test_file_is_hard_and_deleting_source_is_not(self):
        self.assertEqual(keys(self.tc({'web/add.test.ts': None}).hard), ['web/add.test.ts'])
        self.assertEqual(self.tc({'src/calc.py': None}).hard, [])

    def test_deleting_non_code_or_excluded_test_files_is_ignored(self):
        base = {**TC_BASE, 'tests/data.json': '{}\n', 'legacy/tests/test_old.py': 'assert 1\n'}
        scan = self.tc({'tests/data.json': None, 'legacy/tests/test_old.py': None}, base=base,
                       policy={'exclude': ['legacy/**']})
        self.assertEqual(scan.hard, [])

    def test_git_mv_of_a_test_file_is_not_a_deletion(self):
        scan = self.moved_scan('tests/test_calc.py', 'tests/test_calc_renamed.py')
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_git_mv_to_another_test_directory_is_not_a_deletion(self):
        repo = self.repo(TC_BASE)
        repo.branch()
        os.makedirs(os.path.join(repo.root, 'tests', 'unit'))
        git(repo.root, 'mv', 'tests/test_calc.py', 'tests/unit/test_calc.py')
        scan = self.scan_repo(repo, builtins.test_changes)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_renamed_and_lightly_edited_test_file_is_not_a_deletion(self):
        edit = {'tests/test_calc_renamed.py': CALC_TEST + '        self.assertEqual(add(0, 0), 0)\n'}
        scan = self.moved_scan('tests/test_calc.py', 'tests/test_calc_renamed.py', edit=edit)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_renamed_test_file_that_lost_assertions_is_still_judged(self):
        edit = {'tests/test_calc_renamed.py': CALC_TEST.replace('        self.assertEqual(add(2, 2), 4)\n', '')}
        scan = self.moved_scan('tests/test_calc.py', 'tests/test_calc_renamed.py', edit=edit)
        self.assertEqual(scan.hard, [])
        self.assertEqual(rules(scan.advisory), ['assertions-reduced'])
        self.assertEqual(keys(scan.advisory), ['tests/test_calc_renamed.py'])

    def test_plain_mv_without_git_add_is_a_rename_too(self):
        repo = self.repo(TC_BASE)
        repo.branch()
        os.rename(os.path.join(repo.root, 'tests/test_calc.py'), os.path.join(repo.root, 'tests/test_calc2.py'))
        scan = self.scan_repo(repo, builtins.test_changes)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_test_file_moved_out_of_test_paths_is_reported(self):
        scan = self.moved_scan('tests/test_calc.py', 'src/calc_checks.py')
        self.assertTrue(scan.hard or scan.advisory)

    def test_removing_assertions_is_advisory(self):
        scan = self.tc({'tests/test_calc.py': CALC_TEST.replace('        self.assertEqual(add(2, 2), 4)\n', '')})
        (item,) = scan.advisory
        self.assertEqual((item.rule, item.key, item.mode), ('assertions-reduced', 'tests/test_calc.py', 'advisory'))
        self.assertIn('1 assertion lines removed, 0 added', item.message)
        self.assertEqual(scan.hard, [])

    def test_removing_js_expectations_is_advisory(self):
        scan = self.tc({'web/add.test.ts': JS_TEST.replace('  expect(add(2, 2)).toBe(4);\n', '')})
        self.assertEqual(keys(scan.advisory), ['web/add.test.ts'])

    def test_assertions_moved_or_reordered_without_loss_are_clean(self):
        reordered = CALC_TEST.replace('        self.assertEqual(add(1, 2), 3)\n        self.assertEqual(add(2, 2), 4)\n',
                                      '        self.assertEqual(add(2, 2), 4)\n        self.assertEqual(add(1, 2), 3)\n')
        scan = self.tc({'tests/test_calc.py': reordered})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_assertion_moved_into_a_new_test_function_without_loss_is_clean(self):
        split = ('import unittest\nfrom src.calc import add\n\n\nclass T(unittest.TestCase):\n'
                 '    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n\n'
                 '    def test_add_again(self):\n        self.assertEqual(add(2, 2), 4)\n')
        scan = self.tc({'tests/test_calc.py': split})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_assertion_rewritten_in_another_style_keeps_the_count(self):
        scan = self.tc({'tests/test_calc.py': CALC_TEST.replace('self.assertEqual(add(2, 2), 4)', 'assert add(2, 2) == 4')})
        self.assertEqual([i for i in scan.advisory if i.rule == 'assertions-reduced'], [])

    def test_removing_non_assertion_lines_is_clean(self):
        scan = self.tc({'tests/test_calc.py': CALC_TEST.replace('import unittest\n', 'import unittest  # noqa\n')
                        .replace('\n\n\nclass', '\n\nclass')})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_adding_assertions_is_clean(self):
        scan = self.tc({'tests/test_calc.py': CALC_TEST + '        self.assertEqual(add(0, 0), 0)\n'})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_changed_expectation_next_to_a_source_change_is_flagged(self):
        scan = self.tc({'src/calc.py': 'def add(a, b):\n    return a + b + 1\n',
                        'tests/test_calc.py': CALC_TEST.replace('add(2, 2), 4)', 'add(2, 2), 5)')})
        (item,) = [i for i in scan.advisory if i.rule == 'expectation-changed']
        self.assertEqual((item.path, item.line), ('tests/test_calc.py', 8))
        self.assertIn('add(2, 2), 4', item.message)
        self.assertIn('add(2, 2), 5', item.message)
        self.assertEqual(scan.hard, [])

    def test_changed_expectation_without_a_source_change_is_not_flagged(self):
        scan = self.tc({'tests/test_calc.py': CALC_TEST.replace('add(2, 2), 4)', 'add(2, 2), 5)')})
        self.assertEqual([i for i in scan.advisory if i.rule == 'expectation-changed'], [])

    def test_changed_literal_in_js_expectation_is_flagged(self):
        scan = self.tc({'src/calc.py': 'def add(a, b):\n    return a - b\n',
                        'web/add.test.ts': JS_TEST.replace('.toBe(4)', '.toBe(0)')})
        self.assertEqual([i.rule for i in scan.advisory], ['expectation-changed'])

    def test_untested_source_threshold_boundary(self):
        def lines(n):
            return {'src/big.py': ''.join(f'v{i} = {i}\n' for i in range(n))}
        self.assertEqual(self.tc(lines(29)).advisory, [])
        scan = self.tc(lines(30))
        (item,) = scan.advisory
        self.assertEqual((item.rule, item.key), ('no-test-change', 'changeset'))
        self.assertIn('30 source lines', item.message)

    def test_untested_source_threshold_is_configurable(self):
        guard = {'min': {'untested_lines': 5}}
        change = {'src/big.py': ''.join(f'v{i} = {i}\n' for i in range(5))}
        self.assertEqual(rules(self.tc(change, guard=guard).advisory), ['no-test-change'])
        change = {'src/big.py': ''.join(f'v{i} = {i}\n' for i in range(4))}
        self.assertEqual(self.tc(change, guard=guard).advisory, [])

    def test_touching_any_test_silences_the_untested_source_note(self):
        change = {'src/big.py': ''.join(f'v{i} = {i}\n' for i in range(40)),
                  'tests/test_new.py': 'def test_x():\n    assert True\n'}
        self.assertEqual(self.tc(change).advisory, [])

    def test_docs_scripts_and_deleted_source_do_not_count_as_untested_source(self):
        change = {'docs/guide.md': 'x\n' * 100, 'scripts/tool.py': 'x = 1\n' * 100, 'src/calc.py': None,
                  'data/rows.json': '[]\n' * 100}
        self.assertEqual(self.tc(change).advisory, [])

    def test_coverage_counts_changed_files(self):
        scan = self.tc({'src/calc.py': CALC + '\n', 'docs/guide.md': 'guide v2\n'})
        self.assertEqual(scan.coverage, {'scanned': 2, 'unit': 'changed files'})


# ─── migrations ──────────────────────────────────────────────────────────────
MIG_BASE = {
    'db/migrations/0001_init.sql': 'CREATE TABLE users (id INT PRIMARY KEY);\n',
    'db/migrations/0002_orders.sql': 'CREATE TABLE orders (id INT);\n',
    'app/models.py': 'class User: pass\n',
}


class MigrationsTest(BuiltinCase):
    def mig(self, change=None, base=None, **kw):
        return self.scan(builtins.migrations, base or MIG_BASE, change, **kw)

    def test_editing_a_migration_that_is_on_base_is_hard(self):
        scan = self.mig({'db/migrations/0001_init.sql': 'CREATE TABLE users (id INT PRIMARY KEY, name TEXT);\n'})
        self.assertEqual([(i.rule, i.key, i.path, i.mode) for i in scan.hard],
                         [('migration-edited', 'db/migrations/0001_init.sql', 'db/migrations/0001_init.sql', 'hard')])

    def test_deleting_a_migration_that_is_on_base_is_hard(self):
        scan = self.mig({'db/migrations/0002_orders.sql': None})
        self.assertEqual([(i.rule, i.key) for i in scan.hard], [('migration-deleted', 'db/migrations/0002_orders.sql')])

    def test_renaming_a_migration_that_is_on_base_is_hard(self):
        repo = self.repo(MIG_BASE)
        repo.branch()
        git(repo.root, 'mv', 'db/migrations/0002_orders.sql', 'db/migrations/0003_orders.sql')
        scan = self.scan_repo(repo, builtins.migrations)
        (item,) = scan.hard
        self.assertEqual((item.rule, item.key, item.path), ('migration-renamed', 'db/migrations/0002_orders.sql',
                                                           'db/migrations/0003_orders.sql'))

    def test_renaming_out_of_the_migrations_directory_is_still_a_rename(self):
        repo = self.repo(MIG_BASE)
        repo.branch()
        git(repo.root, 'mv', 'db/migrations/0002_orders.sql', 'db/archive_orders.sql')
        scan = self.scan_repo(repo, builtins.migrations)
        self.assertEqual([(i.rule, i.key) for i in scan.hard], [('migration-renamed', 'db/migrations/0002_orders.sql')])

    def test_plain_mv_of_a_migration_is_a_rename(self):
        repo = self.repo(MIG_BASE)
        repo.branch()
        os.rename(os.path.join(repo.root, 'db/migrations/0002_orders.sql'),
                  os.path.join(repo.root, 'db/migrations/0003_orders.sql'))
        scan = self.scan_repo(repo, builtins.migrations)
        self.assertEqual([i.rule for i in scan.hard], ['migration-renamed'])

    def test_renamed_and_edited_migration_is_renamed_with_destructive_evidence(self):
        repo = self.repo(MIG_BASE)
        repo.branch()
        git(repo.root, 'mv', 'db/migrations/0002_orders.sql', 'db/migrations/0003_orders.sql')
        repo.write({'db/migrations/0003_orders.sql': 'CREATE TABLE orders (id INT);\nDROP TABLE legacy;\n'})
        scan = self.scan_repo(repo, builtins.migrations)
        self.assertEqual([i.rule for i in scan.hard], ['migration-renamed'])
        self.assertEqual(rules(scan.advisory), ['destructive-drop-table'])

    def test_a_new_migration_is_not_hard(self):
        scan = self.mig({'db/migrations/0003_add_col.sql': 'ALTER TABLE users ADD COLUMN age INT;\n'})
        self.assertEqual((scan.hard, scan.advisory), ([], []))
        self.assertEqual(scan.coverage, {'scanned': 1, 'unit': 'migration files changed'})

    def test_migration_added_in_this_branch_and_edited_again_is_not_edited(self):
        history = [{'db/migrations/0003_add_col.sql': 'ALTER TABLE users ADD COLUMN age INT;\n'}]
        scan = self.mig({'db/migrations/0003_add_col.sql': 'ALTER TABLE users ADD COLUMN age BIGINT;\n'}, history=history)
        self.assertEqual(scan.hard, [])

    def test_migration_added_in_this_branch_then_deleted_or_renamed_is_clean(self):
        history = [{'db/migrations/0003_add_col.sql': 'ALTER TABLE users ADD COLUMN age INT;\n'}]
        self.assertEqual(self.mig({'db/migrations/0003_add_col.sql': None}, history=history).hard, [])
        repo = self.repo(MIG_BASE)
        repo.branch()
        repo.write(history[0])
        repo.commit('add')
        git(repo.root, 'mv', 'db/migrations/0003_add_col.sql', 'db/migrations/0004_add_col.sql')
        self.assertEqual(self.scan_repo(repo, builtins.migrations).hard, [])

    def test_untracked_new_migration_is_not_hard(self):
        scan = self.mig({'db/migrations/0009_new.sql': 'SELECT 1;\n'})
        self.assertEqual(scan.hard, [])

    def test_destructive_statements_are_advisory_evidence(self):
        cases = {
            'drop-table': 'DROP TABLE users;',
            'drop-column': 'ALTER TABLE users DROP COLUMN name;',
            'truncate': 'TRUNCATE TABLE users;',
            'delete-all': 'DELETE FROM users;',
            'rename': 'ALTER TABLE users RENAME COLUMN name TO full_name;',
            'type-change': 'ALTER TABLE users ALTER COLUMN age TYPE BIGINT;',
            'not-null-without-default': 'ALTER TABLE users ADD COLUMN age INT NOT NULL;',
        }
        for name, sql in cases.items():
            with self.subTest(name):
                scan = self.mig({'db/migrations/0003_x.sql': f'-- header\n{sql}\n'})
                (item,) = scan.advisory
                self.assertEqual((item.rule, item.key, item.path, item.line, item.mode),
                                 (f'destructive-{name}', f'db/migrations/0003_x.sql#{name}', 'db/migrations/0003_x.sql', 2,
                                  'advisory'))
                self.assertEqual(scan.hard, [])

    def test_destructive_operations_in_orm_migrations(self):
        py = ('def upgrade():\n    op.drop_column("users", "name")\n    op.drop_table("old")\n'
              '    op.alter_column("t", "c", type_=sa.Text())\n')
        scan = self.mig({'alembic/versions/abc123_x.py': py})
        self.assertEqual(sorted(rules(scan.advisory)),
                         ['destructive-drop-column', 'destructive-drop-table', 'destructive-type-change'])

    def test_safe_statements_are_not_flagged(self):
        sql = 'CREATE TABLE t (id INT);\nALTER TABLE users ADD COLUMN age INT;\nALTER TABLE users ADD COLUMN age INT NOT NULL DEFAULT 0;\nDELETE FROM users WHERE id = 1;\nCREATE INDEX idx ON users (name);\nINSERT INTO users VALUES (1);' + '\n'
        scan = self.mig({'db/migrations/0003_safe.sql': sql})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_default_before_not_null_is_not_flagged(self):
        scan = self.mig({'db/migrations/0003_x.sql': 'ALTER TABLE users ADD COLUMN age INT DEFAULT 0 NOT NULL;\n'})
        self.assertEqual(scan.advisory, [])

    def test_destructive_text_in_removed_lines_is_not_evidence(self):
        base = {**MIG_BASE, 'db/migrations/0004_x.sql': 'DROP TABLE legacy;\nSELECT 1;\n'}
        scan = self.mig({'db/migrations/0004_x.sql': 'SELECT 1;\n'}, base=base)
        self.assertEqual(rules(scan.hard), ['migration-edited'])
        self.assertEqual(scan.advisory, [])

    def test_destructive_text_in_a_deleted_migration_is_not_evidence(self):
        base = {**MIG_BASE, 'db/migrations/0004_x.sql': 'DROP TABLE legacy;\n'}
        scan = self.mig({'db/migrations/0004_x.sql': None}, base=base)
        self.assertEqual(scan.advisory, [])

    def test_editing_a_base_migration_with_new_destructive_sql_gives_both(self):
        scan = self.mig({'db/migrations/0001_init.sql': 'CREATE TABLE users (id INT PRIMARY KEY);\nDROP TABLE x;\n'})
        self.assertEqual(rules(scan.hard), ['migration-edited'])
        self.assertEqual(rules(scan.advisory), ['destructive-drop-table'])

    def test_non_migration_files_and_migration_housekeeping_files_are_ignored(self):
        base = {**MIG_BASE, 'db/migrations/README.md': 'notes\n', 'app/migrations/__init__.py': '',
                'app/migrations/.gitkeep': '', 'db/migrations/notes.txt': 'n\n'}
        change = {'db/migrations/README.md': 'notes 2\nDROP TABLE x\n', 'app/migrations/__init__.py': '# x\n',
                  'app/migrations/.gitkeep': 'x\n', 'db/migrations/notes.txt': 'DROP TABLE x\n',
                  'app/models.py': 'class User:\n    pass\n'}
        scan = self.mig(change, base=base)
        self.assertEqual((scan.hard, scan.advisory, scan.coverage['scanned']), ([], [], 0))

    def test_default_migration_locations(self):
        for path in ('migrations/0001.sql', 'app/migrations/0001_initial.py', 'prisma/migrations/2024_x/migration.sql',
                     'db/migrate/20240101_add.rb', 'alembic/versions/abc_x.py', 'db/changelog/001.xml'):
            with self.subTest(path):
                scan = self.mig({path: 'x = 1\n'}, base={path: 'x = 0\n'})
                self.assertEqual(rules(scan.hard), ['migration-edited'])

    def test_project_declared_migration_paths_and_roles(self):
        base = {'schema/changes/001.sql': 'a\n', 'ops/db/002.sql': 'a\n'}
        scan = self.mig({'schema/changes/001.sql': 'b\n', 'ops/db/002.sql': 'b\n'}, base=base,
                        policy={'paths': {'migration': ['schema/changes/**']}, 'roles': {'migration': ['ops/db/**']}})
        self.assertEqual(sorted(keys(scan.hard)), ['ops/db/002.sql', 'schema/changes/001.sql'])

    def test_excluded_migration_paths_are_not_judged(self):
        base = {'db/migrations/legacy/001.sql': 'a\n'}
        scan = self.mig({'db/migrations/legacy/001.sql': 'b\n'}, base=base, policy={'exclude': ['db/migrations/legacy/**']})
        self.assertEqual(scan.hard, [])


# ─── generated ───────────────────────────────────────────────────────────────
GEN_BASE = {'gen/out.txt': 'v1\n', 'src/a.py': 'a = 1\n'}


class GeneratedTest(BuiltinCase):
    def gen(self, run, outputs=('gen/*.txt',), base=None, repo=None, **extra):
        guard = {'run': run, 'outputs': list(outputs), **extra}
        if repo is not None:
            return self.scan_repo(repo, builtins.generated, guard=guard)
        return self.scan(builtins.generated, base or GEN_BASE, guard=guard)

    def test_up_to_date_output_is_clean(self):
        scan = self.gen("printf 'v1\\n' > gen/out.txt")
        self.assertEqual((scan.hard, scan.integrity), ([], []))
        self.assertEqual(scan.coverage, {'scanned': 1, 'unit': 'generated files'})

    def test_stale_output_is_hard_and_the_regenerated_file_stays_in_place(self):
        repo = self.repo(GEN_BASE)
        repo.branch()
        scan = self.gen("printf 'v2\\n' > gen/out.txt", repo=repo)
        self.assertEqual([(i.rule, i.key, i.path, i.mode) for i in scan.hard],
                         [('generated-drift', 'gen/out.txt', 'gen/out.txt', 'hard')])
        self.assertIn('stale', scan.hard[0].message)
        self.assertEqual(repo.read('gen/out.txt'), 'v2\n')

    def test_hand_edited_generated_file_is_overwritten_and_reported(self):
        repo = self.repo(GEN_BASE)
        repo.branch()
        repo.write({'gen/out.txt': 'hand edit\n'})
        scan = self.gen("printf 'v1\\n' > gen/out.txt", repo=repo)
        self.assertEqual(keys(scan.hard), ['gen/out.txt'])

    def test_new_generated_file_missing_from_the_commit(self):
        scan = self.gen("printf 'v1\\n' > gen/out.txt; printf 'n\\n' > gen/new.txt")
        self.assertEqual(keys(scan.hard), ['gen/new.txt'])
        self.assertIn('missing from the commit', scan.hard[0].message)

    def test_file_the_generator_no_longer_produces(self):
        scan = self.gen("rm gen/out.txt; printf 'n\\n' > gen/other.txt")
        self.assertEqual(sorted((i.key, 'no longer generated' in i.message) for i in scan.hard),
                         [('gen/other.txt', False), ('gen/out.txt', True)])

    def test_generator_that_empties_the_output_set_is_drift_and_integrity(self):
        scan = self.gen('rm gen/out.txt')
        self.assertEqual(keys(scan.hard), ['gen/out.txt'])
        self.assertTrue(any('no files match outputs' in p for p in scan.integrity), scan.integrity)

    def test_failing_generator_is_integrity_with_its_output(self):
        scan = self.gen("echo generator exploded >&2; exit 3")
        self.assertEqual(scan.hard, [])
        self.assertEqual(len(scan.integrity), 1)
        self.assertIn('exited 3', scan.integrity[0])
        self.assertIn('generator exploded', scan.integrity[0])

    def test_generator_that_times_out_is_integrity(self):
        scan = self.gen('sleep 5', timeout=1)
        self.assertTrue(any('exited 124' in p and 'timed out' in p for p in scan.integrity), scan.integrity)

    def test_missing_outputs_option_is_integrity(self):
        for extra in ({'outputs': []}, {}):
            scan = self.scan(builtins.generated, GEN_BASE, guard={'run': 'true', **extra})
            self.assertTrue(any('needs `outputs`' in p for p in scan.integrity), extra)

    def test_outputs_that_match_nothing_are_integrity(self):
        scan = self.gen('true', outputs=['nothing/**'])
        self.assertTrue(any('no files match outputs' in p for p in scan.integrity), scan.integrity)

    def test_recursive_output_globs(self):
        base = {'gen/a/x.txt': '1\n', 'gen/b/c/y.txt': '2\n', 'other/z.txt': '3\n'}
        scan = self.gen("printf '1\\n' > gen/a/x.txt; printf '2\\n' > gen/b/c/y.txt; printf 'changed\\n' > other/z.txt",
                        outputs=['gen/**'], base=base)
        self.assertEqual((scan.hard, scan.integrity, scan.coverage['scanned']), ([], [], 2))

    def test_generator_runs_in_the_project_root(self):
        scan = self.gen("test -f src/a.py && printf 'v1\\n' > gen/out.txt")
        self.assertEqual((scan.hard, scan.integrity), ([], []))


# ─── deps ────────────────────────────────────────────────────────────────────
def pkg(**sections) -> str:
    return json.dumps({'name': 'x', 'version': '1.0.0', **sections}, indent=2) + '\n'


def npm_lock(packages: dict) -> str:
    return json.dumps({'name': 'x', 'lockfileVersion': 3, 'packages': {'': {'name': 'x'}, **packages}}, indent=2) + '\n'


def lock_entry(name='lodash', version='4.17.21', resolved=None, integrity='sha512-abc', **extra) -> dict:
    resolved = resolved if resolved is not None else f'https://registry.npmjs.org/{name}/-/{name}-{version}.tgz'
    meta = {'version': version, 'resolved': resolved, **extra}
    if integrity:
        meta['integrity'] = integrity
    return meta


NPM_BASE = {'package.json': pkg(dependencies={'left-pad': '^1.0.0'})}
BAD_NPM_SPECS = ['git+https://github.com/o/r.git', 'github:o/r', 'o/r', 'o/r#v1', 'https://pkgs.test/p.tgz', 'file:../p',
                 'link:../p', 'git://pkgs.test/y.git', 'ssh://git@pkgs.test/r.git']
OK_NPM_SPECS = ['^4.17.21', '~1.0.0', '1.2.3', '1.x', '>=1.0.0 <2', '^1 || ^2', 'workspace:*', 'workspace:^1.0.0',
                'catalog:', '1.0.0 - 2.0.0']


class DepsTest(BuiltinCase):
    def deps(self, change=None, base=None, guard=None, **kw):
        return self.scan(deps.check, base if base is not None else {'README.md': 'x\n'}, change, guard=guard, **kw)

    def hard(self, scan):
        return [(i.rule, i.key) for i in scan.hard]

    def note(self, scan):
        return [(i.rule, i.key) for i in scan.advisory]


class NpmManifestTest(DepsTest):
    def test_added_registry_dependency_is_advisory_only(self):
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0', 'lodash': '^4.17.21'})}, NPM_BASE)
        self.assertEqual(self.hard(scan), [])
        self.assertEqual(self.note(scan), [('dep-added', 'package.json#lodash')])
        self.assertEqual(scan.coverage, {'scanned': 1, 'unit': 'manifests and lockfiles changed'})

    def test_non_registry_sources_are_hard(self):
        for spec in BAD_NPM_SPECS:
            with self.subTest(spec):
                scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0', 'thing': spec})}, NPM_BASE)
                self.assertEqual(self.hard(scan), [('dep-source', 'package.json#thing')])

    def test_registry_specs_and_workspace_protocols_are_not_hard(self):
        for spec in OK_NPM_SPECS:
            with self.subTest(spec):
                scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0', 'thing': spec})}, NPM_BASE)
                self.assertEqual(self.hard(scan), [])

    def test_workspace_dependency_is_not_even_an_advisory_problem_besides_added(self):
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0', 'core': 'workspace:*'})}, NPM_BASE)
        self.assertEqual(self.note(scan), [('dep-added', 'package.json#core')])

    def test_wildcard_specs_are_hard(self):
        for spec in ('*', 'latest', '', 'x', 'next'):
            with self.subTest(repr(spec)):
                scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0', 'thing': spec})}, NPM_BASE)
                self.assertEqual(self.hard(scan), [('dep-unpinned', 'package.json#thing')])

    def test_open_ended_ranges_and_aliases_are_advisory(self):
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0', 'open': '>=1.0.0', 'other': 'npm:real@^1.0.0'})},
                         NPM_BASE)
        self.assertEqual(self.hard(scan), [])
        self.assertEqual(sorted(self.note(scan)), sorted([
            ('dep-open-range', 'package.json#open'), ('dep-added', 'package.json#open'),
            ('dep-alias', 'package.json#other'), ('dep-added', 'package.json#other')]))

    def test_peer_dependency_open_range_is_fine(self):
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0'}, peerDependencies={'react': '>=17'})}, NPM_BASE)
        self.assertEqual([r for r, _ in self.note(scan) if r == 'dep-open-range'], [])

    def test_peer_dependency_wildcard_is_not_hard(self):
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0'}, peerDependencies={'react': '*'})}, NPM_BASE)
        self.assertEqual(self.hard(scan), [])

    def test_overrides_and_resolutions_are_checked(self):
        doc = json.loads(pkg(dependencies={'left-pad': '^1.0.0'}))
        doc['overrides'] = {'lodash': '4.17.21', 'react': {'scheduler': 'github:o/scheduler'}}
        doc['resolutions'] = {'minimist': '*'}
        scan = self.deps({'package.json': json.dumps(doc)}, NPM_BASE)
        self.assertEqual(sorted(self.hard(scan)), [('dep-source', 'package.json#react>scheduler'),
                                                   ('dep-unpinned', 'package.json#minimist')])
        self.assertIn(('dep-override', 'package.json#lodash'), self.note(scan))

    def test_every_dependency_section_is_checked(self):
        for section in ('dependencies', 'devDependencies', 'optionalDependencies'):
            with self.subTest(section):
                scan = self.deps({'package.json': pkg(**{section: {'thing': 'github:o/r'}})}, {'package.json': pkg()})
                self.assertEqual(self.hard(scan), [('dep-source', 'package.json#thing')])

    def test_changing_an_existing_spec_to_a_bad_one_is_hard(self):
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': 'github:o/left-pad'})}, NPM_BASE)
        self.assertEqual(self.hard(scan), [('dep-source', 'package.json#left-pad')])
        self.assertEqual(self.note(scan), [])

    def test_pre_existing_bad_dependency_is_not_reported_again(self):
        base = {'package.json': pkg(dependencies={'old': 'github:o/old', 'star': '*'})}
        scan = self.deps({'package.json': pkg(dependencies={'old': 'github:o/old', 'star': '*', 'lodash': '^4.0.0'})}, base)
        self.assertEqual(self.hard(scan), [])

    def test_untracked_new_manifest_is_judged_in_full(self):
        scan = self.deps({'tools/package.json': pkg(dependencies={'thing': 'github:o/r'})})
        self.assertEqual(self.hard(scan), [('dep-source', 'tools/package.json#thing')])

    def test_non_dependency_manifest_edits_are_ignored(self):
        base = {'package.json': pkg(dependencies={'left-pad': '^1.0.0'}, scripts={'test': 'jest'}),
                'package-lock.json': npm_lock({})}
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0'}, scripts={'test': 'vitest'})}, base)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_invalid_json_manifest_is_integrity(self):
        scan = self.deps({'package.json': '{"dependencies": {'}, NPM_BASE)
        self.assertTrue(any('package.json is not valid JSON' in p for p in scan.integrity), scan.integrity)

    def test_keys_have_no_line_numbers(self):
        deps_ = {f'pkg{i}': 'github:o/r' for i in range(5)}
        scan = self.deps({'package.json': pkg(dependencies=deps_)}, {'package.json': pkg()})
        for item in scan.hard + scan.advisory:
            self.assertRegex(item.key, r'^package\.json#pkg\d$')

    def test_renamed_requirements_file_without_content_change_adds_nothing(self):
        repo = self.repo({'requirements.txt': 'requests==2.31.0\n-e .\n'})
        repo.branch()
        os.makedirs(os.path.join(repo.root, 'requirements'))
        git(repo.root, 'mv', 'requirements.txt', 'requirements/base.txt')
        scan = self.scan_repo(repo, deps.check)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_excluded_manifests_are_not_judged(self):
        scan = self.deps({'third_party/lib/package.json': pkg(dependencies={'x': 'github:o/r'})},
                         policy={'exclude': ['third_party/**']})
        self.assertEqual(scan.hard, [])


class LockfileSyncTest(DepsTest):
    LOCKED: ClassVar[dict] = {'package.json': pkg(dependencies={'left-pad': '^1.0.0'}), 'package-lock.json': npm_lock({})}

    def test_manifest_dependencies_changed_without_the_lockfile_is_hard(self):
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0', 'lodash': '^4.0.0'})}, self.LOCKED)
        (item,) = [i for i in scan.hard if i.rule == 'lockfile-stale']
        self.assertEqual((item.key, item.path), ('package-lock.json', 'package.json'))

    def test_lockfile_updated_together_is_fine(self):
        scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^1.0.0', 'lodash': '^4.0.0'}),
                          'package-lock.json': npm_lock({'node_modules/lodash': lock_entry()})}, self.LOCKED)
        self.assertEqual(scan.hard, [])

    def test_removing_a_dependency_without_the_lockfile_is_hard(self):
        scan = self.deps({'package.json': pkg()}, self.LOCKED)
        self.assertEqual(self.hard(scan), [('lockfile-stale', 'package-lock.json')])

    def test_no_lockfile_means_nothing_to_sync(self):
        scan = self.deps({'package.json': pkg(dependencies={'a': '^1.0.0', 'b': '^1.0.0'})}, NPM_BASE)
        self.assertEqual(self.hard(scan), [])

    def test_other_package_managers_lockfiles(self):
        for lock in ('yarn.lock', 'pnpm-lock.yaml', 'npm-shrinkwrap.json', 'bun.lock'):
            with self.subTest(lock):
                base = {'package.json': pkg(dependencies={'left-pad': '^1.0.0'}), lock: '# lock\n'}
                scan = self.deps({'package.json': pkg(dependencies={'left-pad': '^2.0.0'})}, base)
                self.assertEqual(self.hard(scan), [('lockfile-stale', lock)])

    def test_nested_package_uses_its_own_sibling_lockfile(self):
        base = {'packages/a/package.json': pkg(), 'packages/a/package-lock.json': npm_lock({}),
                'package-lock.json': npm_lock({}), 'package.json': pkg()}
        scan = self.deps({'packages/a/package.json': pkg(dependencies={'x': '^1.0.0'})}, base)
        self.assertEqual(self.hard(scan), [('lockfile-stale', 'packages/a/package-lock.json')])

    def test_lockfile_removed_while_manifest_remains_is_hard(self):
        scan = self.deps({'package-lock.json': None}, self.LOCKED)
        self.assertEqual(self.hard(scan), [('lockfile-removed', 'package-lock.json')])

    def test_lockfile_and_manifest_removed_together_is_fine(self):
        scan = self.deps({'package-lock.json': None, 'package.json': None}, self.LOCKED)
        self.assertEqual(scan.hard, [])

    def test_lockfile_removed_for_other_ecosystems(self):
        for manifest, lock in (('go.mod', 'go.sum'), ('Cargo.toml', 'Cargo.lock'), ('Gemfile', 'Gemfile.lock'),
                               ('pyproject.toml', 'uv.lock'), ('composer.json', 'composer.lock')):
            with self.subTest(lock):
                scan = self.deps({lock: None}, {manifest: 'x\n', lock: 'x\n'})
                self.assertEqual(self.hard(scan), [('lockfile-removed', lock)])


class NpmLockTest(DepsTest):
    BASE: ClassVar[dict] = {'package.json': pkg(dependencies={'lodash': '^4.0.0'}), 'package-lock.json': npm_lock({'node_modules/lodash': lock_entry()})}

    def lock(self, packages, base=None, guard=None):
        merged = {'node_modules/lodash': lock_entry(), **packages}
        return self.deps({'package-lock.json': npm_lock(merged)}, base or self.BASE, guard=guard)

    def test_registry_resolution_is_fine(self):
        scan = self.lock({'node_modules/chalk': lock_entry('chalk', '5.0.0')})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_resolution_outside_the_allowed_registries_is_hard(self):
        for resolved in ('https://evil.example.net/x/-/x-1.0.0.tgz', 'git+ssh://git@github.com/o/x.git',
                         'file:../x', 'http://evil.example.net/x.tgz', 'https://registry.npmjs.org@evil.example.net/x.tgz',
                         'https://registry.npmjs.org.evil.example.net/x.tgz'):
            with self.subTest(resolved):
                scan = self.lock({'node_modules/x': lock_entry('x', resolved=resolved)})
                self.assertEqual(self.hard(scan), [('lock-registry', 'package-lock.json#x')])

    def test_extra_registries_are_configurable_and_subdomains_allowed(self):
        entry = lock_entry('x', resolved='https://npm.pkgs.internal.test/x/-/x-1.0.0.tgz')
        self.assertEqual(self.lock({'node_modules/x': entry}).hard[0].rule, 'lock-registry')
        scan = self.lock({'node_modules/x': entry}, guard={'registries': ['pkgs.internal.test']})
        self.assertEqual(scan.hard, [])

    def test_unchanged_lock_entries_are_not_rejudged(self):
        bad = lock_entry('x', resolved='https://evil.example.net/x-1.0.0.tgz')
        base = {**self.BASE, 'package-lock.json': npm_lock({'node_modules/x': bad})}
        scan = self.deps({'package-lock.json': npm_lock({'node_modules/x': bad, 'node_modules/y': lock_entry('y')})}, base)
        self.assertEqual(scan.hard, [])

    def test_version_bump_to_a_bad_host_is_judged(self):
        ok = lock_entry('x', '1.0.0')
        base = {'package-lock.json': npm_lock({'node_modules/x': ok})}
        bad = lock_entry('x', '1.0.1', resolved='https://evil.example.net/x-1.0.1.tgz')
        scan = self.deps({'package-lock.json': npm_lock({'node_modules/x': bad})}, base)
        self.assertEqual(self.hard(scan), [('lock-registry', 'package-lock.json#x')])

    def test_nested_package_names_use_the_innermost_name(self):
        scan = self.lock({'node_modules/a/node_modules/deep': lock_entry('deep', resolved='https://evil.example.net/d.tgz')})
        self.assertEqual(self.hard(scan), [('lock-registry', 'package-lock.json#deep')])

    def test_links_and_entries_without_resolution_are_ignored(self):
        scan = self.lock({'node_modules/local': {'resolved': 'packages/local', 'link': True},
                          'packages/local': {'version': '1.0.0'}})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_missing_integrity_and_install_scripts_are_advisory(self):
        scan = self.lock({'node_modules/a': lock_entry('a', integrity=None),
                          'node_modules/b': lock_entry('b', hasInstallScript=True)})
        self.assertEqual(scan.hard, [])
        self.assertEqual(sorted(self.note(scan)), [('install-script', 'package-lock.json#b'),
                                                    ('lock-integrity-missing', 'package-lock.json#a')])

    def test_install_script_of_an_existing_package_is_not_new(self):
        base = {'package-lock.json': npm_lock({'node_modules/b': lock_entry('b', hasInstallScript=True)})}
        scan = self.deps({'package-lock.json': npm_lock({'node_modules/b': lock_entry('b', '1.0.1', hasInstallScript=True)})}, base)
        self.assertEqual(scan.advisory, [])

    def test_invalid_lockfile_is_integrity(self):
        for text in ('{"packages": ', '[]'):
            scan = self.deps({'package-lock.json': text}, self.BASE)
            self.assertTrue(any('package-lock.json is not a valid npm lockfile' in p for p in scan.integrity), text)

    def test_yarn_lock_new_resolutions(self):
        base = {'yarn.lock': '# yarn lockfile v1\n'}
        good = '  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz#abc"\n'
        bad = '  resolved "https://evil.example.net/x/-/x-1.0.0.tgz#abc"\n'
        git_dep = '  resolved "git+ssh://git@github.com/o/r.git#abc"\n'
        self.assertEqual(self.deps({'yarn.lock': '# yarn lockfile v1\n' + good}, base).hard, [])
        scan = self.deps({'yarn.lock': '# yarn lockfile v1\n' + good + bad + git_dep}, base)
        self.assertEqual([i.rule for i in scan.hard], ['lock-registry', 'lock-registry'])
        self.assertTrue(all(i.key.startswith('yarn.lock#') and '\n' not in i.key for i in scan.hard))

    def test_pnpm_lock_tarballs(self):
        base = {'pnpm-lock.yaml': 'lockfileVersion: 9\n'}
        good = "    resolution: {integrity: sha512-abc, tarball: https://registry.npmjs.org/x/-/x-1.0.0.tgz}\n"
        bad = "    resolution: {tarball: https://evil.example.net/x-1.0.0.tgz}\n"
        self.assertEqual(self.deps({'pnpm-lock.yaml': 'lockfileVersion: 9\n' + good}, base).hard, [])
        scan = self.deps({'pnpm-lock.yaml': 'lockfileVersion: 9\n' + good + bad}, base)
        self.assertEqual([i.rule for i in scan.hard], ['lock-registry'])

    def test_text_lock_lines_that_were_already_there_are_not_rejudged(self):
        bad = '  resolved "https://evil.example.net/x/-/x-1.0.0.tgz#abc"\n'
        base = {'yarn.lock': '# yarn lockfile v1\n' + bad}
        scan = self.deps({'yarn.lock': '# yarn lockfile v1\n' + bad + '\nlodash@^4:\n  version "4.17.21"\n'}, base)
        self.assertEqual(scan.hard, [])


class PythonDepsTest(DepsTest):
    def req(self, text, base='requests==2.31.0\nflask==3.0.0\n', name='requirements.txt', **kw):
        return self.deps({name: base + text}, {name: base}, **kw)

    def test_added_pinned_requirement_is_advisory(self):
        scan = self.req('numpy==1.26.0\n')
        self.assertEqual((scan.hard, self.note(scan)), ([], [('dep-added', 'requirements.txt#numpy')]))

    def test_package_source_options_are_hard(self):
        for line in ('--extra-index-url https://pypi.evil.test/simple', '--index-url https://pkgs.test/simple',
                     '-i https://pkgs.test/simple', '--trusted-host pkgs.test', '-f ./wheels',
                     '--find-links https://pkgs.test/wheels'):
            with self.subTest(line):
                self.assertEqual([r for r, _ in self.hard_of(self.req(line + '\n'))], ['dep-index'])

    def hard_of(self, scan):
        return self.hard(scan)

    def test_requirements_outside_the_index_are_hard(self):
        for line in ('-e git+https://github.com/o/r.git#egg=r', 'git+https://github.com/o/r.git',
                     'r @ https://pkgs.test/r-1.0-py3-none-any.whl', '../sibling', '/abs/pkg', 'r @ file:///opt/r',
                     './wheels/r-1.0-py3-none-any.whl', '-e ../outside'):
            with self.subTest(line):
                self.assertEqual([r for r, _ in self.hard(self.req(line + '\n'))], ['dep-source'])

    def test_packages_from_this_repository_are_advisory(self):
        for line in ('-e .', '-e ./packages/core[dev]', './local_pkg'):
            with self.subTest(line):
                scan = self.req(line + '\n')
                self.assertEqual(scan.hard, [])
                self.assertEqual([r for r, _ in self.note(scan)], ['dep-local'])

    def test_option_comment_and_hash_lines_are_not_problems(self):
        text = '# comment\n\n-r base.txt\n-c constraints.txt\n--no-binary :all:\nnumpy==1.26.0 \\\n    --hash=sha256:abcdef\n'
        scan = self.req(text)
        self.assertEqual(scan.hard, [])

    def test_relative_include_files_are_not_dependency_sources(self):
        self.assertEqual(self.req('-r ../base.txt\n-c ../constraints.txt\n', name='requirements/dev.txt').hard, [])

    def test_lines_already_on_base_are_not_rejudged(self):
        scan = self.req('numpy==1.26.0\n', base='-e .\n--extra-index-url https://pkgs.test/simple\nrequests==2.31.0\n')
        self.assertEqual(scan.hard, [])

    def test_unpinned_requirement_in_a_pinned_file_is_advisory(self):
        scan = self.req('pandas>=2\n')
        self.assertIn(('dep-open-range', 'requirements.txt#pandas'), self.note(scan))
        loose = self.req('pandas>=2\n', base='requests>=2\nflask>=3\n')
        self.assertNotIn(('dep-open-range', 'requirements.txt#pandas'), self.note(loose))

    def test_constraints_and_nested_requirements_files_are_analyzed(self):
        for name in ('constraints.txt', 'requirements-dev.txt', 'requirements/base.txt'):
            with self.subTest(name):
                scan = self.req('--extra-index-url https://pkgs.test/simple\n', name=name)
                self.assertEqual([r for r, _ in self.hard(scan)], ['dep-index'])

    @NEEDS_TOML
    def test_pyproject_pep621_dependencies(self):
        base = '[project]\nname = "x"\ndependencies = ["requests>=2"]\n'
        new = ('[project]\nname = "x"\ndependencies = ["requests>=2", "foo @ git+https://github.com/o/foo.git", "bar>=1"]\n'
               '[project.optional-dependencies]\nweb = ["baz @ https://pkgs.test/baz.whl"]\n'
               '[dependency-groups]\ndev = ["pytest>=8", {include-group = "web"}]\n')
        scan = self.deps({'pyproject.toml': new}, {'pyproject.toml': base})
        self.assertEqual(sorted(self.hard(scan)), [('dep-source', 'pyproject.toml#baz'), ('dep-source', 'pyproject.toml#foo')])
        self.assertEqual(sorted(k for r, k in self.note(scan) if r == 'dep-added'),
                         ['pyproject.toml#bar', 'pyproject.toml#baz', 'pyproject.toml#foo', 'pyproject.toml#pytest'])

    @NEEDS_TOML
    def test_pyproject_poetry_dependencies(self):
        base = '[tool.poetry.dependencies]\npython = "^3.11"\nrequests = "^2"\n'
        new = (base + 'internal = { git = "https://github.com/o/internal.git" }\nlocal = { path = "../local" }\n'
               'anyv = "*"\nfine = { version = "^1.0", extras = ["x"] }\nstar = { version = "*" }\n'
               '[tool.poetry.group.dev.dependencies]\ndevlocal = { path = "../devlocal" }\n')
        scan = self.deps({'pyproject.toml': new}, {'pyproject.toml': base})
        self.assertEqual(sorted(self.hard(scan)), sorted([
            ('dep-source', 'pyproject.toml#internal'), ('dep-source', 'pyproject.toml#local'),
            ('dep-source', 'pyproject.toml#devlocal'), ('dep-unpinned', 'pyproject.toml#anyv'),
            ('dep-unpinned', 'pyproject.toml#star')]))
        self.assertNotIn(('dep-added', 'pyproject.toml#python'), self.note(scan))
        self.assertIn(('dep-added', 'pyproject.toml#fine'), self.note(scan))

    @NEEDS_TOML
    def test_pyproject_uv_sources_and_indexes(self):
        base = '[project]\nname = "x"\ndependencies = []\n'
        new = (base + '[tool.uv.sources]\ngitdep = { git = "https://github.com/o/g.git" }\n'
               'member = { workspace = true }\nlocal = { path = "../local" }\n'
               '[[tool.uv.index]]\nname = "private"\nurl = "https://pkgs.internal.test/simple"\n')
        scan = self.deps({'pyproject.toml': new}, {'pyproject.toml': base})
        self.assertEqual(sorted(self.hard(scan)), [('dep-index', 'pyproject.toml#private'),
                                                    ('dep-source', 'pyproject.toml#gitdep'),
                                                    ('dep-source', 'pyproject.toml#local')])

    @NEEDS_TOML
    def test_pyproject_poetry_source_is_a_new_index(self):
        base = '[tool.poetry]\nname = "x"\n'
        new = base + '[[tool.poetry.source]]\nname = "private"\nurl = "https://pkgs.internal.test/simple"\n'
        scan = self.deps({'pyproject.toml': new}, {'pyproject.toml': base})
        self.assertEqual(self.hard(scan), [('dep-index', 'pyproject.toml#private')])

    @NEEDS_TOML
    def test_pyproject_dependency_change_needs_the_lockfile(self):
        base = {'pyproject.toml': '[project]\nname = "x"\ndependencies = ["requests>=2"]\n', 'uv.lock': 'v1\n'}
        new = '[project]\nname = "x"\ndependencies = ["requests>=2", "flask>=3"]\n'
        self.assertEqual(self.hard(self.deps({'pyproject.toml': new}, base)), [('lockfile-stale', 'uv.lock')])
        self.assertEqual(self.deps({'pyproject.toml': new, 'uv.lock': 'v2\n'}, base).hard, [])

    @NEEDS_TOML
    def test_pyproject_tool_config_change_does_not_need_the_lockfile(self):
        base = {'pyproject.toml': '[project]\nname = "x"\ndependencies = ["requests>=2"]\n', 'uv.lock': 'v1\n',
                'poetry.lock': 'v1\n'}
        new = base['pyproject.toml'] + '[tool.ruff]\nline-length = 120\n'
        scan = self.deps({'pyproject.toml': new}, base)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    @NEEDS_TOML
    def test_reordering_dependencies_does_not_need_the_lockfile(self):
        base = {'pyproject.toml': '[project]\nname = "x"\ndependencies = ["flask>=3", "requests>=2"]\n', 'uv.lock': 'v1\n'}
        new = '[project]\nname = "x"\ndependencies = ["requests>=2", "flask>=3"]\n'
        self.assertEqual(self.deps({'pyproject.toml': new}, base).hard, [])

    def test_toml_manifests_without_tomllib_are_not_analyzed_not_failed(self):
        saved, deps.tomllib = deps.tomllib, None
        try:
            scan = self.deps({'pyproject.toml': '[project]\nname = "x"\ndependencies = ["evil @ git+https://e.test/x"]\n'},
                             {'pyproject.toml': '[project]\nname = "x"\n'})
        finally:
            deps.tomllib = saved
        self.assertEqual(scan.integrity, [])
        self.assertEqual(self.note(scan), [('not-analyzed', 'pyproject.toml')])
        self.assertEqual(scan.missing, ['Python 3.11+ (tomllib) to analyze TOML manifests'])  # run is incomplete

    @NEEDS_TOML
    def test_invalid_toml_is_integrity(self):
        scan = self.deps({'pyproject.toml': '[project\nname = '}, {'pyproject.toml': '[project]\nname = "x"\n'})
        self.assertTrue(any('not valid TOML' in p for p in scan.integrity), scan.integrity)

    def test_pipfile_lock_sync_is_not_attempted_but_deleting_the_lock_is_caught(self):
        scan = self.deps({'Pipfile.lock': None}, {'Pipfile': '[packages]\n', 'Pipfile.lock': '{}\n'})
        self.assertEqual(self.hard(scan), [('lockfile-removed', 'Pipfile.lock')])


class GoRustRubyPhpDepsTest(DepsTest):
    GO_BASE: ClassVar[dict] = {'go.mod': 'module example.com/m\n\ngo 1.21\n\nrequire github.com/a/a v1.0.0\n', 'go.sum': 'sum\n'}

    def test_go_require_added_is_advisory_and_needs_go_sum(self):
        new = self.GO_BASE['go.mod'] + 'require github.com/b/b v1.2.0\n'
        scan = self.deps({'go.mod': new}, self.GO_BASE)
        self.assertEqual(self.note(scan), [('dep-added', 'go.mod#github.com/b/b')])
        self.assertEqual(self.hard(scan), [('lockfile-stale', 'go.sum')])
        self.assertEqual(self.deps({'go.mod': new, 'go.sum': 'sum2\n'}, self.GO_BASE).hard, [])

    def test_go_require_block_and_indirect_comments(self):
        new = ('module example.com/m\n\ngo 1.21\n\nrequire (\n\tgithub.com/a/a v1.0.0\n'
               '\tgithub.com/c/c v0.3.0 // indirect\n)\n')
        scan = self.deps({'go.mod': new, 'go.sum': 'sum2\n'}, self.GO_BASE)
        self.assertEqual(self.note(scan), [('dep-added', 'go.mod#github.com/c/c')])

    def test_go_replace_to_a_local_path_is_hard(self):
        for target in ('../local', './vendor/x', '/abs/x'):
            with self.subTest(target):
                new = self.GO_BASE['go.mod'] + f'replace github.com/a/a => {target}\n'
                scan = self.deps({'go.mod': new, 'go.sum': 'sum2\n'}, self.GO_BASE)
                self.assertEqual(self.hard(scan), [('dep-source', 'go.mod#github.com/a/a')])

    def test_go_replace_with_a_module_fork_is_advisory(self):
        new = self.GO_BASE['go.mod'] + 'replace github.com/a/a => github.com/fork/a v1.0.1\n'
        scan = self.deps({'go.mod': new, 'go.sum': 'sum2\n'}, self.GO_BASE)
        self.assertEqual(scan.hard, [])
        self.assertIn(('dep-replace', 'go.mod#github.com/a/a'), self.note(scan))

    def test_go_version_bump_alone_is_ignored(self):
        scan = self.deps({'go.mod': self.GO_BASE['go.mod'].replace('go 1.21', 'go 1.22')}, self.GO_BASE)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    CARGO_BASE: ClassVar[dict] = {'Cargo.toml': '[package]\nname = "x"\nversion = "0.1.0"\n\n[dependencies]\nserde = "1.0"\n',
                  'Cargo.lock': 'lock\n'}

    @NEEDS_TOML
    def test_cargo_added_dependency_is_advisory_and_needs_cargo_lock(self):
        new = self.CARGO_BASE['Cargo.toml'] + 'rand = "0.8"\n'
        scan = self.deps({'Cargo.toml': new}, self.CARGO_BASE)
        self.assertEqual(self.note(scan), [('dep-added', 'Cargo.toml#rand')])
        self.assertEqual(self.hard(scan), [('lockfile-stale', 'Cargo.lock')])

    @NEEDS_TOML
    def test_cargo_git_and_wildcard_are_hard(self):
        new = (self.CARGO_BASE['Cargo.toml'] + 'gitdep = { git = "https://github.com/o/g" }\nany = "*"\n'
               'anyv = { version = "*" }\n[dev-dependencies]\ndevgit = { git = "https://github.com/o/d" }\n')
        scan = self.deps({'Cargo.toml': new, 'Cargo.lock': 'lock2\n'}, self.CARGO_BASE)
        self.assertEqual(sorted(self.hard(scan)), [('dep-source', 'Cargo.toml#devgit'), ('dep-source', 'Cargo.toml#gitdep'),
                                                    ('dep-unpinned', 'Cargo.toml#any'), ('dep-unpinned', 'Cargo.toml#anyv')])

    def test_cargo_path_and_workspace_dependencies_are_not_hard(self):
        new = (self.CARGO_BASE['Cargo.toml'] + 'sibling = { path = "../sibling" }\n'
               'shared = { workspace = true }\nlocal = { path = "crates/local", version = "0.1" }\n'
               '[workspace.dependencies]\ntokio = "1"\n[target.\'cfg(unix)\'.dependencies]\nlibc = "0.2"\n')
        scan = self.deps({'Cargo.toml': new, 'Cargo.lock': 'lock2\n'}, self.CARGO_BASE)
        self.assertEqual(scan.hard, [])

    @NEEDS_TOML
    def test_cargo_package_version_bump_does_not_need_the_lockfile(self):
        new = self.CARGO_BASE['Cargo.toml'].replace('0.1.0', '0.2.0')
        scan = self.deps({'Cargo.toml': new}, self.CARGO_BASE)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    @NEEDS_TOML
    def test_cargo_patch_section_git_override_is_hard(self):
        new = self.CARGO_BASE['Cargo.toml'] + '\n[patch.crates-io]\nserde = { git = "https://github.com/o/serde" }\n'
        scan = self.deps({'Cargo.toml': new, 'Cargo.lock': 'lock2\n'}, self.CARGO_BASE)
        self.assertEqual([r for r, _ in self.hard(scan)], ['dep-source'])

    GEM_BASE: ClassVar[dict] = {'Gemfile': 'source "https://rubygems.org"\ngem "rails", "~> 7.0"\n', 'Gemfile.lock': 'lock\n'}

    def test_gemfile_added_gem_is_advisory_and_needs_the_lockfile(self):
        scan = self.deps({'Gemfile': self.GEM_BASE['Gemfile'] + 'gem "puma", "~> 6.0"\n'}, self.GEM_BASE)
        self.assertEqual(self.note(scan), [('dep-added', 'Gemfile#puma')])
        self.assertEqual(self.hard(scan), [('lockfile-stale', 'Gemfile.lock')])

    def test_gemfile_git_github_path_gems_and_foreign_sources_are_hard(self):
        extra = ('source "https://gems.internal.test"\ngem "a", git: "https://github.com/o/a.git"\n'
                 'gem "b", github: "o/b"\ngem "c", path: "../c"\n')
        scan = self.deps({'Gemfile': self.GEM_BASE['Gemfile'] + extra, 'Gemfile.lock': 'lock2\n'}, self.GEM_BASE)
        self.assertEqual(sorted(self.hard(scan)), sorted([('dep-index', 'Gemfile#source "https://gems.internal.test"'),
                                                          ('dep-source', 'Gemfile#a'), ('dep-source', 'Gemfile#b'),
                                                          ('dep-source', 'Gemfile#c')]))

    def test_gemfile_rubygems_source_variants_are_fine(self):
        new = "source 'https://rubygems.org'\ngem 'rails', '~> 7.1'\n"
        scan = self.deps({'Gemfile': new, 'Gemfile.lock': 'lock2\n'}, self.GEM_BASE)
        self.assertEqual(scan.hard, [])

    def test_gemfile_hash_rocket_git_source_is_hard(self):
        new = self.GEM_BASE['Gemfile'] + "gem 'a', :git => 'https://github.com/o/a.git'\n"
        scan = self.deps({'Gemfile': new, 'Gemfile.lock': 'lock2\n'}, self.GEM_BASE)
        self.assertEqual([r for r, _ in self.hard(scan)], ['dep-source'])

    COMPOSER_BASE: ClassVar[dict] = {'composer.json': json.dumps({'require': {'php': '^8.1', 'monolog/monolog': '^3.0'}}),
                     'composer.lock': '{}'}

    def composer(self, require=None, lock=True, **extra):
        doc = json.dumps({'require': {'php': '^8.1', 'monolog/monolog': '^3.0', **(require or {})}, **extra})
        change = {'composer.json': doc}
        if lock:
            change['composer.lock'] = '{"v": 2}'
        return self.deps(change, self.COMPOSER_BASE)

    def test_composer_wildcards_are_hard(self):
        for spec in ('*', 'dev-master', 'dev-main', ''):
            with self.subTest(repr(spec)):
                self.assertEqual(self.hard(self.composer({'acme/lib': spec})), [('dep-unpinned', 'composer.json#acme/lib')])

    def test_composer_pinned_dependency_is_advisory(self):
        scan = self.composer({'acme/lib': '^1.2'})
        self.assertEqual((scan.hard, self.note(scan)), ([], [('dep-added', 'composer.json#acme/lib')]))

    def test_composer_repositories_and_lockfile_sync(self):
        scan = self.composer(repositories=[{'type': 'vcs', 'url': 'https://github.com/o/lib'}])
        self.assertEqual(self.hard(scan), [('dep-index', 'composer.json#repositories')])
        stale = self.composer({'acme/lib': '^1.2'}, lock=False)
        self.assertEqual(self.hard(stale), [('lockfile-stale', 'composer.lock')])

    def test_composer_platform_extension_requirements_are_not_unpinned(self):
        self.assertEqual(self.composer({'ext-json': '*', 'ext-mbstring': '*', 'lib-curl': '*'}).hard, [])


class NotAnalyzedDepsTest(DepsTest):
    def test_unparsed_ecosystems_are_advisory_not_clean(self):
        for name in ('pom.xml', 'build.gradle', 'Package.swift', 'pubspec.yaml', 'mix.exs', 'App/App.csproj',
                     'Directory.Packages.props'):
            with self.subTest(name):
                scan = self.deps({name: 'changed\n'}, {name: 'orig\n'})
                self.assertEqual(self.note(scan), [('not-analyzed', name)])
                self.assertEqual(scan.hard, [])
                self.assertEqual(scan.coverage['scanned'], 0)

    def test_unrelated_files_and_empty_change_are_clean(self):
        scan = self.deps({'src/a.py': 'a = 1\n', 'README.md': 'x\n'})
        self.assertEqual((scan.hard, scan.advisory, scan.integrity), ([], [], []))
        self.assertEqual(scan.coverage['scanned'], 0)


# ─── diff-coverage ───────────────────────────────────────────────────────────
def lcov(path: str, hits: dict[int, int]) -> str:
    return f'SF:{path}\n' + ''.join(f'DA:{n},{h}\n' for n, h in sorted(hits.items())) + 'end_of_record\n'


def cobertura(source: str | None, classes: dict[str, dict[int, int]]) -> str:
    sources = f'<sources><source>{source}</source></sources>' if source else ''
    body = ''.join(f'<class name="c" filename="{f}"><lines>'
                   + ''.join(f'<line number="{n}" hits="{h}"/>' for n, h in sorted(lines.items()))
                   + '</lines></class>' for f, lines in classes.items())
    return f'<?xml version="1.0"?><coverage>{sources}<packages><package name="p"><classes>{body}</classes></package></packages></coverage>'


def jacoco(package: str, sourcefile: str, lines: dict[int, int]) -> str:
    rows = ''.join(f'<line nr="{n}" mi="{0 if c else 2}" ci="{c}" mb="0" cb="0"/>' for n, c in sorted(lines.items()))
    return (f'<?xml version="1.0"?><report name="r"><package name="{package}"><sourcefile name="{sourcefile}">{rows}'
            f'</sourcefile></package></report>')


class DiffCoverageTest(BuiltinCase):
    def report_path(self, name='cov.report') -> str:
        return os.path.join(self.tmp, name)

    def cov(self, report, change, base=None, guard=None, policy=None, history=(), report_name='cov.report'):
        if report is not None:
            with open(self.report_path(report_name), 'w', encoding='utf-8') as fh:
                fh.write(report)
        g = {'builtin': 'diff-coverage', 'input': self.report_path(report_name), **(guard or {})}
        return self.scan(coverage.diff_coverage, base, change, guard=g, policy=policy, history=history)

    def boundary(self, total: int, hit: int, **kw):
        hits = {n: 1 if n <= hit else 0 for n in range(1, total + 1)}
        return self.cov(lcov('src/a.py', hits), {'src/a.py': numbered_file(total)}, **kw)

    def test_a_report_older_than_the_run_is_integrity(self):
        path = self.report_path('old.report')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(lcov('src/a.py', {1: 1}))
        os.utime(path, (time.time() - 3600, time.time() - 3600))
        scan = self.cov(None, {'src/a.py': numbered_file(1)}, report_name='old.report')
        self.assertTrue(any('not written during this run' in p for p in scan.integrity), scan.integrity)

    def test_exactly_at_the_minimum_passes_and_one_line_below_fails(self):
        at_min = self.boundary(100, 80)
        self.assertEqual((at_min.hard, at_min.integrity), ([], []))
        below = self.boundary(100, 79)
        (item,) = below.hard
        self.assertEqual((item.rule, item.key, item.mode), ('diff-coverage', 'logic', 'hard'))
        self.assertIn('79.0%', item.message)
        self.assertIn('minimum 80%', item.message)

    def test_boundary_with_a_custom_minimum(self):
        guard = {'min': {'logic': 50}}
        self.assertEqual(self.boundary(10, 5, guard=guard).hard, [])
        self.assertEqual(rules(self.boundary(10, 4, guard=guard).hard), ['diff-coverage'])

    def test_full_coverage_and_no_coverage(self):
        self.assertEqual(self.boundary(10, 10).hard, [])
        scan = self.boundary(10, 0)
        self.assertEqual(rules(scan.hard), ['diff-coverage'])
        self.assertIn('0.0%', scan.hard[0].message)

    def test_one_line_below_the_minimum_fails_even_in_a_large_change(self):
        scan = self.boundary(2001, 1600)
        self.assertEqual(rules(scan.hard), ['diff-coverage'])

    def test_uncovered_lines_are_advisory_with_ranges(self):
        hits = {1: 1, 2: 0, 3: 0, 4: 1, 5: 0, 6: 1, 7: 1, 8: 1, 9: 1, 10: 1}
        scan = self.cov(lcov('src/a.py', hits), {'src/a.py': numbered_file(10)}, guard={'min': {'logic': 0}})
        (item,) = scan.advisory
        self.assertEqual((item.rule, item.key, item.path, item.line, item.mode), ('uncovered-lines', 'src/a.py', 'src/a.py', 2, 'advisory'))
        self.assertIn('2-3,5', item.message)

    def test_only_changed_lines_are_judged(self):
        base = {'src/a.py': numbered_file(100)}
        change = {'src/a.py': numbered_file(100) + 'extra_1 = 1\nextra_2 = 2\n'}
        hits = {n: 0 for n in range(1, 101)}
        hits.update({101: 1, 102: 1})
        scan = self.cov(lcov('src/a.py', hits), change, base=base)
        self.assertEqual((scan.hard, scan.advisory, scan.integrity), ([], [], []))

    def test_lines_the_report_does_not_know_are_not_executable(self):
        change = {'src/a.py': '# comment\n\nvalue = 1\n# another\n'}
        scan = self.cov(lcov('src/a.py', {3: 1}), change)
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_changed_lines_without_any_executable_line_pass(self):
        scan = self.cov(lcov('src/a.py', {50: 0}), {'src/a.py': '# only comments\n# here\n'})
        self.assertEqual((scan.hard, scan.integrity), ([], []))

    def test_changed_code_file_missing_from_the_report_is_hard(self):
        change = {'src/a.py': numbered_file(5), 'src/b.py': numbered_file(5)}
        scan = self.cov(lcov('src/a.py', {n: 1 for n in range(1, 6)}), change)
        self.assertEqual([(i.rule, i.key) for i in scan.hard], [('unmeasured', 'src/b.py')])

    def test_tests_deleted_docs_generated_and_excluded_files_need_no_coverage(self):
        base = {'src/old.py': numbered_file(3)}
        change = {'src/a.py': numbered_file(5), 'tests/test_a.py': 'def test_a():\n    assert True\n',
                  'README.md': 'x\n', 'src/old.py': None, 'src/gen.py': '# @generated\nx = 1\n',
                  'vendor/v.py': 'x = 1\n', 'legacy/l.py': 'x = 1\n', 'web/App.tsx': 'export const A = 1;\n'}
        scan = self.cov(lcov('src/a.py', {n: 1 for n in range(1, 6)}), change, base=base, policy={'exclude': ['legacy/**']})
        self.assertEqual((scan.hard, scan.advisory, scan.integrity), ([], [], []))

    def test_minimums_for_other_kinds_are_opt_in(self):
        change = {'web/App.tsx': 'export const A = 1;\nexport const B = 2;\n'}
        guard = {'min': {'ui': 90}}
        scan = self.cov(lcov('web/App.tsx', {1: 1, 2: 0}), change, guard=guard)
        self.assertEqual([(i.rule, i.key) for i in scan.hard], [('diff-coverage', 'ui')])
        scan = self.cov(lcov('src/other.py', {1: 1}), {'web/App.tsx': change['web/App.tsx'], 'src/other.py': 'x = 1\n'},
                        guard=guard)
        self.assertEqual([(i.rule, i.key) for i in scan.hard], [('unmeasured', 'web/App.tsx')])

    def test_null_minimum_switches_a_kind_off(self):
        scan = self.cov(lcov('src/other.py', {1: 1}), {'src/a.py': 'x = 1\n', 'src/other.py': 'y = 1\n'},
                        guard={'min': {'logic': None}})
        self.assertEqual(scan.hard, [])

    def test_totals_aggregate_per_kind_across_files(self):
        report = lcov('src/a.py', {n: 1 for n in range(1, 11)}) + lcov('src/b.py', {n: 0 for n in range(1, 11)})
        change = {'src/a.py': numbered_file(10), 'src/b.py': numbered_file(10)}
        scan = self.cov(report, change, guard={'min': {'logic': 50}})
        self.assertEqual(scan.hard, [])
        scan = self.cov(report, change, guard={'min': {'logic': 51}})
        self.assertEqual(rules(scan.hard), ['diff-coverage'])
        self.assertIn('50.0% of 20 changed', scan.hard[0].message)

    def test_renamed_file_is_judged_by_its_new_path(self):
        repo = self.repo({'src/old.py': numbered_file(10)})
        repo.branch()
        git(repo.root, 'mv', 'src/old.py', 'src/new.py')
        repo.write({'src/new.py': numbered_file(10) + 'added_a = 1\nadded_b = 2\n'})
        with open(self.report_path(), 'w', encoding='utf-8') as fh:
            fh.write(lcov('src/new.py', {**{n: 1 for n in range(1, 11)}, 11: 0, 12: 0}))
        guard = {'builtin': 'diff-coverage', 'input': self.report_path()}
        scan = self.scan_repo(repo, coverage.diff_coverage, guard=guard)
        self.assertEqual(rules(scan.hard), ['diff-coverage'])
        self.assertEqual(rules(scan.advisory), ['uncovered-lines'])
        self.assertEqual(scan.advisory[0].path, 'src/new.py')

    def test_path_spellings_in_the_report_resolve_to_the_repo_file(self):
        for spelling in ('src/a.py', './src/a.py', 'a.py', '{root}/src/a.py', 'src\\a.py'):
            with self.subTest(spelling):
                repo = self.repo({'README.md': 'x\n'})
                repo.branch()
                repo.write({'src/a.py': numbered_file(5)})
                with open(self.report_path(), 'w', encoding='utf-8') as fh:
                    fh.write(lcov(spelling.format(root=repo.root), {n: 0 for n in range(1, 6)}))
                scan = self.scan_repo(repo, coverage.diff_coverage, guard={'builtin': 'diff-coverage', 'input': self.report_path()})
                self.assertEqual((rules(scan.hard), scan.integrity), (['diff-coverage'], []))

    def test_ambiguous_suffix_does_not_resolve(self):
        change = {'src/a.py': numbered_file(3), 'lib/a.py': numbered_file(3)}
        scan = self.cov(lcov('a.py', {1: 1, 2: 1, 3: 1}), change)
        self.assertTrue(any('covers no file of this repository' in p for p in scan.integrity), scan.integrity)

    def test_real_coverage_py_lcov_and_cobertura(self):
        source = fixture('coverage-sample-src.txt')
        with self.subTest('lcov'):
            scan = self.cov(fixture('coverage-py.lcov'), {'src/a.py': source})
            self.assertEqual(rules(scan.hard), ['diff-coverage'])
            self.assertIn('54.5% of 11 changed executable logic lines', scan.hard[0].message)
            self.assertIn('6-8,12-13', scan.advisory[0].message)
            self.assertEqual(scan.integrity, [])
        with self.subTest('cobertura'):
            repo = self.repo({'README.md': 'x\n'})
            repo.branch()
            repo.write({'src/a.py': source})
            xml = fixture('coverage-py-cobertura.xml').replace('{ROOT}', repo.root)
            with open(self.report_path(), 'w', encoding='utf-8') as fh:
                fh.write(xml)
            scan = self.scan_repo(repo, coverage.diff_coverage, guard={'builtin': 'diff-coverage', 'input': self.report_path()})
            self.assertEqual(rules(scan.hard), ['diff-coverage'])
            self.assertIn('54.5% of 11', scan.hard[0].message)
            self.assertIn('6-8,12-13', scan.advisory[0].message)

    def test_real_coverage_py_lcov_passes_with_a_lower_minimum(self):
        scan = self.cov(fixture('coverage-py.lcov'), {'src/a.py': fixture('coverage-sample-src.txt')},
                        guard={'min': {'logic': 54}})
        self.assertEqual((scan.hard, scan.integrity), ([], []))

    def test_cobertura_source_directory_prefixes(self):
        repo = self.repo({'README.md': 'x\n'})
        repo.branch()
        repo.write({'src/pkg/a.py': numbered_file(5)})
        xml = cobertura(os.path.join(repo.root, 'src', 'pkg'), {'a.py': {n: 0 for n in range(1, 6)}})
        with open(self.report_path(), 'w', encoding='utf-8') as fh:
            fh.write(xml)
        scan = self.scan_repo(repo, coverage.diff_coverage, guard={'builtin': 'diff-coverage', 'input': self.report_path()})
        self.assertEqual((rules(scan.hard), scan.integrity), (['diff-coverage'], []))

    def test_jacoco_package_and_source_name_resolve_by_suffix(self):
        change = {'src/main/java/com/acme/A.java': 'class A {}\n' * 10}
        report = jacoco('com/acme', 'A.java', {n: 1 if n <= 8 else 0 for n in range(1, 11)})
        self.assertEqual(self.cov(report, change).hard, [])
        report = jacoco('com/acme', 'A.java', {n: 1 if n <= 7 else 0 for n in range(1, 11)})
        self.assertEqual(rules(self.cov(report, change).hard), ['diff-coverage'])

    def test_real_go_coverprofile_with_module_prefix(self):
        base = {'go.mod': 'module example.com/m\n\ngo 1.21\n'}
        scan = self.cov(fixture('go-cover.out'), {'pkg/a.go': fixture('go-sample-src.txt')}, base=base)
        self.assertEqual(scan.integrity, [])
        self.assertEqual(rules(scan.hard), ['diff-coverage'])
        self.assertIn('66.7% of 9 changed executable logic lines', scan.hard[0].message)
        self.assertIn('10,14-15', scan.advisory[0].message)

    def test_go_overlapping_blocks_keep_the_highest_count(self):
        base = {'go.mod': 'module example.com/m\n'}
        report = 'mode: count\nexample.com/m/a.go:1.1,3.2 1 0\nexample.com/m/a.go:1.1,3.2 1 3\n'
        scan = self.cov(report, {'a.go': 'package a\n' + 'var x = 1\n' * 2}, base=base, guard={'min': {'logic': 100}})
        self.assertEqual((scan.hard, scan.advisory), ([], []))

    def test_several_report_files_are_merged_by_highest_hit_count(self):
        change = {'src/a.py': numbered_file(10)}
        for name, hit in (('cov-1.lcov', range(1, 6)), ('cov-2.lcov', range(6, 11))):
            with open(self.report_path(name), 'w', encoding='utf-8') as fh:
                fh.write(lcov('src/a.py', {n: 1 if n in hit else 0 for n in range(1, 11)}))
        scan = self.scan(coverage.diff_coverage, None, change,
                         guard={'builtin': 'diff-coverage', 'input': self.report_path('cov-*.lcov'), 'min': {'logic': 100}})
        self.assertEqual((scan.hard, scan.integrity), ([], []))

    def test_report_that_resolves_to_no_repo_file_is_integrity(self):
        scan = self.cov(lcov('/somewhere/else/pkg/mod.py', {1: 1, 2: 1}), {'src/a.py': numbered_file(3)})
        self.assertTrue(any('covers no file of this repository' in p for p in scan.integrity), scan.integrity)
        self.assertEqual(scan.hard, [])

    def test_report_with_other_projects_files_among_ours_is_fine(self):
        report = lcov('/somewhere/else/mod.py', {1: 0}) + lcov('src/a.py', {n: 1 for n in range(1, 4)})
        scan = self.cov(report, {'src/a.py': numbered_file(3)})
        self.assertEqual((scan.hard, scan.integrity), ([], []))

    def test_missing_report_is_integrity(self):
        scan = self.scan(coverage.diff_coverage, None, {'src/a.py': numbered_file(3)},
                         guard={'builtin': 'diff-coverage', 'input': self.report_path('does-not-exist.lcov')})
        self.assertTrue(any('not found' in p for p in scan.integrity), scan.integrity)
        self.assertEqual(scan.hard, [])

    def test_malformed_reports_are_integrity(self):
        for name, text in (('empty', ''), ('prose', 'coverage was great\n'), ('broken-xml', '<coverage><packages>'),
                           ('unknown-xml', '<html><body/></html>'), ('json', '{"total": 100}')):
            with self.subTest(name):
                scan = self.cov(text, {'src/a.py': numbered_file(3)})
                self.assertTrue(any('coverage report unreadable' in p for p in scan.integrity), scan.integrity)
                self.assertEqual(scan.hard, [])

    def test_coverage_command_failure_is_integrity(self):
        scan = self.cov(lcov('src/a.py', {1: 1}), {'src/a.py': 'x = 1\n'}, guard={'run': 'echo tests exploded >&2; exit 4'})
        self.assertEqual(len(scan.integrity), 1)
        self.assertIn('exited 4', scan.integrity[0])
        self.assertIn('tests exploded', scan.integrity[0])

    def test_coverage_command_allowed_exit_codes_and_report_production(self):
        path = self.report_path('made.lcov')
        run = f"printf 'SF:src/a.py\\nDA:1,1\\nend_of_record\\n' > {path}; exit 1"
        guard = {'run': run, 'ok_exit': [0, 1], 'input': path}
        scan = self.scan(coverage.diff_coverage, None, {'src/a.py': 'x = 1\n'}, guard={'builtin': 'diff-coverage', **guard})
        self.assertEqual((scan.hard, scan.integrity), ([], []))
        scan = self.scan(coverage.diff_coverage, None, {'src/a.py': 'x = 1\n'},
                         guard={'builtin': 'diff-coverage', 'run': run, 'input': path})
        self.assertTrue(any('exited 1' in p for p in scan.integrity), scan.integrity)

    def test_tmp_placeholder_in_input(self):
        with open(os.path.join(self.tmp, 'placeholder.lcov'), 'w', encoding='utf-8') as fh:
            fh.write(lcov('src/a.py', {1: 1}))
        scan = self.scan(coverage.diff_coverage, None, {'src/a.py': 'x = 1\n'},
                         guard={'builtin': 'diff-coverage', 'input': '{tmp}/placeholder.lcov'})
        self.assertEqual((scan.hard, scan.integrity), ([], []))

    def test_coverage_reports_files_in_report(self):
        scan = self.cov(lcov('src/a.py', {1: 1}) + lcov('src/b.py', {1: 1}), {'src/a.py': 'x = 1\n', 'src/b.py': 'y = 1\n'})
        self.assertEqual(scan.coverage, {'scanned': 2, 'unit': 'files in report'})


# ─── mutation ────────────────────────────────────────────────────────────────
def mutant(line: int, status: str, mutator: str = 'ArithmeticOperator', replacement: str = '-') -> dict:
    return {'id': f'{line}-{status}', 'mutatorName': mutator, 'replacement': replacement, 'status': status,
            'location': {'start': {'line': line, 'column': 1}, 'end': {'line': line, 'column': 5}}}


def mutation_report(files: dict[str, list[dict]]) -> str:
    return json.dumps({'schemaVersion': '1', 'thresholds': {'high': 80, 'low': 60},
                       'files': {p: {'language': 'python', 'source': '', 'mutants': m} for p, m in files.items()}})


class MutationTest(BuiltinCase):
    def mut(self, report, change=None, base=None, guard=None, report_name='mutation.json', policy=None):
        if report is not None:
            with open(os.path.join(self.tmp, report_name), 'w', encoding='utf-8') as fh:
                fh.write(report)
        g = {'builtin': 'mutation', 'input': os.path.join(self.tmp, report_name), **(guard or {})}
        return self.scan(coverage.mutation, base, change if change is not None else {'src/a.py': numbered_file(10)},
                         guard=g, policy=policy)

    def statuses(self, killed: int, survived: int, **kw):
        mutants = [mutant(i + 1, 'Killed') for i in range(killed)] + \
                  [mutant(killed + i + 1, 'Survived') for i in range(survived)]
        return self.mut(mutation_report({'src/a.py': mutants}), **kw)

    def test_a_report_the_command_did_not_rewrite_is_integrity(self):
        path = os.path.join(self.tmp, 'committed.json')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(mutation_report({'src/a.py': [mutant(1, 'Killed')]}))
        os.utime(path, (time.time() - 3600, time.time() - 3600))
        scan = self.mut(None, guard={'run': 'false', 'input': path})
        self.assertTrue(any('not written during this run' in p for p in scan.integrity), scan.integrity)

    def test_score_exactly_at_the_default_minimum_passes(self):
        scan = self.statuses(3, 2)       # 60%
        self.assertEqual((scan.hard, scan.integrity), ([], []))
        self.assertEqual(scan.coverage['mutants_on_changed_lines'], 5)

    def test_score_below_the_minimum_fails_with_the_numbers(self):
        scan = self.statuses(2, 3)       # 40%
        (item,) = scan.hard
        self.assertEqual((item.rule, item.key, item.mode), ('mutation-score', 'changed-lines', 'hard'))
        self.assertIn('40.0%', item.message)
        self.assertIn('(2/5 killed)', item.message)
        self.assertIn('minimum 60%', item.message)

    def test_boundary_with_custom_min_score(self):
        self.assertEqual(self.statuses(4, 1, guard={'min_score': 80}).hard, [])
        self.assertEqual(rules(self.statuses(3, 2, guard={'min_score': 80}).hard), ['mutation-score'])
        self.assertEqual(self.statuses(5, 0, guard={'min_score': 100}).hard, [])
        self.assertEqual(rules(self.statuses(9, 1, guard={'min_score': 100}).hard), ['mutation-score'])

    def test_one_below_a_non_round_boundary(self):
        # min 66: 33/50 = 66% passes, 32/50 = 64% fails
        self.assertEqual(self.statuses(33, 17, guard={'min_score': 66}, change={'src/a.py': numbered_file(60)}).hard, [])
        self.assertEqual(rules(self.statuses(32, 18, guard={'min_score': 66}, change={'src/a.py': numbered_file(60)}).hard),
                         ['mutation-score'])

    def test_timeout_counts_as_killed_and_no_coverage_as_survived(self):
        mutants = [mutant(1, 'Timeout'), mutant(2, 'Timeout'), mutant(3, 'Killed'), mutant(4, 'NoCoverage'),
                   mutant(5, 'NoCoverage')]
        self.assertEqual(self.mut(mutation_report({'src/a.py': mutants})).hard, [])
        mutants[2] = mutant(3, 'NoCoverage')
        self.assertEqual(rules(self.mut(mutation_report({'src/a.py': mutants})).hard), ['mutation-score'])

    def test_ignored_pending_and_error_mutants_are_not_counted(self):
        mutants = [mutant(1, 'Killed'), mutant(2, 'Ignored'), mutant(3, 'CompileError'), mutant(4, 'RuntimeError'),
                   mutant(5, 'Pending')]
        scan = self.mut(mutation_report({'src/a.py': mutants}), guard={'min_score': 100})
        self.assertEqual((scan.hard, scan.coverage['mutants_on_changed_lines']), ([], 1))

    def test_only_mutants_on_changed_lines_count(self):
        base = {'src/a.py': numbered_file(10)}
        change = {'src/a.py': numbered_file(10) + 'extra = 1\n'}
        mutants = [mutant(n, 'Survived') for n in range(1, 11)] + [mutant(11, 'Killed')]
        scan = self.mut(mutation_report({'src/a.py': mutants}), change, base=base)
        self.assertEqual((scan.hard, scan.advisory, scan.coverage['mutants_on_changed_lines']), ([], [], 1))

    def test_no_mutants_on_changed_lines_passes(self):
        scan = self.mut(mutation_report({'src/a.py': [mutant(99, 'Survived')]}))
        self.assertEqual((scan.hard, scan.coverage['mutants_on_changed_lines']), ([], 0))

    def test_survived_mutants_are_advisory_evidence(self):
        mutants = [mutant(n, 'Killed') for n in range(1, 9)] + [mutant(9, 'Survived', 'ConditionalExpression', 'true')]
        scan = self.mut(mutation_report({'src/a.py': mutants}))
        (item,) = scan.advisory
        self.assertEqual((item.rule, item.path, item.line, item.mode), ('survived-mutant', 'src/a.py', 9, 'advisory'))
        self.assertIn('ConditionalExpression survived (-> true)', item.message)
        self.assertEqual(scan.hard, [])

    def test_advisory_list_is_capped_but_the_score_uses_every_mutant(self):
        mutants = [mutant(n, 'Survived') for n in range(1, 41)]
        scan = self.mut(mutation_report({'src/a.py': mutants}), change={'src/a.py': numbered_file(40)})
        self.assertEqual(len(scan.advisory), 30)
        self.assertIn('0/40 killed', scan.hard[0].message)

    def test_path_spellings_and_several_reports(self):
        repo = self.repo({'README.md': 'x\n'})
        repo.branch()
        repo.write({'src/a.py': numbered_file(4), 'src/b.py': numbered_file(4)})
        with open(os.path.join(self.tmp, 'm-1.json'), 'w', encoding='utf-8') as fh:
            fh.write(mutation_report({os.path.join(repo.root, 'src/a.py'): [mutant(1, 'Killed'), mutant(2, 'Killed')]}))
        with open(os.path.join(self.tmp, 'm-2.json'), 'w', encoding='utf-8') as fh:
            fh.write(mutation_report({'./src/b.py': [mutant(1, 'Survived'), mutant(2, 'Survived')]}))
        guard = {'builtin': 'mutation', 'input': os.path.join(self.tmp, 'm-*.json'), 'min_score': 50}
        scan = self.scan_repo(repo, coverage.mutation, guard=guard)
        self.assertEqual(scan.hard, [])
        self.assertEqual((scan.coverage['scanned'], scan.coverage['mutants_on_changed_lines']), (2, 4))
        scan = self.scan_repo(repo, coverage.mutation, guard={**guard, 'min_score': 51})
        self.assertEqual(rules(scan.hard), ['mutation-score'])

    def test_missing_report_is_integrity(self):
        scan = self.mut(None, report_name='absent.json')
        self.assertTrue(any('not found' in p for p in scan.integrity), scan.integrity)

    def test_malformed_reports_are_integrity(self):
        for name, text in (('not-json', 'oops {'), ('empty', ''), ('no-files', '{"schemaVersion": "1"}'),
                           ('files-is-a-list', '{"files": []}')):
            with self.subTest(name):
                scan = self.mut(text)
                self.assertTrue(any('mutation-testing-elements schema' in p for p in scan.integrity), scan.integrity)

    def test_top_level_array_is_integrity(self):
        scan = self.mut('[]')
        self.assertTrue(scan.integrity)

    def test_report_with_no_files_is_integrity(self):
        self.assertTrue(self.mut(json.dumps({'schemaVersion': '1', 'files': {}})).integrity)

    def test_report_for_other_files_only_is_integrity(self):
        scan = self.mut(mutation_report({'/ci/build/other/mod.py': [mutant(1, 'Survived'), mutant(2, 'Survived')]}))
        self.assertTrue(scan.integrity, 'mutation report covering none of the repo files was accepted')

    def test_mutation_command_exit_codes(self):
        path = os.path.join(self.tmp, 'by-command.json')
        report = mutation_report({'src/a.py': [mutant(1, 'Killed')]})
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(report)
        ok = self.mut(None, guard={'run': 'exit 1', 'input': path})
        self.assertEqual((ok.hard, ok.integrity), ([], []))
        failed = self.mut(None, guard={'run': 'echo stryker crashed >&2; exit 2', 'input': path})
        self.assertEqual(len(failed.integrity), 1)
        self.assertIn('exited 2', failed.integrity[0])
        self.assertIn('stryker crashed', failed.integrity[0])
        strict = self.mut(None, guard={'run': 'exit 1', 'ok_exit': [0], 'input': path})
        self.assertTrue(any('exited 1' in p for p in strict.integrity))


if __name__ == '__main__':
    unittest.main()
