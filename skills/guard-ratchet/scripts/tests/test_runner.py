"""End-to-end runner behavior on throwaway git repositories.

A fake detector (`detectors/det.py`) prints whatever `det.json` in the scanned root contains, so
"code" changes are edits to det.json and every ratchet path can be exercised without external tools.
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest

from helpers import FIXTURES, RepoCase, problems, status

PY = sys.executable
DET_PY = '''import json, os, sys
root = sys.argv[1]
with open(os.path.join(root, 'det.json')) as fh:
    doc = json.load(fh)
mode = doc.pop('_raw', None)
if mode == 'garbage':
    print('not json'); sys.exit(0)
if mode == 'crash':
    sys.exit(3)
doc.setdefault('schema', 'guard-ratchet/detector@2')
doc.setdefault('guard', 'det')
doc.setdefault('coverage', {'planned': 10, 'scanned': 10, 'unit': 'files'})
print(json.dumps(doc))
'''
DET_GUARD = {'name': 'det', 'run': f'{PY} detectors/det.py {{root}}', 'parse': 'findings', 'tier': 'fast'}


def det(findings=(), metrics=(), **extra) -> str:
    return json.dumps({'findings': list(findings), 'metrics': list(metrics), **extra})


def finding(rule, key, count=1, path=None):
    return {'rule': rule, 'key': key, 'count': count, **({'path': path} if path else {})}


class Base(RepoCase):
    def setup_repo(self, doc: str, guards=None, files=None, **policy):
        """main = detector + policy + files + baselines; then a feature branch for the change."""
        repo = self.repo({'detectors/det.py': DET_PY, 'det.json': doc, 'README.md': 'x\n', **(files or {})},
                         commit=False)
        repo.policy(guards or [DET_GUARD], **policy)
        repo.commit('init')
        code, report, err = repo.guard('update')
        self.assertIn(code, (0, 1, 3), err)
        repo.commit('baselines')
        repo.branch()
        return repo

    def check(self, repo, *args, expect=None):
        code, report, err = repo.guard('check', *args)
        if expect is not None:
            self.assertEqual(code, expect, json.dumps(report, indent=1) if isinstance(report, dict) else err)
        return code, report


class RatchetFlow(Base):
    def test_in_sync_passes_and_baseline_records_fingerprint(self):
        repo = self.setup_repo(det([finding('dead-file', 'src/a.py', 1, 'src/a.py')]))
        base = json.loads(repo.read('guards/baselines/det.json'))
        self.assertEqual(base['entries'], {'dead-file': {'src/a.py': 1}})
        self.assertTrue(base['fingerprint'].startswith('sha256:'))
        self.assertEqual(base['scanned'], 10)
        self.check(repo, expect=0)

    def test_new_finding_fails_until_excepted(self):
        repo = self.setup_repo(det([finding('dead-file', 'src/a.py')]))
        repo.write({'det.json': det([finding('dead-file', 'src/a.py'), finding('dead-file', 'src/b.py')])})
        _, report = self.check(repo, expect=1)
        self.assertEqual([p['key'] for p in problems(report, 'det', 'new')], ['src/b.py'])
        code, _, err = repo.guard('except', 'add', '--guard', 'det', '--rule', 'dead-file', '--key', 'src/b.py',
                                  '--reason', 'kept for the plugin loader', '--approved-by', 'reviewer')
        self.assertEqual(code, 0, err)
        _, report = self.check(repo, expect=0)
        self.assertEqual(problems(report, 'det', 'new')[0]['excepted_by'], '#1 det/dead-file/src/b.py')
        # update never adopts the excepted finding into the baseline
        repo.guard('update')
        self.assertNotIn('src/b.py', json.loads(repo.read('guards/baselines/det.json'))['entries']['dead-file'])

    def test_exception_max_and_expiry(self):
        repo = self.setup_repo(det([finding('dup', 'h1', 2)]))
        repo.write({'det.json': det([finding('dup', 'h1', 4)]),
                    'guards/exceptions.json': json.dumps({'version': 1, 'exceptions': [
                        {'guard': 'det', 'rule': 'dup', 'key': 'h1', 'max': 3, 'reason': 'mirror of the server copy',
                         'approved_by': 'x'}]})})
        _, report = self.check(repo, expect=1)
        self.assertEqual(problems(report, 'det', 'worse', blocking=True)[0]['current'], 4)
        repo.write({'guards/exceptions.json': json.dumps({'version': 1, 'exceptions': [
            {'guard': 'det', 'rule': 'dup', 'key': 'h1', 'reason': 'mirror of the server copy', 'approved_by': 'x',
             'expires': '2000-01-01'}]})})
        _, report = self.check(repo, expect=1)
        self.assertTrue(problems(report, 'exceptions', 'exception', blocking=True))
        self.assertTrue(problems(report, 'det', 'worse', blocking=True))

    def test_worse_stale_and_safe_update(self):
        repo = self.setup_repo(det([finding('r', 'a', 3), finding('r', 'b', 3), finding('r', 'c', 1)]))
        repo.write({'det.json': det([finding('r', 'a', 5), finding('r', 'b', 2), finding('r', 'new', 1)])})
        _, report = self.check(repo, expect=1)
        self.assertEqual({p['category'] for p in problems(report, 'det', blocking=True)}, {'worse', 'stale', 'new'})
        code, report, _ = repo.guard('update')
        self.assertEqual(code, 1)  # worse and new still block after the update
        entries = json.loads(repo.read('guards/baselines/det.json'))['entries']['r']
        self.assertEqual(entries, {'a': 3, 'b': 2})
        self.assertEqual({p['category'] for p in problems(report, 'det', blocking=True)}, {'worse', 'new'})

    def test_rename_rewrites_keys_on_update(self):
        repo = self.setup_repo(det([finding('fn-complexity', 'src/old.py#parse', 30)]), files={'src/old.py': 'x = 1\n'})
        from helpers import git
        git(repo.root, 'mv', 'src/old.py', 'src/new.py')
        repo.write({'det.json': det([finding('fn-complexity', 'src/new.py#parse', 30)])})
        _, report = self.check(repo, expect=1)
        self.assertEqual(problems(report, 'det', 'moved')[0]['key'], 'src/new.py#parse')
        # The baseline still names the old path; that is not a hand-added entry.
        self.assertEqual(problems(report, 'det', 'locked'), [])
        code, _, _ = repo.guard('update')
        self.assertEqual(code, 0)
        self.check(repo, expect=0)

    def test_rename_of_a_file_keyed_finding_is_moved_not_a_baseline_edit(self):
        # SARIF-style keys are the bare path, so move pairing by symbol does not apply.
        repo = self.setup_repo(det([finding('F401', 'src/old.py', 1)]), files={'src/old.py': 'x = 1\n'})
        from helpers import git
        git(repo.root, 'mv', 'src/old.py', 'src/new.py')
        repo.write({'det.json': det([finding('F401', 'src/new.py', 1)])})
        _, report = self.check(repo, expect=1)
        self.assertEqual([p['key'] for p in problems(report, 'det', 'moved')], ['src/new.py'])
        self.assertEqual(problems(report, 'det', 'locked'), [])
        repo.guard('update')
        self.check(repo, expect=0)

    def test_legacy_v1_detector_output_and_baseline(self):
        repo = self.repo({'detectors/det.py': DET_PY, 'det.json': json.dumps(
            {'schema': None, 'guard': 'det', 'scanned': 5, 'findings': [{'rule': 'r', 'key': 'a', 'count': 2}],
             'hard': []}), 'guards/baselines/det.json': json.dumps(
            {'version': 1, 'guard': 'det', 'entries': {'r': {'a': 2}}})}, commit=False)
        repo.write({'det.json': repo.read('det.json').replace('"schema": null, ', '')})
        repo.write({'detectors/det.py': DET_PY.replace("doc.setdefault('schema', 'guard-ratchet/detector@2')\n", '')
                    .replace("doc.setdefault('coverage', {'planned': 10, 'scanned': 10, 'unit': 'files'})\n", '')})
        repo.policy([DET_GUARD])
        repo.commit()
        _, report = self.check(repo, expect=0)
        self.assertTrue(any('legacy v1' in p['message'] for p in problems(report, 'det', 'advisory')))
        repo.guard('update')
        self.assertEqual(json.loads(repo.read('guards/baselines/det.json'))['version'], 2)


class Integrity(Base):
    def test_a_failing_version_command_is_integrity(self):
        repo = self.setup_repo(det(), [{**DET_GUARD, 'version': 'false'}])
        _, report = self.check(repo, expect=1)
        self.assertTrue(any('version command' in p['message'] for p in problems(report, 'det', 'integrity')))

    def test_a_committed_report_is_not_evidence(self):
        with open(os.path.join(FIXTURES, 'pytest-junit.xml'), encoding='utf-8') as fh:
            junit = fh.read()
        guard = {'name': 'tests', 'run': 'echo ignored', 'parse': 'junit', 'input': 'reports/junit.xml', 'tier': 'fast'}
        repo = self.repo({'reports/junit.xml': junit, 'guards/policy.json': json.dumps({'version': 2, 'guards': [guard]})})
        old = time.time() - 3600
        os.utime(os.path.join(repo.root, 'reports/junit.xml'), (old, old))
        _, report = self.check(repo, '--base', 'none', expect=1)
        self.assertTrue(any('did not write' in p['message'] for p in problems(report, 'tests', 'integrity')))

    def test_broken_scans_fail_closed(self):
        cases = {
            'garbage': det(_raw='garbage'),
            'crash': det(_raw='crash'),
            'parse': det(parse_failures=['src/bad.py']),
            'partial': det(coverage={'planned': 10, 'scanned': 7}),
            'unsupported': det(unsupported=[{'path': 'src/a.js', 'message': 'cannot resolve ./x'}]),
        }
        repo = self.setup_repo(det())
        for name, doc in cases.items():
            with self.subTest(name):
                repo.write({'det.json': doc})
                _, report = self.check(repo, expect=1)
                self.assertEqual(status(report, 'det'), 'error')
                self.assertTrue(all(not p['exceptable'] for p in problems(report, 'det', 'integrity')))

    def test_update_refuses_to_write_from_a_broken_scan(self):
        repo = self.setup_repo(det([finding('r', 'a')]))
        repo.write({'det.json': det(parse_failures=['x.py'])})
        before = repo.read('guards/baselines/det.json')
        repo.guard('update')
        self.assertEqual(repo.read('guards/baselines/det.json'), before)

    def test_scope_shrink(self):
        repo = self.setup_repo(det(coverage={'planned': 100, 'scanned': 100}))
        repo.write({'det.json': det(coverage={'planned': 60, 'scanned': 60})})
        _, report = self.check(repo, expect=1)
        self.assertTrue(problems(report, 'det', 'scope', blocking=True))
        repo.write({'det.json': det(coverage={'planned': 97, 'scanned': 97})})
        self.check(repo, expect=0)

    def test_missing_tool_is_incomplete_not_pass(self):
        guards = [DET_GUARD, {'name': 'needs', 'run': 'true', 'parse': 'exit', 'requires': ['no-such-tool-xyz']}]
        repo = self.setup_repo(det(), guards)
        repo.write({'src/x.py': 'x = 1\n'})
        code, report = self.check(repo)
        self.assertEqual((code, report['verdict']), (3, 'incomplete'))
        self.assertEqual(status(report, 'needs'), 'missing-tool')
        guards[1]['required'] = False
        repo.policy(guards)
        code, report = self.check(repo)
        self.assertEqual(code, 1)  # optional now, but making it optional is a policy loosening
        self.assertTrue(problems(report, 'policy', 'locked'))

    def test_config_errors_exit_2(self):
        repo = self.setup_repo(det())
        repo.write({'guards/policy.json': json.dumps({'version': 2, 'gards': []})})
        self.assertEqual(repo.guard('check')[0], 2)
        repo.write({'guards/policy.json': json.dumps({'version': 2, 'guards': [DET_GUARD]}),
                    'guards/exceptions.json': '{nope'})
        self.assertEqual(repo.guard('check')[0], 2)
        repo.write({'guards/exceptions.json': None})
        self.assertEqual(repo.guard('check', '--base', 'does-not-exist')[0], 2)


class Thresholds(Base):
    def metric(self, key, value, path):
        return {'metric': 'fn-complexity', 'key': key, 'path': path, 'value': value}

    def test_limits_depend_on_kind_and_language(self):
        doc = det(metrics=[self.metric('src/a.py#f', 23, 'src/a.py'), self.metric('src/a.go#f', 23, 'src/a.go'),
                           self.metric('src/v.tsx#f', 23, 'src/v.tsx'), self.metric('tests/t.py#f', 60, 'tests/t.py'),
                           self.metric('gen/x_pb2.py#f', 90, 'gen/x_pb2.py'), self.metric('src/b.py#g', 17, 'src/b.py')])
        repo = self.setup_repo(det())
        repo.write({'det.json': doc})
        _, report = self.check(repo, expect=1)
        self.assertEqual([p['key'] for p in problems(report, 'det', 'new')], ['src/a.py#f'])
        near = [p['key'] for p in problems(report, 'det', 'advisory') if 'near' in p.get('message', '')]
        self.assertEqual(sorted(near), ['src/a.go#f', 'src/b.py#g', 'src/v.tsx#f'])

    def test_raising_a_threshold_is_locked_and_needs_a_rebuild(self):
        repo = self.setup_repo(det(metrics=[self.metric('src/a.py#f', 30, 'src/a.py')]))
        self.assertEqual(json.loads(repo.read('guards/baselines/det.json'))['entries'],
                         {'fn-complexity': {'src/a.py#f': 30}})
        repo.policy([DET_GUARD], thresholds={'fn-complexity': {'limit': {'logic': 40}}})
        _, report = self.check(repo, expect=1)
        self.assertTrue(any(p['key'] == 'thresholds.fn-complexity.limit.logic'
                            for p in problems(report, 'policy', 'locked', blocking=True)))
        self.assertTrue(problems(report, 'det', 'rule-change', blocking=True))
        code, report, _ = repo.guard('update', '--rules-changed')
        self.assertEqual(code, 1)
        dropped = problems(report, 'det', 'rule-change', blocking=True)
        self.assertEqual([p['key'] for p in dropped], ['src/a.py#f'])
        repo.write({'guards/exceptions.json': json.dumps({'version': 1, 'exceptions': [
            {'guard': 'det', 'rule': 'rule-change', 'key': '*', 'reason': 'agreed with the team: 40 for parsers',
             'approved_by': 'lead'},
            {'guard': 'policy', 'rule': 'loosen', 'key': 'thresholds.fn-complexity.limit.logic',
             'reason': 'agreed with the team: 40 for parsers', 'approved_by': 'lead'}]})})
        code, report, _ = repo.guard('update', '--rules-changed')
        self.assertEqual(code, 0, json.dumps(report, indent=1))
        self.assertEqual(json.loads(repo.read('guards/baselines/det.json'))['entries'], {})

    def test_deleting_the_baseline_does_not_skip_the_rule_change_check(self):
        repo = self.setup_repo(det(metrics=[self.metric('src/a.py#f', 30, 'src/a.py')]))
        repo.policy([DET_GUARD], thresholds={'fn-complexity': {'limit': {'logic': 40}}})
        repo.write({'guards/baselines/det.json': None})
        code, report, _ = repo.guard('update')
        self.assertEqual(code, 1)
        self.assertEqual([p['key'] for p in problems(report, 'det', 'rule-change', blocking=True)], ['src/a.py#f'])
        self.assertFalse(os.path.exists(os.path.join(repo.root, 'guards/baselines/det.json')))

    def test_tightening_rebuilds_from_base_code_not_from_the_change(self):
        repo = self.setup_repo(det(metrics=[self.metric('src/a.py#f', 15, 'src/a.py')]))
        repo.policy([DET_GUARD], thresholds={'fn-complexity': {'limit': {'logic': 10}}})
        # the change also adds a new complex function: it must not be grandfathered
        repo.write({'det.json': det(metrics=[self.metric('src/a.py#f', 15, 'src/a.py'),
                                             self.metric('src/b.py#g', 14, 'src/b.py')])})
        code, report, _ = repo.guard('update', '--rules-changed')
        self.assertEqual(json.loads(repo.read('guards/baselines/det.json'))['entries'],
                         {'fn-complexity': {'src/a.py#f': 15}})
        self.assertEqual([p['key'] for p in problems(report, 'det', 'new')], ['src/b.py#g'])
        self.assertFalse(problems(report, 'policy', 'locked', blocking=True))


class Locks(Base):
    def test_hand_edited_baseline_is_locked(self):
        repo = self.setup_repo(det([finding('r', 'a', 2)]))
        doc = json.loads(repo.read('guards/baselines/det.json'))
        doc['entries']['r']['a'] = 5
        doc['entries']['r']['b'] = 1
        repo.write({'guards/baselines/det.json': json.dumps(doc), 'det.json': det([finding('r', 'a', 5),
                                                                                    finding('r', 'b', 1)])})
        _, report = self.check(repo, expect=1)
        self.assertEqual(sorted(p['key'] for p in problems(report, 'det', 'locked', blocking=True)), ['a', 'b'])
        self.assertFalse(problems(report, 'det', 'new'))  # the forged baseline hides it from the sync check...

    def test_policy_loosenings(self):
        variants = {
            'guard removed': ([], {}),
            'tier raised': ([{**DET_GUARD, 'tier': 'strict'}], {}),
            'command changed': ([{**DET_GUARD, 'run': DET_GUARD['run'] + ' --quiet'}], {}),
            'mode weakened': ([{**DET_GUARD, 'mode': 'advisory'}], {}),
            'exclude added': ([DET_GUARD], {'exclude': ['src/**']}),
            'more generated': ([DET_GUARD], {'paths': {'generated': ['src/**']}}),
            'strict role removed': ([DET_GUARD], {'risk': {'strict_roles': ['ci']}}),
        }
        repo = self.setup_repo(det())
        for name, (guards, extra) in variants.items():
            with self.subTest(name):
                repo.policy(guards, **extra)
                _, report = self.check(repo, expect=1)
                self.assertTrue(problems(report, 'policy', 'locked', blocking=True), name)
        repo.policy([DET_GUARD], thresholds={'fn-complexity': {'limit': {'logic': 10}}})
        _, report = self.check(repo)
        self.assertFalse(problems(report, 'policy', 'locked'))  # tightening is free

    def test_protected_files_and_reclassification(self):
        repo = self.setup_repo(det(), files={'src/app.py': 'def f():\n    return 1\n'})
        repo.write({'detectors/det.py': DET_PY + '\n# tweak\n', '.github/workflows/ci.yml': 'on: push\n',
                    'src/app.py': '# Code generated by hand. DO NOT EDIT.\ndef f():\n    return 1\n'})
        _, report = self.check(repo, expect=1)
        keys = {p['key'] for p in problems(report, 'protected', 'protected', blocking=True)}
        self.assertEqual(keys, {'detectors/det.py', '.github/workflows/ci.yml'})
        self.assertEqual([p['key'] for p in problems(report, 'policy', 'locked') if p['rule'] == 'reclassified'],
                         ['src/app.py'])


    def test_code_escaping_its_kind_is_locked(self):
        repo = self.setup_repo(det(), files={'src/m1.py': 'x = 1\n', 'src/m2.py': 'y = 1\n'})
        from helpers import git
        os.makedirs(os.path.join(repo.root, 'src/vendor'))
        os.makedirs(os.path.join(repo.root, 'scripts'))
        git(repo.root, 'mv', 'src/m1.py', 'src/vendor/m1.py')
        git(repo.root, 'mv', 'src/m2.py', 'scripts/m2.py')
        repo.write({'src/new.py': '# @generated\nTODO = 1\n', 'vendor/lib.py': 'z = 1\n',
                    'gen/api_pb2.py': '# @generated\n'})
        _, report = self.check(repo, expect=1)
        locked = {p['key'] for p in problems(report, 'policy', 'locked') if p['rule'] == 'reclassified'}
        # gen/ is a generated path in the policy, so its header is not what exempts it.
        self.assertEqual(locked, {'src/vendor/m1.py', 'scripts/m2.py', 'src/new.py'})
        self.assertEqual([p['key'] for p in problems(report, 'policy', 'advisory') if p['rule'] == 'vendored'],
                         ['vendor/lib.py'])

    def test_kind_changes_within_source_code_are_advisory_and_codegen_takes_one_exception(self):
        repo = self.setup_repo(det(), files={'src/Button.js': 'export const b = 1;\n'})
        from helpers import git
        git(repo.root, 'mv', 'src/Button.js', 'src/Button.jsx')
        repo.write({f'src/api/m{i}.py': '# Code generated by protoc. DO NOT EDIT.\nX = 1\n' for i in range(5)})
        _, report = self.check(repo, expect=1)
        self.assertEqual([p['key'] for p in problems(report, 'policy', 'advisory') if p['rule'] == 'reclassified'],
                         ['src/Button.jsx'])
        self.assertEqual(len([p for p in problems(report, 'policy', 'locked') if p['rule'] == 'reclassified']), 5)
        code, _, err = repo.guard('except', 'add', '--guard', 'policy', '--rule', 'reclassified', '--key', 'src/api/*',
                                  '--reason', 'protoc output for the public API', '--approved-by', 'owner')
        self.assertEqual(code, 0, err)
        _, report = self.check(repo)
        self.assertFalse([p for p in problems(report, 'policy', 'locked', blocking=True) if p['rule'] == 'reclassified'])

    def test_detector_invocation_forms_are_protected_but_data_is_not(self):
        guards = [DET_GUARD,
                  {'name': 'lint', 'run': f'{PY} {{root}}/scripts/lint.py {{root}}', 'parse': 'exit', 'tier': 'fast'},
                  {'name': 'mod', 'run': f'cd {{root}} && {PY} -m checks.run', 'parse': 'exit', 'tier': 'fast'},
                  {'name': 'data', 'run': 'cat {root}/size.txt', 'parse': 'exit', 'tier': 'fast'},
                  {'name': 'api', 'run': f'{PY} {{root}}/scripts/api.py --root {{root}} src/index.py', 'parse': 'exit',
                   'tier': 'fast'}]
        repo = self.setup_repo(det(), guards, files={
            'scripts/lint.py': 'pass\n', 'scripts/api.py': 'pass\n', 'scripts/helper.py': 'pass\n',
            'checks/__init__.py': '', 'checks/run.py': 'pass\n', 'checks/other.py': 'pass\n', 'size.txt': '1\n',
            'src/index.py': 'x = 1\n'})
        repo.write({'scripts/lint.py': None, 'scripts/helper.py': 'print(2)\n', 'checks/run.py': 'print(1)\n',
                    'checks/other.py': 'print(1)\n', 'size.txt': '2\n', 'src/index.py': 'x = 2\n'})
        _, report = self.check(repo, expect=1)
        keys = {p['key'] for p in problems(report, 'protected', 'protected')}
        # A deleted detector stays protected, and so do helpers in a tooling directory. A module run
        # with -m protects that module only; scan targets and data files are not detector code.
        self.assertEqual(keys, {'scripts/lint.py', 'scripts/helper.py', 'checks/run.py'})


class TiersAndSelection(Base):
    def guards(self):
        return [{**DET_GUARD}, {'name': 'slow', 'run': 'true', 'parse': 'exit', 'tier': 'standard'},
                {'name': 'deep', 'run': 'true', 'parse': 'exit', 'tier': 'strict'},
                {'name': 'deps-only', 'run': 'true', 'parse': 'exit', 'tier': 'fast', 'when': ['deps']}]

    def test_tier_follows_the_change(self):
        repo = self.setup_repo(det(), self.guards())
        repo.write({'README.md': 'docs only\n'})
        _, report = self.check(repo, expect=0)
        self.assertEqual(report['tier'], 'fast')
        self.assertEqual(status(report, 'slow'), 'skipped')
        self.assertEqual(status(report, 'deps-only'), 'skipped')
        repo.write({'src/util.py': 'x = 1\n'})
        _, report = self.check(repo, expect=0)
        self.assertEqual((report['tier'], status(report, 'slow'), status(report, 'deep')), ('standard', 'pass', 'skipped'))
        repo.write({'src/auth/login.py': 'x = 1\n', 'package.json': '{}'})
        _, report = self.check(repo, expect=0)
        self.assertEqual((report['tier'], status(report, 'deep'), status(report, 'deps-only')), ('strict', 'pass', 'pass'))

    def test_requesting_a_lower_tier_is_incomplete(self):
        repo = self.setup_repo(det(), self.guards())
        repo.write({'src/auth/login.py': 'x = 1\n'})
        code, report = self.check(repo, '--tier', 'fast')
        self.assertEqual((code, report['verdict']), (3, 'incomplete'))

    def test_weakened_assertions_raise_the_tier(self):
        repo = self.setup_repo(det(), self.guards(),
                               files={'tests/test_a.py': 'def test_a():\n    assert f() == 1\n    assert g() == 2\n'})
        repo.write({'tests/test_a.py': 'def test_a():\n    f()\n'})
        _, report = self.check(repo)
        self.assertEqual(report['tier'], 'strict')


class KeepGuards(Base):
    def junit(self, *cases):
        body = ''.join(f'<testcase classname="t" name="{n}">{"<skipped/>" if s else ""}</testcase>' for n, s in cases)
        return f'<testsuite>{body}</testsuite>'

    def test_test_inventory(self):
        guard = {'name': 'tests', 'run': 'cat {root}/junit.xml', 'parse': 'junit', 'tier': 'fast'}
        repo = self.setup_repo(det(), [guard], files={'junit.xml': self.junit(('a', 0), ('b', 0))})
        repo.write({'junit.xml': self.junit(('a', 0), ('b', 1), ('c', 0))})
        _, report = self.check(repo, expect=1)
        lost = problems(report, 'tests', 'lost', blocking=True)
        self.assertEqual([(p['rule'], p['key']) for p in lost], [('active', 't::b')])
        self.assertIn('skipped', lost[0]['message'])
        self.assertTrue(any(p['key'] == 't::c' for p in problems(report, 'tests', 'advisory')))
        repo.write({'junit.xml': self.junit(('a', 0), ('c', 0))})
        _, report = self.check(repo, expect=1)
        self.assertEqual(sorted((p['rule'], p['key']) for p in problems(report, 'tests', 'lost')),
                         [('active', 't::b'), ('present', 't::b')])
        repo.guard('except', 'add', '--guard', 'tests', '--rule', '*', '--key', 't::b',
                   '--reason', 'feature b was removed in this change', '--approved-by', 'owner')
        code, _, _ = repo.guard('update')
        self.assertEqual(code, 0)
        entries = json.loads(repo.read('guards/baselines/tests.json'))['entries']['present']
        self.assertEqual(sorted(entries), ['t::a', 't::c'])

    def test_failing_test_is_hard(self):
        guard = {'name': 'tests', 'run': 'cat {root}/junit.xml', 'parse': 'junit', 'tier': 'fast'}
        repo = self.setup_repo(det(), [guard], files={'junit.xml': '<testsuite><testcase classname="t" name="a"/>'
                                                                    '</testsuite>'})
        repo.write({'junit.xml': '<testsuite><testcase classname="t" name="a"><failure message="boom"/>'
                                 '</testcase></testsuite>'})
        _, report = self.check(repo, expect=1)
        self.assertEqual(problems(report, 'tests', 'hard')[0]['key'], 't::a')

    def test_api_snapshot(self):
        guard = {'name': 'api', 'builtin': 'snapshot', 'run': 'cat {root}/api.txt', 'tier': 'fast'}
        repo = self.setup_repo(det(), [guard], files={'api.txt': 'pkg:f(a)\npkg:g()\n'})
        repo.write({'api.txt': 'pkg:f(a, b)\npkg:g()\n'})
        _, report = self.check(repo, expect=1)
        self.assertEqual([p['key'] for p in problems(report, 'api', 'lost')], ['pkg:f(a)'])
        self.assertEqual([p['key'] for p in problems(report, 'api', 'unrecorded')], ['pkg:f(a, b)'])
        repo.write({'api.txt': 'pkg:f(a)\npkg:g()\npkg:h()\n'})
        _, report = self.check(repo, expect=1)  # additions must be recorded (strict sync)
        repo.guard('update')
        self.check(repo, expect=0)

    def test_metric_budget(self):
        guard = {'name': 'bundle', 'builtin': 'metric', 'run': 'cat {root}/size.txt', 'tier': 'fast',
                 'budget': {'pct': 10}}
        repo = self.setup_repo(det(), [guard], files={'size.txt': '{"main.js": 1000}'})
        repo.write({'size.txt': '{"main.js": 1080}'})
        self.check(repo, expect=0)
        repo.write({'size.txt': '{"main.js": 1150}'})
        _, report = self.check(repo, expect=1)
        self.assertEqual(problems(report, 'bundle', 'worse')[0]['key'], 'main.js')


class Trusted(Base):
    def test_trusted_run_uses_base_rules(self):
        repo = self.setup_repo(det([finding('r', 'a')]))
        repo.commit('ready')
        # The change hides a new finding by editing the detector and "approves" its own protected edit.
        sneaky = DET_PY.replace("print(json.dumps(doc))", "doc['findings'] = [f for f in doc['findings'] "
                                "if f['key'] != 'b']\nprint(json.dumps(doc))")
        repo.write({'detectors/det.py': sneaky, 'det.json': det([finding('r', 'a'), finding('r', 'b')]),
                    'guards/exceptions.json': json.dumps({'version': 1, 'exceptions': [
                        {'guard': 'protected', 'rule': 'changed', 'key': 'detectors/det.py',
                         'reason': 'refactor of the detector output', 'approved_by': 'me'}]})})
        repo.commit('sneaky')
        self.check(repo, expect=0)  # the local check is fooled: only review can catch the self-approval
        _, report = self.check(repo, '--trusted', '--base', 'main', expect=1)
        self.assertEqual([p['key'] for p in problems(report, 'det', 'new')], ['b'])
        self.assertIn("!= 'b'", repo.read('detectors/det.py'))  # working tree restored

    def test_trusted_run_accepts_improvements(self):
        repo = self.setup_repo(det([finding('r', 'a', 3)]))
        repo.write({'det.json': det([finding('r', 'a', 1)])})
        repo.guard('update')
        repo.commit('improve')
        _, report = self.check(repo, '--trusted', '--base', 'main', expect=0)
        self.assertTrue(problems(report, 'det', 'improved'))

    @unittest.skipIf(sys.version_info < (3, 11), 'TOML manifests need Python 3.11+ (tomllib)')
    def test_trusted_builtins_judge_the_change_not_the_restored_config(self):
        # pyproject.toml is both ruff configuration (restored from base) and a manifest (judged by deps).
        guards = [{**DET_GUARD, 'config_files': ['**/pyproject.toml']},
                  {'name': 'deps', 'builtin': 'deps', 'tier': 'fast'}]
        manifest = '[project]\nname = "x"\ndependencies = ["requests>=2"]\n'
        repo = self.setup_repo(det(), guards, files={'pyproject.toml': manifest})
        repo.write({'pyproject.toml': manifest.replace('"requests>=2"', '"requests>=2", "evil @ git+https://e.test/x"')})
        repo.commit('dep')
        _, report = self.check(repo, '--trusted', '--base', 'main', expect=1)
        self.assertEqual([p['rule'] for p in problems(report, 'deps', 'hard')], ['dep-source'])
        self.assertIn('evil', repo.read('pyproject.toml'))

    def test_trusted_needs_an_explicit_base_and_only_needs_real_guards(self):
        repo = self.setup_repo(det())
        repo.commit('ready')
        code, out, err = repo.guard('check', '--trusted')
        self.assertEqual(code, 2)
        self.assertIn('explicit --base', err)
        code, out, err = repo.guard('check', '--only', 'dett')
        self.assertEqual(code, 2)
        self.assertIn('unknown guards: dett', err)

    def test_trusted_sets_aside_config_files_the_change_adds(self):
        # The detector honors det.cfg if present; the change adds one that hides finding b.
        honoring = DET_PY.replace("print(json.dumps(doc))", "import os\nif os.path.exists('sub/det.cfg'):\n"
                                  "    doc['findings'] = [f for f in doc['findings'] if f['key'] != 'b']\n"
                                  "print(json.dumps(doc))")
        repo = self.setup_repo(det([finding('r', 'a')]), [{**DET_GUARD, 'config_files': ['**/det.cfg']}],
                               files={'detectors/det.py': honoring})
        repo.write({'det.json': det([finding('r', 'a'), finding('r', 'b')]), 'sub/det.cfg': 'hide b\n'})
        repo.commit('nested config')
        _, report = self.check(repo, '--trusted', '--base', 'main', expect=1)
        self.assertEqual([p['key'] for p in problems(report, 'det', 'new')], ['b'])
        self.assertFalse(problems(report, 'det', 'rule-change'))
        self.assertEqual(repo.read('sub/det.cfg'), 'hide b\n')  # put back afterwards

    def test_trusted_refuses_dirty_guard_config(self):
        repo = self.setup_repo(det())
        repo.write({'detectors/det.py': DET_PY + '# dirty\n'})
        self.assertEqual(repo.guard('check', '--trusted')[0], 2)


class Reports(Base):
    def test_formats(self):
        repo = self.setup_repo(det([finding('r', 'a')]))
        repo.write({'det.json': det([finding('r', 'a'), finding('r', 'b')])})
        code, text, _ = repo.guard('check', '--format', 'text')
        self.assertEqual(code, 1)
        self.assertIn('FAIL', text)
        self.assertIn('next steps:', text)
        code, md, _ = repo.guard('check', '--format', 'markdown')
        self.assertIn('| category | guard | rule | key | detail |', md)
        _, report = self.check(repo)
        self.assertEqual(report['schema'], 'guard-ratchet/report@1')
        self.assertEqual(report['summary']['by_category'], {'new': 1})


class Init(RepoCase):
    def test_python_project(self):
        repo = self.repo({'src/app.py': 'x = 1\n', 'tests/test_app.py': 'def test_a():\n    assert 1\n',
                          'requirements.txt': 'pytest\npytest-cov\n', 'db/migrations/0001.sql': 'create table t();\n'})
        code, out, err = repo.guard('init', '--write')
        self.assertEqual(code, 0, err)
        policy = json.loads(repo.read('guards/policy.json'))
        names = [g['name'] for g in policy['guards']]
        for expected in ('secrets', 'suppressions', 'size', 'test-changes', 'deps', 'migrations', 'tests',
                         'diff-coverage'):
            self.assertIn(expected, names)
        rules = os.path.join(repo.root, 'tools/guard/rules/semgrep')
        self.assertTrue(all(f.endswith('.yaml') for f in os.listdir(rules)))
        self.assertTrue(os.path.exists(os.path.join(repo.root, 'tools/guard/guard.py')))
        self.assertEqual(repo.guard('init', '--write')[0], 2)  # never overwrites silently

    def test_js_project_with_vitest(self):
        repo = self.repo({'package.json': json.dumps({'devDependencies': {'vitest': '^3', '@vitest/coverage-v8': '^3',
                                                                          'typescript': '^5'}}),
                          'tsconfig.json': '{}', 'src/a.ts': 'export const a = 1\n'})
        code, out, _ = repo.guard('init')
        self.assertEqual(code, 0)
        self.assertIn('vitest run --reporter=junit', out)
        self.assertIn('"name": "typecheck"', out)


class PyApi(RepoCase):
    def test_surface(self):
        repo = self.repo({'pkg/__init__.py': '__all__ = ["run"]\ndef run(a, *, b=1): ...\ndef hidden(): ...\n',
                          'pkg/client.py': 'class Client(Base):\n    def get(self, url: str) -> bytes: ...\n'
                                           '    def _x(self): ...\nTIMEOUT = 3\n',
                          'pkg/_private.py': 'def f(): ...\n'})
        code, out, _ = repo.guard('pyapi', os.path.join(repo.root, 'pkg'))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ['pkg.client:Client(Base)', 'pkg.client:Client.get(self, url: str) -> bytes',
                                            'pkg.client:TIMEOUT', 'pkg:run(a, *, b=1)'])


if __name__ == '__main__':
    unittest.main()
