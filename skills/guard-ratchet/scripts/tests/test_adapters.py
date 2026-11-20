"""Adapter tests: tool output -> Scan.

Real tool output (ruff, gitleaks, zizmor, semgrep SARIF; eslint JSON; pytest JUnit; lizard CSV;
tsc, mypy and clang text) lives in tests/fixtures/. Absolute paths in those files were rewritten to
/work/proj, which is the project root every test here hands to Paths.

Contract under test (guardlib/adapters.py docstring): every adapter fails closed. Output that
cannot be parsed, or a tool that says it did not finish, is an integrity problem, never "0 findings".
Keys identify a problem by place (file, function, test id), never by line number.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import helpers

from guardlib import adapters
from guardlib.model import DETECTOR_SCHEMA, KEEP

ROOT = '/work/proj'
PATHS = adapters.Paths(ROOT, ROOT)


def fixture(name: str) -> str:
    with open(os.path.join(helpers.FIXTURES, name), encoding='utf-8') as fh:
        return fh.read()


def run(fmt: str, text: str | list[str], code: int = 0, **guard):
    outputs = text if isinstance(text, list) else [text]
    return adapters.parse(fmt, outputs, code, {'name': 'g', **guard}, PATHS)


def detector_v2(**doc) -> str:
    base = {'schema': DETECTOR_SCHEMA, 'guard': 'g', 'coverage': {'scanned': 3}}
    return json.dumps({**base, **doc})


def sarif(results, rules=None, invocations=None, artifacts=None, base_ids=None, extra_runs=()) -> str:
    run_ = {'tool': {'driver': {'name': 'tool', 'version': '1', 'rules': rules or []}}, 'results': results}
    if invocations is not None:
        run_['invocations'] = invocations
    if artifacts is not None:
        run_['artifacts'] = artifacts
    if base_ids is not None:
        run_['originalUriBaseIds'] = base_ids
    return json.dumps({'version': '2.1.0', 'runs': [run_, *extra_runs]})


def result(rule='R1', uri='src/a.py', line=3, **extra) -> dict:
    out = {'ruleId': rule, 'message': {'text': 'bad thing'}, **extra}
    if uri is not None:
        out['locations'] = [{'physicalLocation': {'artifactLocation': {'uri': uri}, 'region': {'startLine': line}}}]
    return out


def rules_keys(items):
    return [(i.rule, i.key) for i in items]


# ─── Paths ───────────────────────────────────────────────────────────────────
class PathsTest(unittest.TestCase):
    def test_relative_forms_normalize_to_the_same_key(self):
        for raw in ('src/a.py', './src/a.py', '././src/a.py', 'src//a.py', 'src/./a.py', 'src\\a.py'):
            self.assertEqual(PATHS.rel(raw), 'src/a.py', raw)

    def test_absolute_and_file_uri_inside_the_repo(self):
        self.assertEqual(PATHS.rel('/work/proj/src/a.py'), 'src/a.py')
        self.assertEqual(PATHS.rel('file:///work/proj/src/a.py'), 'src/a.py')

    def test_file_uri_is_percent_decoded(self):
        self.assertEqual(PATHS.rel('file:///work/proj/my%20dir/a%2Bb.py'), 'my dir/a+b.py')

    def test_empty_and_none(self):
        self.assertIsNone(PATHS.rel(None))
        self.assertIsNone(PATHS.rel(''))

    def test_absolute_path_outside_the_repo_is_none(self):
        self.assertIsNone(PATHS.rel('/usr/lib/python3/site.py'))
        self.assertIsNone(PATHS.rel('file:///usr/lib/x.py'))

    def test_sibling_directory_with_the_same_prefix_is_outside(self):
        self.assertIsNone(PATHS.rel('/work/proj-other/a.py'))
        self.assertIsNone(PATHS.rel('/work/project/a.py'))

    def test_symlinked_root_matches_the_real_path_reported_by_tools(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix='paths-test-'))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        real = os.path.join(tmp, 'real')
        link = os.path.join(tmp, 'link')
        os.makedirs(real)
        os.symlink(real, link)
        paths = adapters.Paths(link, link)
        self.assertEqual(paths.rel(os.path.join(real, 'src', 'a.py')), 'src/a.py')
        self.assertEqual(paths.rel(os.path.join(link, 'src', 'a.py')), 'src/a.py')
        self.assertEqual(paths.rel('file://' + os.path.join(real, 'a.py')), 'a.py')

    def test_scan_root_and_project_root_map_to_the_same_key(self):
        # a base-branch scan runs in a worktree: tools report paths under that worktree
        paths = adapters.Paths('/tmp/guard-base-x/tree', '/work/proj')
        self.assertEqual(paths.rel('/tmp/guard-base-x/tree/src/a.py'), 'src/a.py')
        self.assertEqual(paths.rel('/work/proj/src/a.py'), 'src/a.py')
        self.assertIsNone(paths.rel('/tmp/other/src/a.py'))

    def test_relative_path_escaping_the_repo_is_none(self):
        self.assertIsNone(PATHS.rel('../elsewhere/x.py'))

    def test_relative_path_that_climbs_back_into_the_repo_resolves(self):
        # golangci-lint prints paths relative to its cwd, which can pass through a symlinked /tmp.
        self.assertEqual(PATHS.rel('../../work/proj/src/a.py'), 'src/a.py')
        self.assertEqual(PATHS.rel('../proj/src/a.py'), 'src/a.py')


# ─── findings (detector JSON) ────────────────────────────────────────────────
class FindingsTest(unittest.TestCase):
    def test_v2_hard_advisory_findings_and_metrics(self):
        text = detector_v2(
            tool={'name': 'mine', 'version': '1.2'},
            hard=[{'rule': 'no-eval', 'key': 'src/a.py#f', 'path': '/work/proj/src/a.py', 'line': 4, 'message': 'eval'}],
            advisory=['just a note'],
            findings=[{'rule': 'fn-x', 'key': 'src/a.py#f', 'count': 3}],
            metrics=[{'metric': 'fn-complexity', 'key': 'src/a.py#f', 'value': 12, 'path': './src/a.py'}])
        scan = run('findings', text, mode='budget')
        self.assertEqual(scan.integrity, [])
        self.assertEqual(scan.tool, {'name': 'mine', 'version': '1.2'})
        (hard,) = scan.hard
        self.assertEqual((hard.rule, hard.key, hard.path, hard.line, hard.mode), ('no-eval', 'src/a.py#f', 'src/a.py', 4, 'hard'))
        (adv,) = scan.advisory
        self.assertEqual((adv.rule, adv.key, adv.mode), ('advisory', 'just a note', 'advisory'))
        (finding,) = scan.findings
        self.assertEqual((finding.rule, finding.key, finding.count, finding.mode), ('fn-x', 'src/a.py#f', 3, 'budget'))
        self.assertEqual(scan.metrics, [{'metric': 'fn-complexity', 'key': 'src/a.py#f', 'value': 12, 'path': 'src/a.py'}])
        self.assertEqual(scan.coverage['scanned'], 3)

    def test_v1_document_without_schema(self):
        scan = run('findings', json.dumps({'scanned': 10, 'findings': [{'rule': 'r', 'key': 'k'}]}))
        self.assertEqual(scan.integrity, [])
        self.assertEqual(rules_keys(scan.findings), [('r', 'k')])
        self.assertEqual(scan.coverage, {'scanned': 10, 'min': 1})

    def test_v1_scanned_zero_is_below_the_default_minimum(self):
        scan = run('findings', json.dumps({'scanned': 0, 'findings': []}))
        self.assertTrue(any('below' in p for p in scan.integrity), scan.integrity)

    def test_v1_min_scanned_is_enforced(self):
        scan = run('findings', json.dumps({'scanned': 5, 'min_scanned': 8}))
        self.assertTrue(any('minimum 8' in p for p in scan.integrity), scan.integrity)
        self.assertEqual(run('findings', json.dumps({'scanned': 8, 'min_scanned': 8})).integrity, [])

    def test_v2_missing_coverage_is_integrity(self):
        scan = run('findings', json.dumps({'schema': DETECTOR_SCHEMA, 'findings': []}))
        self.assertTrue(any('coverage.scanned' in p for p in scan.integrity), scan.integrity)

    def test_v2_incomplete_scan(self):
        scan = run('findings', detector_v2(coverage={'scanned': 9, 'planned': 10}))
        self.assertTrue(any('incomplete scan' in p for p in scan.integrity), scan.integrity)
        self.assertEqual(run('findings', detector_v2(coverage={'scanned': 10, 'planned': 10})).integrity, [])

    def test_v2_coverage_min_boundary(self):
        self.assertTrue(run('findings', detector_v2(coverage={'scanned': 4, 'min': 5})).integrity)
        self.assertEqual(run('findings', detector_v2(coverage={'scanned': 5, 'min': 5})).integrity, [])

    def test_unsupported_schema_version(self):
        scan = run('findings', json.dumps({'schema': 'guard-ratchet/detector@9', 'coverage': {'scanned': 1}}))
        self.assertTrue(any('unsupported detector schema' in p for p in scan.integrity), scan.integrity)

    def test_guard_name_mismatch_is_integrity(self):
        scan = run('findings', detector_v2(guard='other'))
        self.assertTrue(any("'other'" in p for p in scan.integrity), scan.integrity)

    def test_parse_failures_and_unsupported_inputs_are_integrity(self):
        scan = run('findings', detector_v2(parse_failures=['src/x.py: bad syntax'],
                                           unsupported=[{'path': 'a.cob', 'message': 'language'}, 'b.f77']))
        text = '\n'.join(scan.integrity)
        self.assertIn('parse failure: src/x.py: bad syntax', text)
        self.assertIn('unsupported input: a.cob language', text)
        self.assertIn('unsupported input: b.f77', text)

    def test_finding_without_rule_or_key_is_malformed(self):
        for item in ({'rule': 'r'}, {'key': 'k'}, {}):
            scan = run('findings', detector_v2(findings=[item]))
            self.assertTrue(any('malformed detector item' in p for p in scan.integrity), item)

    def test_bad_counts_are_malformed(self):
        for count in (-1, 'many', True, None):
            scan = run('findings', detector_v2(findings=[{'rule': 'r', 'key': 'k', 'count': count}]))
            self.assertTrue(any('malformed detector item' in p for p in scan.integrity), count)

    def test_zero_and_fractional_counts_are_accepted(self):
        scan = run('findings', detector_v2(findings=[{'rule': 'r', 'key': 'a', 'count': 0},
                                                      {'rule': 'r', 'key': 'b', 'count': 2.5}]))
        self.assertEqual(scan.integrity, [])
        self.assertEqual([f.count for f in scan.findings], [0, 2.5])

    def test_malformed_metrics_are_integrity_and_dropped(self):
        scan = run('findings', detector_v2(metrics=[
            {'metric': 'm', 'key': 'k', 'value': 1}, {'metric': 'm', 'key': 'k2'}, {'key': 'k3', 'value': 1},
            {'metric': 'm', 'key': 'k4', 'value': 'high'}, 'oops']))
        self.assertEqual([m['key'] for m in scan.metrics], ['k'])
        self.assertEqual(len([p for p in scan.integrity if p.startswith('malformed metric')]), 4)

    def test_not_json_not_object_and_empty(self):
        self.assertTrue(any('not valid JSON' in p for p in run('findings', 'oops {').integrity))
        self.assertTrue(any('not valid JSON' in p for p in run('findings', '').integrity))
        self.assertTrue(any('must be a JSON object' in p for p in run('findings', '[]').integrity))
        self.assertTrue(any('must be a JSON object' in p for p in run('findings', '"x"').integrity))

    def test_json_null_lists_do_not_crash_and_are_not_clean(self):
        # A detector that prints `"findings": null` is broken; it must not read as a clean scan.
        try:
            scan = run('findings', detector_v2(findings=None))
        except TypeError as err:
            self.fail(f'adapter crashed instead of reporting integrity: {err}')
        self.assertTrue(scan.integrity, 'null findings list accepted as an empty list')

    def test_detector_paths_are_normalized_and_outside_paths_dropped(self):
        scan = run('findings', detector_v2(findings=[
            {'rule': 'r', 'key': 'a', 'path': 'file:///work/proj/x.py'},
            {'rule': 'r', 'key': 'b', 'path': '/etc/passwd'}]))
        self.assertEqual([f.path for f in scan.findings], ['x.py', None])


# ─── SARIF ───────────────────────────────────────────────────────────────────
class SarifRealToolsTest(unittest.TestCase):
    def test_jscpd(self):
        # jscpd 4.2.5 `--reporters sarif`: one result per clone, on the file where it was found.
        scan = run('sarif', fixture('jscpd.sarif'))
        self.assertEqual(scan.integrity, [])
        self.assertEqual(scan.tool, {'name': 'jscpd', 'version': '4.2.5'})
        self.assertEqual([(f.rule, f.key) for f in scan.findings], [('duplication', 'src/a.js')])

    def test_golangci_lint(self):
        # golangci-lint 2.15 `run --output.sarif.path=...`; exit 1 when issues are found.
        scan = run('sarif', fixture('golangci.sarif'), code=1)
        self.assertEqual(scan.integrity, [])
        self.assertEqual(scan.tool['name'], 'golangci-lint')
        self.assertEqual([(f.rule, f.key, f.line) for f in scan.findings], [('errcheck', 'main.go', 6)])

    def test_ruff(self):
        scan = run('sarif', fixture('ruff.sarif'), code=1)
        self.assertEqual(scan.integrity, [])
        self.assertEqual(scan.tool['name'], 'ruff')
        self.assertEqual(rules_keys(scan.findings), [('F401', 'src/app.py'), ('F401', 'src/app.py'),
                                                      ('F821', 'src/app.py'), ('F811', 'src/app.py')])
        self.assertEqual([f.line for f in scan.findings], [1, 2, 11, 14])
        self.assertEqual(scan.advisory, [])

    def test_gitleaks_relative_path_without_level(self):
        scan = run('sarif', fixture('gitleaks.sarif'), code=1)
        self.assertEqual(scan.integrity, [])
        self.assertEqual(scan.tool['name'], 'gitleaks')
        self.assertEqual(rules_keys(scan.findings), [('aws-access-token', 'src/leak.py')])
        self.assertEqual(scan.findings[0].line, 1)

    def test_zizmor_levels_split_between_findings_and_advisory(self):
        doc = json.loads(fixture('zizmor.sarif'))
        results = doc['runs'][0]['results']
        warnings = [r['ruleId'] for r in results if r.get('level') == 'warning']
        self.assertTrue(warnings, 'fixture should contain warnings')
        scan = run('sarif', fixture('zizmor.sarif'), advisory_levels=['warning', 'note', 'none'])
        self.assertEqual(scan.integrity, [])
        self.assertEqual(sorted(i.rule for i in scan.advisory), sorted(warnings))
        self.assertEqual(len(scan.advisory) + len(scan.findings), len(results))
        self.assertTrue(all(i.mode == 'advisory' for i in scan.advisory))
        self.assertTrue(all(i.key == '.github/workflows/ci.yml' for i in scan.advisory + scan.findings))
        # default advisory levels are note/none: warnings stay blocking findings
        default = run('sarif', fixture('zizmor.sarif'))
        self.assertEqual(default.advisory, [])
        self.assertEqual(len(default.findings), len(results))

    def test_semgrep_srcroot_relative_uris_and_no_artifacts(self):
        scan = run('sarif', fixture('semgrep.sarif'))
        doc = json.loads(fixture('semgrep.sarif'))
        self.assertEqual(scan.integrity, [])
        self.assertEqual(len(scan.findings), len(doc['runs'][0]['results']))
        self.assertEqual({f.key for f in scan.findings},
                         {'rules/semgrep/python.py', 'rules/semgrep/javascript.js', 'rules/semgrep/javascript.ts'})
        self.assertTrue(all(f.line for f in scan.findings))
        self.assertEqual(scan.coverage, {'scanned': None, 'unit': 'not reported'})

    def test_keys_never_contain_line_numbers(self):
        for name in ('ruff.sarif', 'gitleaks.sarif', 'zizmor.sarif', 'semgrep.sarif'):
            scan = run('sarif', fixture(name))
            for item in scan.findings + scan.advisory:
                self.assertEqual(item.key, item.path, name)

    def test_guard_mode_applies_to_findings(self):
        scan = run('sarif', fixture('ruff.sarif'), mode='budget')
        self.assertTrue(all(f.mode == 'budget' for f in scan.findings))


class SarifSyntheticTest(unittest.TestCase):
    def test_no_runs_or_no_results_array_is_integrity(self):
        self.assertTrue(run('sarif', json.dumps({'version': '2.1.0', 'runs': []})).integrity)
        no_results = json.dumps({'version': '2.1.0', 'runs': [{'tool': {'driver': {'name': 't'}}}]})
        self.assertTrue(any('no results array' in p for p in run('sarif', no_results).integrity))
        clean = json.dumps({'version': '2.1.0', 'runs': [{'tool': {'driver': {'name': 't'}}, 'results': []}]})
        self.assertEqual(run('sarif', clean).integrity, [])

    def test_unsuccessful_run_is_integrity_with_the_tool_message(self):
        inv = [{'executionSuccessful': False, 'toolExecutionNotifications': [
            {'level': 'error', 'message': {'text': 'rule pack failed to download'}},
            {'level': 'warning', 'message': {'text': 'just a warning'}}]}]
        scan = run('sarif', sarif([], invocations=inv))
        self.assertEqual(len(scan.integrity), 1)
        self.assertIn('rule pack failed to download', scan.integrity[0])
        self.assertNotIn('just a warning', scan.integrity[0])

    def test_unsuccessful_run_without_notifications(self):
        scan = run('sarif', sarif([result()], invocations=[{'executionSuccessful': False}]))
        self.assertTrue(scan.integrity)

    def test_unsuccessful_second_run_is_caught(self):
        second = {'tool': {'driver': {'name': 'two'}}, 'invocations': [{'executionSuccessful': False}], 'results': []}
        scan = run('sarif', sarif([result()], invocations=[{'executionSuccessful': True}], extra_runs=[second]))
        self.assertEqual(len(scan.integrity), 1)
        self.assertIn('two', scan.integrity[0])

    def test_successful_invocation_and_missing_flag_are_clean(self):
        self.assertEqual(run('sarif', sarif([], invocations=[{'executionSuccessful': True}])).integrity, [])
        self.assertEqual(run('sarif', sarif([], invocations=[{}])).integrity, [])

    def test_malformed_documents_are_integrity(self):
        self.assertTrue(any('not valid JSON' in p for p in run('sarif', '{"runs": [').integrity))
        self.assertTrue(any('not valid JSON' in p for p in run('sarif', '').integrity))
        self.assertTrue(any('no runs array' in p for p in run('sarif', '{}').integrity))
        self.assertTrue(any('no runs array' in p for p in run('sarif', '[]').integrity))
        self.assertTrue(any('no runs array' in p for p in run('sarif', '{"runs": {}}').integrity))

    def test_suppressed_and_absent_results_are_ignored(self):
        scan = run('sarif', sarif([
            result('R1', suppressions=[{'kind': 'inSource'}]),
            result('R2', baselineState='absent'),
            result('R3', suppressions=[]),
            result('R4', baselineState='new')]))
        self.assertEqual([i.rule for i in scan.findings], ['R3', 'R4'])

    def test_non_fail_kinds_are_not_findings(self):
        scan = run('sarif', sarif([result('ok', kind='pass'), result('fyi', kind='informational'),
                                   result('bad', kind='fail')]))
        self.assertEqual([i.rule for i in scan.findings + scan.advisory], ['bad'])

    def test_rule_id_resolution(self):
        rules = [{'id': 'first'}, {'id': 'second'}]
        scan = run('sarif', sarif([
            {'ruleIndex': 1, 'message': {'text': 'm'}},
            {'rule': {'index': 0}, 'message': {'text': 'm'}},
            {'rule': {'id': 'nested'}, 'message': {'text': 'm'}},
            {'message': {'text': 'm'}},
            {'ruleIndex': 99, 'message': {'text': 'm'}}], rules=rules))
        self.assertEqual([i.rule for i in scan.findings], ['second', 'first', 'nested', 'unknown', 'unknown'])

    def test_level_falls_back_to_rule_default_then_warning(self):
        rules = [{'id': 'quiet', 'defaultConfiguration': {'level': 'note'}}, {'id': 'loud'}]
        scan = run('sarif', sarif([result('quiet'), result('loud'), result('quiet', level='error')], rules=rules))
        self.assertEqual([i.rule for i in scan.advisory], ['quiet'])
        self.assertEqual([i.rule for i in scan.findings], ['loud', 'quiet'])

    def test_advisory_levels_are_configurable(self):
        text = sarif([result('a', level='warning'), result('b', level='error'), result('c', level='note')])
        scan = run('sarif', text, advisory_levels=['warning'])
        self.assertEqual([i.rule for i in scan.advisory], ['a'])
        self.assertEqual([i.rule for i in scan.findings], ['b', 'c'])

    def test_location_variants(self):
        base_ids = {'SRC': {'uri': 'file:///work/proj/'}}
        results = [
            result(uri='file:///work/proj/a.py'),
            result(uri='./b.py'),
            result(uri='dir/my%20file.py'),
            {'ruleId': 'viaindex', 'message': {'text': 'm'}, 'locations': [{'physicalLocation': {
                'artifactLocation': {'index': 0}, 'region': {'startLine': 7}}}]},
            {'ruleId': 'viabase', 'message': {'text': 'm'}, 'locations': [{'physicalLocation': {
                'artifactLocation': {'uri': 'c.py', 'uriBaseId': 'SRC'}, 'region': {'startLine': 1}}}]},
        ]
        artifacts = [{'location': {'uri': 'file:///work/proj/d.py'}}]
        scan = run('sarif', sarif(results, artifacts=artifacts, base_ids=base_ids))
        self.assertEqual([i.key for i in scan.findings], ['a.py', 'b.py', 'dir/my file.py', 'd.py', 'c.py'])
        self.assertEqual(scan.findings[3].line, 7)

    def test_missing_or_outside_location_gets_the_placeholder_key(self):
        scan = run('sarif', sarif([result(uri=None), result(uri='file:///usr/lib/x.py')]))
        self.assertEqual([i.key for i in scan.findings], ['(no location)', '(no location)'])
        self.assertEqual([i.path for i in scan.findings], [None, None])

    def test_duplicate_results_keep_one_item_each(self):
        scan = run('sarif', sarif([result(line=1), result(line=9)]))
        self.assertEqual(len(scan.findings), 2)
        self.assertEqual({i.key for i in scan.findings}, {'src/a.py'})

    def test_message_uses_first_line_truncated(self):
        long = 'x' * 500
        scan = run('sarif', sarif([result(message={'text': f'  first line {long}\nsecond'})]))
        self.assertTrue(scan.findings[0].message.startswith('first line'))
        self.assertLessEqual(len(scan.findings[0].message), 300)
        self.assertNotIn('second', scan.findings[0].message)

    def test_coverage_counts_distinct_artifacts(self):
        artifacts = [{'location': {'uri': 'a.py'}}, {'location': {'uri': './a.py'}}, {'location': {'uri': 'b.py'}},
                     {'location': {'uri': '/usr/x.py'}}]
        scan = run('sarif', sarif([], artifacts=artifacts))
        self.assertEqual(scan.coverage, {'scanned': 2, 'unit': 'files'})

    def test_empty_results_are_a_clean_scan(self):
        scan = run('sarif', sarif([]))
        self.assertEqual((scan.integrity, scan.findings, scan.advisory), ([], [], []))

    def test_tool_version_prefers_semantic_version(self):
        doc = json.loads(sarif([]))
        doc['runs'][0]['tool']['driver'].update({'semanticVersion': '9.9.9', 'version': 'build-1'})
        self.assertEqual(run('sarif', json.dumps(doc)).tool, {'name': 'tool', 'version': '9.9.9'})


# ─── ESLint ──────────────────────────────────────────────────────────────────
class EslintTest(unittest.TestCase):
    def test_real_eslint_output(self):
        scan = run('eslint', fixture('eslint.json'), code=1)
        self.assertEqual(rules_keys(scan.findings), [('eqeqeq', 'a.js'), ('no-unused-vars', 'c.js')])
        self.assertEqual([f.line for f in scan.findings], [2, 1])
        self.assertEqual(scan.coverage, {'scanned': 3, 'unit': 'files'})
        self.assertEqual(scan.tool['name'], 'eslint')

    def test_fatal_parse_error_is_integrity_not_a_finding(self):
        scan = run('eslint', fixture('eslint.json'))
        self.assertEqual(len(scan.integrity), 1)
        self.assertIn('bad.js', scan.integrity[0])
        self.assertIn('Parsing error', scan.integrity[0])
        self.assertNotIn('bad.js', [f.key for f in scan.findings])

    def test_advisory_levels(self):
        scan = run('eslint', fixture('eslint.json'), advisory_levels=['warning'])
        self.assertEqual([i.rule for i in scan.advisory], ['eqeqeq'])
        self.assertEqual([i.rule for i in scan.findings], ['no-unused-vars'])

    def test_message_without_rule_id_uses_a_generic_rule(self):
        doc = [{'filePath': '/work/proj/a.js', 'messages': [{'ruleId': None, 'severity': 1, 'message': 'ignored', 'line': 1}]}]
        scan = run('eslint', json.dumps(doc))
        self.assertEqual(rules_keys(scan.findings), [('eslint', 'a.js')])

    def test_not_json_and_wrong_shape(self):
        self.assertTrue(any('not valid JSON' in p for p in run('eslint', 'Oops! Something went wrong!').integrity))
        self.assertTrue(any('not valid JSON' in p for p in run('eslint', '').integrity))
        self.assertTrue(any('must be an array' in p for p in run('eslint', '{"results": []}').integrity))

    def test_clean_run_reports_scanned_files(self):
        doc = [{'filePath': '/work/proj/a.js', 'messages': []}, {'filePath': '/work/proj/b.js', 'messages': []}]
        scan = run('eslint', json.dumps(doc))
        self.assertEqual((scan.integrity, scan.findings, scan.coverage['scanned']), ([], [], 2))

    def test_path_outside_repo_gets_placeholder_key(self):
        doc = [{'filePath': '/usr/lib/a.js', 'messages': [{'ruleId': 'x', 'severity': 2, 'message': 'm', 'line': 1}]}]
        self.assertEqual(run('eslint', json.dumps(doc)).findings[0].key, '(no location)')


# ─── JUnit ───────────────────────────────────────────────────────────────────
JUNIT_SKELETON = '<testsuites><testsuite name="s">{}</testsuite></testsuites>'


class JunitTest(unittest.TestCase):
    def test_real_pytest_report(self):
        scan = run('junit', fixture('pytest-junit.xml'), code=1)
        self.assertEqual(scan.integrity, [])
        self.assertEqual(scan.coverage, {'scanned': 5, 'unit': 'tests'})
        present = {i.key for i in scan.findings if i.rule == 'present'}
        active = {i.key for i in scan.findings if i.rule == 'active'}
        self.assertEqual(present, {'test_a::test_ok', 'test_a::test_skipped', 'test_a::test_bad',
                                   'test_a::test_p[1]', 'test_a::test_p[2]'})
        self.assertEqual(present - active, {'test_a::test_skipped'})
        self.assertTrue(all(i.mode == KEEP for i in scan.findings))
        (failing,) = scan.hard
        self.assertEqual((failing.rule, failing.key, failing.mode), ('failing', 'test_a::test_bad', 'hard'))
        self.assertIn('assert 1 == 2', failing.message)

    def test_failure_and_error_elements_are_hard(self):
        xml = JUNIT_SKELETON.format('<testcase classname="c" name="f"><failure message="boom"/></testcase>'
                                    '<testcase classname="c" name="e"><error message="crash">trace</error></testcase>'
                                    '<testcase classname="c" name="ok"/>')
        scan = run('junit', xml)
        self.assertEqual(sorted(i.key for i in scan.hard), ['c::e', 'c::f'])

    def test_skipped_test_is_present_but_not_active(self):
        scan = run('junit', JUNIT_SKELETON.format('<testcase classname="c" name="s"><skipped/></testcase>'))
        self.assertEqual(rules_keys(scan.findings), [('present', 'c::s')])
        self.assertEqual(scan.hard, [])

    def test_duplicate_ids_get_numbered_keys(self):
        xml = JUNIT_SKELETON.format('<testcase classname="c" name="t"/>' * 3)
        scan = run('junit', xml)
        self.assertEqual([i.key for i in scan.findings if i.rule == 'present'], ['c::t', 'c::t~2', 'c::t~3'])

    def test_multiple_reports_are_merged(self):
        a = JUNIT_SKELETON.format('<testcase classname="c" name="one"/>')
        b = JUNIT_SKELETON.format('<testcase classname="c" name="two"/>')
        scan = run('junit', [a, b])
        self.assertEqual(scan.coverage['scanned'], 2)
        self.assertEqual({i.key for i in scan.findings}, {'c::one', 'c::two'})

    def test_file_attribute_is_the_owner_when_there_is_no_classname(self):
        xml = JUNIT_SKELETON.format('<testcase name="works" file="/work/proj/tests/a.test.js"/>'
                                    '<testcase name="loose"/>')
        scan = run('junit', xml)
        self.assertEqual({i.key for i in scan.findings}, {'tests/a.test.js::works', 'loose'})

    def test_nested_testsuites_and_bare_testsuite_root(self):
        nested = '<testsuites><testsuite><testsuite><testcase classname="c" name="deep"/></testsuite></testsuite></testsuites>'
        self.assertEqual(run('junit', nested).coverage['scanned'], 1)
        bare = '<testsuite><testcase classname="c" name="x"/></testsuite>'
        self.assertEqual(run('junit', bare).coverage['scanned'], 1)

    def test_zero_test_cases_is_integrity(self):
        for xml in ('<testsuites/>', '<testsuites><testsuite name="s" tests="0"/></testsuites>'):
            scan = run('junit', xml)
            self.assertTrue(any('no test cases' in p for p in scan.integrity), xml)
            self.assertEqual(scan.coverage['scanned'], 0)

    def test_malformed_xml_is_integrity(self):
        for text in ('<testsuites><testcase', '', 'not xml at all'):
            scan = run('junit', text)
            self.assertTrue(any('not valid XML' in p for p in scan.integrity), repr(text))

    def test_one_broken_report_among_good_ones_is_still_integrity(self):
        good = JUNIT_SKELETON.format('<testcase classname="c" name="x"/>')
        scan = run('junit', [good, '<broken'])
        self.assertTrue(scan.integrity)
        self.assertEqual(scan.coverage['scanned'], 1)

    def test_no_report_at_all_is_integrity(self):
        self.assertTrue(run('junit', []).integrity)

    def test_keys_have_no_timing_or_line_data(self):
        a = JUNIT_SKELETON.format('<testcase classname="c" name="t" time="0.1" line="10"/>')
        b = JUNIT_SKELETON.format('<testcase classname="c" name="t" time="9.9" line="99"/>')
        self.assertEqual(rules_keys(run('junit', a).findings), rules_keys(run('junit', b).findings))


# ─── lizard ──────────────────────────────────────────────────────────────────
def metric(scan, name, key):
    return next(m for m in scan.metrics if m['metric'] == name and m['key'] == key)


class LizardTest(unittest.TestCase):
    def test_real_lizard_csv(self):
        scan = run('lizard', fixture('lizard.csv'))
        self.assertEqual(scan.integrity, [])
        self.assertEqual(scan.coverage, {'scanned': 3, 'unit': 'files', 'functions': 5})
        self.assertEqual(len(scan.metrics), 10)  # complexity + length per function
        self.assertEqual(metric(scan, 'fn-complexity', 'src/typed.py#add')['value'], 1)
        self.assertEqual(metric(scan, 'fn-length', 'src/typed.py#add')['value'], 2)
        first = metric(scan, 'fn-complexity', 'src/app.py#parse')
        self.assertEqual((first['value'], first['line'], first['path']), (5, 5, 'src/app.py'))
        self.assertEqual(metric(scan, 'fn-length', 'src/app.py#parse')['value'], 7)

    def test_duplicate_function_names_get_numbered_keys(self):
        scan = run('lizard', fixture('lizard.csv'))
        keys = {m['key'] for m in scan.metrics}
        self.assertIn('src/app.py#parse', keys)
        self.assertIn('src/app.py#parse~2', keys)
        self.assertIn('src/lib.js#f', keys)
        self.assertIn('src/lib.js#f~2', keys)
        self.assertEqual(metric(scan, 'fn-complexity', 'src/app.py#parse~2')['value'], 1)
        self.assertEqual(metric(scan, 'fn-complexity', 'src/app.py#parse~2')['line'], 14)

    def test_keys_do_not_change_when_code_moves(self):
        moved = fixture('lizard.csv').replace('parse@5-11@', 'parse@105-111@').replace(',5,11\n', ',105,111\n')
        a = {m['key'] for m in run('lizard', fixture('lizard.csv')).metrics}
        b = {m['key'] for m in run('lizard', moved).metrics}
        self.assertEqual(a, b)
        for key in a:
            self.assertNotIn('@', key)

    def test_header_row_is_skipped(self):
        text = 'NLOC,CCN,token,PARAM,length,location,file,function,long_name,start,end\n' + fixture('lizard.csv')
        scan = run('lizard', text)
        self.assertEqual((scan.integrity, scan.coverage['functions']), ([], 5))

    def test_absolute_paths_inside_repo_are_normalized_and_outside_skipped(self):
        text = ('3,2,10,1,3,"f@1-3@/work/proj/a.py","/work/proj/a.py","f","f( )",1,3\n'
                '3,2,10,1,3,"g@1-3@/usr/lib/b.py","/usr/lib/b.py","g","g( )",1,3\n')
        scan = run('lizard', text)
        self.assertEqual({m['key'] for m in scan.metrics}, {'a.py#f'})
        self.assertEqual(scan.coverage['scanned'], 1)

    def test_function_names_with_commas_and_quotes(self):
        text = '4,3,20,2,4,"op@1-4@a.cpp","a.cpp","Foo::operator,","Foo::operator,( int a, int b )",1,4\n'
        self.assertEqual(run('lizard', text).metrics[0]['key'], 'a.cpp#Foo::operator,')

    def test_short_row_is_integrity(self):
        scan = run('lizard', '1,2,3\n')
        self.assertTrue(any('unexpected lizard CSV row' in p for p in scan.integrity))

    def test_non_numeric_row_is_integrity_not_a_crash(self):
        text = 'x,y,10,1,3,"f@1-3@a.py","a.py","f","f( )",1,3\n'
        try:
            scan = run('lizard', text)
        except ValueError as err:
            self.fail(f'adapter crashed on a malformed row: {err}')
        self.assertTrue(scan.integrity)

    def test_empty_output_reports_zero_functions(self):
        scan = run('lizard', '')
        self.assertEqual(scan.coverage, {'scanned': 0, 'unit': 'files', 'functions': 0})
        self.assertEqual(scan.metrics, [])


# ─── tsc / mypy / gcc text ───────────────────────────────────────────────────
class TextParsersTest(unittest.TestCase):
    def test_tsc(self):
        scan = run('tsc', fixture('tsc.txt'), code=2)
        self.assertEqual(scan.integrity, [])
        self.assertEqual(rules_keys(scan.findings), [('TS2322', 't.ts'), ('TS2322', 't.ts')])
        self.assertEqual([f.line for f in scan.findings], [1, 2])
        self.assertIn('not assignable', scan.findings[0].message)

    def test_tsc_global_configuration_error_is_integrity(self):
        scan = run('tsc', fixture('tsc-config-error.txt'), code=2)
        self.assertTrue(any('tsc configuration error' in p and 'TS6053' in p for p in scan.integrity), scan.integrity)
        self.assertEqual(scan.findings, [])

    def test_tsc_clean_output(self):
        scan = run('tsc', '')
        self.assertEqual((scan.integrity, scan.findings), ([], []))

    def test_tsc_pretty_output_is_not_silently_clean(self):
        scan = run('tsc', fixture('tsc-pretty.txt'), code=1)
        self.assertTrue(scan.findings or scan.integrity, 'pretty tsc errors parsed as a clean run')

    def test_mypy(self):
        scan = run('mypy', fixture('mypy.txt'), code=1)
        self.assertEqual(scan.integrity, [])
        self.assertEqual(rules_keys(scan.findings), [('arg-type', 'src/typed.py'), ('assignment', 'src/typed.py')])
        self.assertEqual([f.line for f in scan.findings], [5, 6])

    def test_mypy_notes_and_summary_are_not_findings(self):
        text = ('src/a.py:3: error: Missing return statement  [return]\n'
                'src/a.py:3: note: See https://example.com\n'
                'src/a.py:9:5: error: Bad thing\n'
                'Found 2 errors in 1 file (checked 1 source file)\n')
        scan = run('mypy', text, code=1)
        self.assertEqual(rules_keys(scan.findings), [('return', 'src/a.py'), ('error', 'src/a.py')])
        self.assertEqual(scan.findings[1].line, 9)

    def test_mypy_advisory_levels(self):
        text = 'a.py:1: warning: Unused "type: ignore" comment  [unused-ignore]\na.py:2: error: Bad  [misc]\n'
        scan = run('mypy', text, code=1, advisory_levels=['warning'])
        self.assertEqual([i.rule for i in scan.advisory], ['unused-ignore'])
        self.assertEqual([i.rule for i in scan.findings], ['misc'])

    def test_mypy_traceback_with_failing_exit_is_not_a_clean_scan(self):
        text = 'Traceback (most recent call last):\n  File "mypy/__main__.py", line 1\nRuntimeError: INTERNAL ERROR\n'
        scan = run('mypy', text, code=1)
        self.assertTrue(scan.findings or scan.integrity, 'a crashed mypy run was read as clean')

    def test_gcc_clang_warnings(self):
        scan = run('gcc', fixture('gcc.txt'), code=1, advisory_levels=['warning'])
        self.assertEqual(scan.integrity, [])
        self.assertEqual(rules_keys(scan.advisory), [('-Wunused-variable', 'w.c'), ('-Wreturn-type', 'w.c')])
        self.assertEqual(scan.findings, [])
        self.assertEqual(scan.advisory[0].line, 1)

    def test_gcc_errors_and_levels(self):
        text = ('src/a.c:10:5: error: expected ; before return\n'
                'src/a.c:12:1: warning: unused variable x [-Wunused-variable]\n'
                'src/a.c:13:1: note: declared here\n'
                'src/a.c:14:1: fatal error: missing.h: No such file or directory\n')
        scan = run('gcc', text, code=1, advisory_levels=['warning'])
        self.assertEqual(rules_keys(scan.findings), [('error', 'src/a.c'), ('fatal error', 'src/a.c')])
        self.assertEqual(rules_keys(scan.advisory), [('-Wunused-variable', 'src/a.c')])

    def test_gcc_context_and_caret_lines_are_ignored(self):
        scan = run('gcc', fixture('gcc.txt'), code=1)
        self.assertEqual(len(scan.findings), 2)
        self.assertEqual({f.path for f in scan.findings}, {'w.c'})

    def test_gcc_include_trace_line_is_not_a_finding(self):
        scan = run('gcc', fixture('gcc-include.txt'), code=1)
        self.assertEqual({f.path for f in scan.findings}, {'h.h'})
        self.assertEqual(len(scan.findings), 2)

    def test_regex_parser(self):
        pattern = r'^(?P<path>[\w./]+):(?P<line>\d+): (?P<level>\w+): (?P<message>.*) \[(?P<rule>[\w/-]+)\]$'
        text = 'src/a.rb:4: error: bad style [Style/Foo]\nsrc/a.rb:8: warning: meh [Lint/Bar]\ngarbage line\n'
        scan = run('regex', text, pattern=pattern, advisory_levels=['warning'])
        self.assertEqual(scan.integrity, [])
        self.assertEqual(rules_keys(scan.findings), [('Style/Foo', 'src/a.rb')])
        self.assertEqual(rules_keys(scan.advisory), [('Lint/Bar', 'src/a.rb')])
        self.assertEqual(scan.findings[0].line, 4)

    def test_regex_without_line_group_and_defaults(self):
        scan = run('regex', 'a.py bad\n', pattern=r'^(?P<path>\S+) (?P<message>.*)$')
        self.assertEqual((scan.findings[0].rule, scan.findings[0].key, scan.findings[0].line), ('error', 'a.py', None))

    def test_regex_missing_or_invalid_pattern_is_integrity(self):
        self.assertTrue(any('valid pattern' in p for p in run('regex', 'x').integrity))
        self.assertTrue(any('valid pattern' in p for p in run('regex', 'x', pattern='(unclosed').integrity))

    def test_text_parser_paths_are_normalized(self):
        scan = run('mypy', '/work/proj/src/a.py:3: error: Bad  [misc]\n./src/b.py:4: error: Bad  [misc]\n', code=1)
        self.assertEqual([f.key for f in scan.findings], ['src/a.py', 'src/b.py'])


# ─── lines / number / exit ───────────────────────────────────────────────────
class SnapshotLinesTest(unittest.TestCase):
    def test_sorted_unique_trimmed_lines(self):
        scan = run('lines', '  b()\n\na()\nb()\n   \n')
        self.assertEqual([(i.rule, i.key, i.mode) for i in scan.findings],
                         [('surface', 'a()', KEEP), ('surface', 'b()', KEEP)])
        self.assertEqual(scan.coverage, {'scanned': 2, 'unit': 'lines'})

    def test_empty_snapshot_is_integrity(self):
        for text in ('', '\n  \n'):
            self.assertTrue(any('printed nothing' in p for p in run('lines', text).integrity), repr(text))


class NumberTest(unittest.TestCase):
    def test_single_number_is_named_after_the_guard(self):
        scan = run('number', '42')
        self.assertEqual([(i.rule, i.key, i.count, i.mode) for i in scan.findings], [('metric', 'g', 42, 'budget')])
        self.assertEqual(scan.coverage, {'scanned': 1, 'unit': 'metrics'})

    def test_float_and_json_object(self):
        scan = run('number', '{"size": 1.5, "count": 3}')
        self.assertEqual([(i.key, i.count) for i in scan.findings], [('count', 3), ('size', 1.5)])

    def test_repeat_uses_the_median(self):
        scan = run('number', ['10', '30', '20'])
        self.assertEqual(scan.findings[0].count, 20)
        scan = run('number', ['{"a": 1, "b": 5}', '{"a": 9, "b": 7}', '{"a": 2, "b": 6}'])
        self.assertEqual([(i.key, i.count) for i in scan.findings], [('a', 2), ('b', 6)])

    def test_even_number_of_runs_averages_the_middle_pair(self):
        self.assertEqual(run('number', ['1', '3']).findings[0].count, 2)

    def test_non_numeric_output_is_integrity(self):
        for text in ('', 'twelve', '12 ms', '"12"', 'null', '[1, 2]', '{"a": "x"}', '{"a": true}', 'true', '{"a": null}'):
            scan = run('number', text)
            self.assertTrue(scan.integrity, repr(text))
            self.assertEqual(scan.findings, [], repr(text))

    def test_nan_and_infinity_are_integrity(self):
        for text in ('NaN', 'Infinity', '-Infinity', '{"a": NaN}'):
            scan = run('number', text)
            self.assertTrue(scan.integrity, f'{text!r} accepted as a metric value')


class ExitTest(unittest.TestCase):
    def test_zero_passes(self):
        scan = adapters.parse_exit(0, 'ignored', {'name': 'g'})
        self.assertEqual((scan.hard, scan.integrity, scan.coverage['scanned']), ([], [], 1))

    def test_nonzero_is_one_hard_item_with_output_tail(self):
        output = '\n'.join(f'line {n}' for n in range(40))
        scan = adapters.parse_exit(3, output, {'name': 'g'})
        (item,) = scan.hard
        self.assertEqual((item.rule, item.key, item.mode), ('failed', 'g', 'hard'))
        self.assertIn('exited 3', item.message)
        self.assertEqual(scan.evidence[-1], 'line 39')
        self.assertEqual(len(scan.evidence), 20)


class DispatchTest(unittest.TestCase):
    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            run('yaml', 'x')

    def test_ok_exit_table_covers_every_parser_but_exit(self):
        from guardlib.policy import PARSERS
        self.assertEqual(set(adapters.OK_EXIT), set(PARSERS) - {'exit'})
        for fmt, codes in adapters.OK_EXIT.items():
            self.assertIn(0, codes, fmt)

    def test_missing_output_means_integrity_for_parsers_that_need_text(self):
        for fmt in ('findings', 'sarif', 'eslint', 'junit', 'lines'):
            scan = adapters.parse(fmt, [], 0, {'name': 'g'}, PATHS)
            self.assertTrue(scan.integrity, fmt)


if __name__ == '__main__':
    unittest.main()
