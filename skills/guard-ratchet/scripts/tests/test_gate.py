"""The local merge gate: a branch is judged by its own rules and by the target's, and merged only
if both pass. These tests run the runner installed in the repository, as a user would."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from helpers import GUARD, RepoCase, git
from test_runner import DET_GUARD, DET_PY, PY, det, finding

from guardlib import gate as gatemod
from guardlib import init as initmod

ENV = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 't',
       'GIT_COMMITTER_EMAIL': 't@example.com', 'PYTHONDONTWRITEBYTECODE': '1'}


class GateTest(RepoCase):
    def setUp(self):
        repo = self.repo({'detectors/det.py': DET_PY, 'det.json': det([finding('r', 'a', 2)]), 'README.md': 'x\n'},
                         commit=False)
        initmod.install_runner(repo.root, 'tools/guard')
        repo.policy([DET_GUARD])
        repo.commit('guards')
        self.runner = os.path.join(repo.root, 'tools/guard/guard.py')
        self.run_guard(repo, 'update')
        repo.commit('baselines')
        repo.branch()
        self.repo_ = repo

    def run_guard(self, repo, *args, runner=None):
        proc = subprocess.run([sys.executable, runner or self.runner, *args], capture_output=True, text=True,
                              cwd=repo.root, env=ENV)
        return proc.returncode, proc.stdout, proc.stderr

    def gate(self, *args, runner=None):
        code, out, err = self.run_guard(self.repo_, 'gate', 'feature', *args, runner=runner)
        return code, out + err

    def head(self, ref='HEAD'):
        return git(self.repo_.root, 'rev-parse', ref).strip()

    def worktrees(self):
        return git(self.repo_.root, 'worktree', 'list').strip().splitlines()

    def test_a_branch_that_rewrites_its_judge_fails_and_is_not_merged(self):
        repo = self.repo_
        sneaky = DET_PY.replace("print(json.dumps(doc))", "doc['findings'] = [f for f in doc['findings'] "
                                "if f['key'] != 'b']\nprint(json.dumps(doc))")
        repo.write({'detectors/det.py': sneaky, 'det.json': det([finding('r', 'a', 2), finding('r', 'b')]),
                    'guards/exceptions.json': json.dumps({'version': 1, 'exceptions': [
                        {'guard': 'protected', 'rule': 'changed', 'key': 'detectors/det.py',
                         'reason': 'refactor of the detector output', 'approved_by': 'me'}]})})
        repo.commit('sneaky')
        git(repo.root, 'checkout', '-q', 'main')
        before = self.head()
        code, out = self.gate('--merge', '--format', 'json')
        self.assertEqual(code, 1, out)
        report = json.loads(out)
        # The branch's own rules are fooled by its edited detector; the target's rules are not.
        self.assertEqual([s['exit_code'] for s in report['steps']], [0, 1])
        trusted = report['steps'][1]['report']
        self.assertIn('b', [p['key'] for g in trusted['guards'] for p in g['problems'] if p['category'] == 'new'])
        self.assertIsNone(report['merged'])
        self.assertEqual(self.head(), before)
        code, out = self.gate()
        self.assertIn('gate FAIL', out)
        self.assertEqual(len(self.worktrees()), 1)  # the disposable worktree is gone

    def test_a_clean_branch_is_merged_at_the_judged_commit(self):
        repo = self.repo_
        repo.write({'det.json': det([finding('r', 'a', 1)])})
        self.assertEqual(self.run_guard(repo, 'update')[0], 0)
        repo.commit('improve')
        judged = self.head('feature')
        git(repo.root, 'checkout', '-q', 'main')
        code, out = self.gate('--merge', '--format', 'json')
        self.assertEqual(code, 0, out)
        report = json.loads(out)
        self.assertEqual([s['exit_code'] for s in report['steps']], [0, 0])
        self.assertEqual(report['merged'], self.head())
        self.assertEqual(self.head('HEAD^2'), judged)

    def test_an_unrecorded_improvement_blocks_through_the_branch_step(self):
        repo = self.repo_
        repo.write({'det.json': det([finding('r', 'a', 1)])})
        repo.commit('improve without update')
        git(repo.root, 'checkout', '-q', 'main')
        code, out = self.gate()
        self.assertEqual(code, 1, out)
        self.assertIn('stale', out)

    def test_refuses_a_launcher_that_is_not_the_targets_runner(self):
        repo = self.repo_
        repo.write({'det.json': det([finding('r', 'a', 2), finding('r', 'b')])})
        repo.commit('new finding')
        # Running the branch's edited runner (uncommitted edit on top of the branch) is refused...
        with open(os.path.join(repo.root, 'tools/guard/guardlib/report.py'), 'a', encoding='utf-8') as fh:
            fh.write('\n# always pass\n')
        code, out = self.gate('--into', 'main')
        self.assertEqual(code, 2, out)
        self.assertIn("not main's committed runner", out)
        git(repo.root, 'checkout', '-q', '--', 'tools/guard')
        # ...and so is any other copy, such as the skill's own scripts, when it differs from main's.
        git(repo.root, 'checkout', '-q', 'main')
        with open(os.path.join(repo.root, 'tools/guard/guardlib/report.py'), 'a', encoding='utf-8') as fh:
            fh.write('\n# local note\n')
        repo.commit('runner note')
        self.assertEqual(self.gate(runner=GUARD)[0], 2)

    def test_merge_needs_the_target_checked_out_and_a_clean_tree(self):
        repo = self.repo_
        repo.write({'det.json': det([finding('r', 'a', 1)])})
        self.run_guard(repo, 'update')
        repo.commit('improve')
        code, out = self.gate('--into', 'main', '--merge')
        self.assertEqual(code, 2, out)
        self.assertIn('check out main first', out)
        git(repo.root, 'checkout', '-q', 'main')
        repo.write({'README.md': 'dirty\n'})
        code, out = self.gate('--merge')
        self.assertEqual(code, 2, out)
        self.assertIn('clean working tree', out)

    def test_branch_code_cannot_tamper_with_the_judge_or_the_judged_tree(self):
        # The branch's tests run in both steps (unittest is not repository code, so nothing restores
        # them). They try to rewrite any extracted target runner and to reset their own worktree.
        repo = self.repo_
        unit = {'name': 'unit', 'run': f'cd {{root}} && {PY} -m unittest discover -s tests -q', 'parse': 'exit',
                'tier': 'fast'}
        git(repo.root, 'checkout', '-q', 'main')
        repo.policy([DET_GUARD, unit])
        repo.write({'tests/__init__.py': '', 'tests/test_ok.py': 'import unittest\n\n\nclass T(unittest.TestCase):\n'
                    '    def test_ok(self):\n        self.assertTrue(True)\n'})
        repo.commit('unit tests')
        self.run_guard(repo, 'update')
        repo.commit('baselines')
        git(repo.root, 'checkout', '-q', '-B', 'feature')
        evil = """import glob, os, subprocess, tempfile, unittest
for path in glob.glob(os.path.join(tempfile.gettempdir(), 'guard-gate-*', '**', 'runner.py'), recursive=True):
    with open(path, 'a') as fh:
        fh.write('\\nRun.exit_code = property(lambda self: 0)\\n')
subprocess.run(['git', 'reset', '-q', '--hard', 'HEAD~1'], check=False)


class T(unittest.TestCase):
    def test_evil(self):
        self.assertTrue(True)
"""
        repo.write({'tests/test_evil.py': evil, 'det.json': det([finding('r', 'a', 2), finding('r', 'b')])})
        repo.commit('evil')
        git(repo.root, 'checkout', '-q', 'main')
        before = self.head()
        code, out = self.gate('--merge', '--format', 'json')
        self.assertEqual(code, 1, out)
        trusted = json.loads(out)['steps'][1]
        self.assertEqual(trusted['exit_code'], 1)
        self.assertIn('b', [p['key'] for g in trusted['report']['guards'] for p in g['problems'] if p['category'] == 'new'])
        self.assertEqual(self.head(), before)

    def with_unit_tests(self, evil: str):
        """main gets a test guard whose test files nothing restores; the branch adds `evil` as a test."""
        repo = self.repo_
        unit = {'name': 'unit', 'run': f'cd {{root}} && {PY} -m unittest discover -s tests -q', 'parse': 'exit',
                'tier': 'fast'}
        git(repo.root, 'checkout', '-q', 'main')
        repo.policy([unit, DET_GUARD])  # tests first, so they run before the detector scans
        repo.write({'tests/__init__.py': '', 'tests/test_ok.py': 'import unittest\n\n\nclass T(unittest.TestCase):\n'
                    '    def test_ok(self):\n        self.assertTrue(True)\n'})
        repo.commit('unit tests')
        self.run_guard(repo, 'update')
        repo.commit('baselines')
        git(repo.root, 'checkout', '-q', '-B', 'feature')
        repo.write({'tests/test_evil.py': evil, 'det.json': det([finding('r', 'a', 2), finding('r', 'b')])})
        repo.commit('evil')
        git(repo.root, 'checkout', '-q', 'main')
        return self.head()

    def test_a_test_that_rewrites_what_later_guards_scan_is_an_error(self):
        before = self.with_unit_tests(
            "import json\nwith open('det.json', 'w') as fh:\n"
            "    json.dump({'findings': [{'rule': 'r', 'key': 'a', 'count': 2}], 'metrics': []}, fh)\n")
        code, out = self.gate('--merge', '--format', 'json')
        self.assertEqual(code, 2, out)
        self.assertTrue(any('tracked files changed: det.json' in i for i in json.loads(out)['issues']), out)
        self.assertEqual(self.head(), before)

    def test_a_daemon_that_patches_the_extracted_runner_is_caught(self):
        daemon = (
            "import glob, os, tempfile, time\n"
            "end = time.time() + 30\n"
            "while time.time() < end:\n"
            "    for path in glob.glob(os.path.join(tempfile.gettempdir(), 'guard-gate-*', 'runner-*', '**',"
            " 'runner.py'), recursive=True):\n"
            "        text = open(path).read()\n"
            "        if 'PATCHED' not in text:\n"
            "            open(path, 'a').write('\\n# PATCHED\\nRun.exit_code = property(lambda self: 0)\\n')\n"
            "            raise SystemExit\n"
            "    time.sleep(0.01)\n")
        evil = ("import subprocess, sys\n"
                f"subprocess.Popen([sys.executable, '-c', {daemon!r}], start_new_session=True,\n"
                "                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n")
        before = self.with_unit_tests(evil)
        code, out = self.gate('--merge', '--format', 'json')
        self.assertIn(code, (1, 2), out)
        self.assertEqual(self.head(), before)

    def test_guard_changes_without_merge_still_fail_and_hooks_count_as_guard_changes(self):
        repo = self.repo_
        repo.write({'.githooks/post-merge': '#!/bin/sh\necho hi\n', 'det.json': det([finding('r', 'a', 1)])})
        self.run_guard(repo, 'update')
        repo.commit('hook and improvement')
        git(repo.root, 'checkout', '-q', 'main')
        code, out = self.gate('--format', 'json')
        self.assertEqual(code, 1, out)
        report = json.loads(out)
        self.assertEqual(report['guard_changes'], ['.githooks/post-merge'])
        self.assertIn('needs approval', report['note'])
        self.assertEqual(self.gate('--approve-guard-changes')[0], 0)

    def test_isolated_python_modes_and_desktop_junk_are_fine(self):
        repo = self.repo_
        repo.write({'det.json': det([finding('r', 'a', 1)])})
        self.run_guard(repo, 'update')
        repo.commit('improve')
        git(repo.root, 'checkout', '-q', 'main')
        with open(os.path.join(repo.root, '.git/info/exclude'), 'a', encoding='utf-8') as fh:
            fh.write('.DS_Store\n.mypy_cache/\n')  # what a global gitignore usually does
        repo.write({'tools/guard/.DS_Store': 'x', 'tools/guard/.mypy_cache/x': 'y'})
        for flags in (['-I'], ['-P']) if sys.version_info >= (3, 11) else (['-I'],):  # -P is new in 3.11
            with self.subTest(flags=flags):
                proc = subprocess.run([sys.executable, *flags, self.runner, 'check'], capture_output=True, text=True,
                                      cwd=repo.root, env=ENV)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        code, out = self.gate()
        self.assertEqual(code, 0, out)

    def test_the_merge_result_is_judged_against_the_target_tip(self):
        # main gains a rule after the branch was cut; the branch breaks it.
        repo = self.repo_
        git(repo.root, 'checkout', '-q', 'main')
        repo.policy([DET_GUARD, {'name': 'nobad', 'run': 'test ! -e {root}/bad.txt', 'parse': 'exit', 'tier': 'fast'}])
        repo.commit('new rule')
        git(repo.root, 'checkout', '-q', 'feature')
        repo.write({'bad.txt': 'x\n'})
        repo.commit('break the new rule')
        git(repo.root, 'checkout', '-q', 'main')
        code, out = self.gate('--merge')
        self.assertEqual(code, 1, out)
        self.assertIn('not merged', out)

    def test_guard_configuration_changes_need_explicit_approval_to_merge(self):
        repo = self.repo_
        repo.write({'det.json': det([finding('r', 'a', 2), finding('r', 'b')]),
                    'guards/exceptions.json': json.dumps({'version': 1, 'exceptions': [
                        {'guard': 'det', 'rule': 'r', 'key': 'b', 'reason': 'accepted for the beta release',
                         'approved_by': 'me'}]})})
        repo.commit('self-approved exception')
        git(repo.root, 'checkout', '-q', 'main')
        before = self.head()
        code, out = self.gate('--merge')
        self.assertEqual(code, 1, out)
        self.assertIn('guards/exceptions.json', out)
        self.assertIn('--approve-guard-changes', out)
        self.assertEqual(self.head(), before)
        code, out = self.gate('--merge', '--approve-guard-changes')
        self.assertEqual(code, 0, out)
        self.assertNotEqual(self.head(), before)

    def test_repository_hooks_never_run(self):
        repo = self.repo_
        marker = os.path.join(repo.root, '..', os.path.basename(repo.root) + '-hook-ran')
        self.addCleanup(lambda: os.path.exists(marker) and os.remove(marker))
        hook = f'#!/bin/sh\ntouch {marker}\n'
        repo.write({'.githooks/post-checkout': hook, '.githooks/post-merge': hook,
                    '.githooks/pre-merge-commit': hook, 'det.json': det([finding('r', 'a', 1)])})
        for name in ('post-checkout', 'post-merge', 'pre-merge-commit'):
            os.chmod(os.path.join(repo.root, '.githooks', name), 0o755)
        self.run_guard(repo, 'update')
        repo.commit('hooks')
        git(repo.root, 'config', 'core.hooksPath', '.githooks')
        git(repo.root, 'checkout', '-q', 'main')
        if os.path.exists(marker):
            os.remove(marker)  # the checkout above is the test's own, not the gate's
        code, out = self.gate('--merge', '--approve-guard-changes')
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(marker), 'a hook from the branch ran during the gate')

    def test_branch_beats_a_tag_of_the_same_name_and_crlf_checkouts_are_accepted(self):
        repo = self.repo_
        repo.write({'det.json': det([finding('r', 'a', 1)])})
        self.run_guard(repo, 'update')
        repo.commit('improve')
        git(repo.root, 'checkout', '-q', 'main')
        git(repo.root, 'tag', 'main', 'HEAD~1')
        git(repo.root, 'config', 'core.autocrlf', 'true')
        path = os.path.join(repo.root, 'tools/guard/guardlib/report.py')
        with open(path, 'rb') as fh:
            data = fh.read()
        with open(path, 'wb') as fh:
            fh.write(data.replace(b'\n', b'\r\n'))
        code, out = self.gate('--into', 'main', '--format', 'json')
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)['target_commit'], self.head('refs/heads/main'))

    def test_extra_files_next_to_the_runner_are_refused(self):
        git(self.repo_.root, 'checkout', '-q', 'main')
        self.repo_.write({'tools/guard/json.py': 'raise SystemExit(0)\n'})
        code, out = self.gate()
        self.assertEqual(code, 2, out)
        self.assertIn('json.py', out)

    def test_crashed_or_killed_steps_are_errors_not_passes(self):
        self.assertEqual(gatemod._verdict([0, -9]), 2)
        self.assertEqual(gatemod._verdict([0, 139]), 2)
        self.assertEqual(gatemod._verdict([3, 0]), 3)
        self.assertEqual(gatemod._verdict([1, 3]), 1)
        self.assertEqual(gatemod._verdict([0, 0]), 0)

    def test_errors_are_json_under_json_format(self):
        code, out = self.gate('--into', 'nope', '--format', 'json')
        self.assertEqual(code, 2)
        self.assertIn('unknown branch', json.loads(out)['error'])

    def test_a_branch_already_merged_has_nothing_to_judge(self):
        git(self.repo_.root, 'checkout', '-q', 'main')
        code, out = self.gate()
        self.assertEqual(code, 0, out)
        self.assertIn('nothing to judge', out)


if __name__ == '__main__':
    unittest.main()
