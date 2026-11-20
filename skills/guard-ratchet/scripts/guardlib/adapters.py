"""Turn tool output into a Scan. One adapter per output format, not per tool.

Formats: findings (guard-ratchet detector JSON v1/v2), sarif (semgrep, ruff, gitleaks, zizmor,
osv-scanner, bandit, gosec, golangci-lint, CodeQL, clippy-sarif, ...), eslint (JSON formatter),
junit (test results from nearly every runner), lizard (CSV, ~30 languages), tsc / mypy / gcc
(compiler-style text), regex (any line format), lines (API/schema snapshots), number (metrics),
exit (pass/fail by exit code).

Every adapter fails closed: output that cannot be parsed, or a tool that reports it did not run
to completion, becomes an integrity problem rather than "0 findings".
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import statistics
import urllib.parse
import xml.etree.ElementTree as ET

from .model import DETECTOR_SCHEMA, KEEP, Item, Scan

# Exit codes that mean "ran fine" for each parser (findings may exist).
OK_EXIT = {
    'findings': [0], 'sarif': [0, 1], 'eslint': [0, 1], 'junit': [0, 1], 'lizard': [0, 1],
    'tsc': [0, 1, 2], 'mypy': [0, 1], 'gcc': [0, 1], 'regex': [0, 1], 'lines': [0], 'number': [0],
}

GCC_RE = re.compile(r'^(?P<path>[^:\s][^:]*):(?P<line>\d+)(?::\d+)?:\s*(?:(?P<level>fatal error|error|warning|note|info)'
                    r'\s*:\s*)?(?P<message>.*?)(?:\s+\[(?P<rule>[^\]\s]+)\])?\s*$')
TSC_RE = re.compile(r'^(?P<path>[^(\s][^(]*)\((?P<line>\d+),\d+\):\s*(?P<level>error|warning)\s+(?P<rule>TS\d+):\s*(?P<message>.*)$')
TSC_GLOBAL_RE = re.compile(r'^error (?P<rule>TS\d+):\s*(?P<message>.*)$')
MYPY_RE = re.compile(r'^(?P<path>[^:\s][^:]*):(?P<line>\d+)(?::\d+)?:\s*(?P<level>error|warning|note):\s*(?P<message>.*?)'
                     r'(?:\s+\[(?P<rule>[\w-]+)\])?\s*$')


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Paths:
    """Normalize tool paths to repo-relative paths. Tools report paths relative to the cwd, the
    scanned root, or as absolute paths / file:// URIs; all must map to the same key."""

    def __init__(self, scan_root: str, project_root: str):
        self.roots = [os.path.realpath(scan_root), os.path.realpath(project_root), scan_root, project_root]

    def rel(self, raw: str | None) -> str | None:
        if not raw:
            return None
        path = raw
        if path.startswith('file://'):
            path = urllib.parse.unquote(urllib.parse.urlparse(path).path)
        path = path.replace('\\', '/')
        if os.path.isabs(path):
            for root in self.roots:
                prefix = root.rstrip('/') + '/'
                if path.startswith(prefix):
                    return path[len(prefix):]
            real = os.path.realpath(path)
            for root in self.roots:
                prefix = root.rstrip('/') + '/'
                if real.startswith(prefix):
                    return real[len(prefix):]
            return None  # outside the repository
        while path.startswith('./'):
            path = path[2:]
        if not path:
            return None
        norm = os.path.normpath(path).replace(os.sep, '/')
        if norm != '..' and not norm.startswith('../'):
            return norm
        # Some tools (golangci-lint) print paths relative to their working directory that climb out
        # through a symlink and back in. Resolve against the possible working directories; anything
        # that still lands outside the repository is not a repository file.
        for cwd in self.roots[2:] + self.roots[:2]:
            inside = self.rel(os.path.normpath(os.path.join(cwd, norm)))
            if inside:
                return inside
        return None


def _json(text: str, what: str, scan: Scan):
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        scan.integrity.append(f'{what} output is not valid JSON: {err}')
        return None


# ─── detector JSON ───────────────────────────────────────────────────────────
def _item(raw, default_rule: str, paths: Paths, mode: str) -> Item:
    if isinstance(raw, str):
        return Item(default_rule, raw, message=raw, mode=mode)
    count = raw.get('count', 1)
    if not isinstance(count, (int, float)) or isinstance(count, bool) or count < 0:
        raise ValueError(f'count must be a non-negative number: {raw}')
    if default_rule == 'finding' and not (raw.get('rule') and raw.get('key')):
        raise ValueError(f'finding needs rule and key: {raw}')
    return Item(raw.get('rule') or default_rule, str(raw.get('key') or raw.get('message') or ''), count,
                paths.rel(raw.get('path')), raw.get('line'), raw.get('message', ''), mode)


def parse_findings(text: str, guard: dict, paths: Paths) -> Scan:
    scan = Scan(guard['name'])
    doc = _json(text, 'detector', scan)
    if not isinstance(doc, dict):
        if doc is not None:
            scan.integrity.append('detector output must be a JSON object')
        return scan
    schema = doc.get('schema')
    if schema not in (None, DETECTOR_SCHEMA):
        scan.integrity.append(f'unsupported detector schema {schema!r} (expected {DETECTOR_SCHEMA})')
        return scan
    if doc.get('guard') not in (None, guard['name']):
        scan.integrity.append(f"detector reports guard {doc.get('guard')!r}, policy calls it {guard['name']!r}")
    scan.tool = doc.get('tool') or {}
    if schema:
        scan.coverage = dict(doc.get('coverage') or {})
    else:  # v1: {scanned, min_scanned}
        scan.coverage = {'scanned': doc.get('scanned'), 'min': doc.get('min_scanned', 1)}
    cov = scan.coverage
    if not isinstance(cov.get('scanned'), (int, float)):
        scan.integrity.append('detector did not report coverage.scanned')
    elif cov.get('planned') is not None and cov['scanned'] < cov['planned']:
        scan.integrity.append(f"incomplete scan: planned {cov['planned']}, scanned {cov['scanned']}")
    elif cov.get('min') is not None and cov['scanned'] < cov['min']:
        scan.integrity.append(f"scanned {cov['scanned']} is below the detector's minimum {cov['min']}")
    for field in ('parse_failures', 'unsupported', 'hard', 'advisory', 'findings', 'metrics'):
        if field in doc and not isinstance(doc[field], list):
            scan.integrity.append(f'detector field {field} must be a list, got {type(doc[field]).__name__}')
            return scan
    scan.integrity += [f'parse failure: {p}' for p in doc.get('parse_failures') or []]
    for u in doc.get('unsupported') or []:
        scan.integrity.append(f"unsupported input: {u.get('path', '')} {u.get('message', '')}".strip()
                              if isinstance(u, dict) else f'unsupported input: {u}')
    try:
        scan.hard = [_item(h, 'hard', paths, 'hard') for h in doc.get('hard') or []]
        scan.advisory = [_item(a, 'advisory', paths, 'advisory') for a in doc.get('advisory') or []]
        scan.findings = [_item(f, 'finding', paths, guard.get('mode', 'ratchet')) for f in doc.get('findings') or []]
    except (ValueError, AttributeError) as err:
        scan.integrity.append(f'malformed detector item: {err}')
    for metric in doc.get('metrics') or []:
        if not isinstance(metric, dict) or not metric.get('metric') or not metric.get('key') \
                or not _finite(metric.get('value')):
            scan.integrity.append(f'malformed metric: {metric}')
            continue
        scan.metrics.append({**metric, 'path': paths.rel(metric.get('path'))})
    return scan


# ─── SARIF ───────────────────────────────────────────────────────────────────
def _sarif_rule_id(result: dict, rules: list) -> str:
    if result.get('ruleId'):
        return result['ruleId']
    rule = result.get('rule') or {}
    if rule.get('id'):
        return rule['id']
    index = rule.get('index', result.get('ruleIndex'))
    if isinstance(index, int) and 0 <= index < len(rules):
        return rules[index].get('id', 'unknown')
    return 'unknown'


def _sarif_location(result: dict, run: dict, paths: Paths) -> tuple[str | None, int | None]:
    for loc in result.get('locations') or []:
        phys = loc.get('physicalLocation') or {}
        art = phys.get('artifactLocation') or {}
        uri = art.get('uri')
        if uri is None and isinstance(art.get('index'), int):
            artifacts = run.get('artifacts') or []
            if art['index'] < len(artifacts):
                uri = (artifacts[art['index']].get('location') or {}).get('uri')
        base = (run.get('originalUriBaseIds') or {}).get(art.get('uriBaseId') or '', {}).get('uri')
        if uri and base and not re.match(r'^[a-z]+://', uri) and not uri.startswith('/'):
            uri = base.rstrip('/') + '/' + uri
        if uri:
            return paths.rel(urllib.parse.unquote(uri) if not uri.startswith('file://') else uri), \
                (phys.get('region') or {}).get('startLine')
    return None, None


def parse_sarif(text: str, guard: dict, paths: Paths) -> Scan:
    scan = Scan(guard['name'])
    doc = _json(text, 'SARIF', scan)
    if doc is None:
        return scan
    if not isinstance(doc, dict) or not isinstance(doc.get('runs'), list):
        scan.integrity.append('SARIF output has no runs array')
        return scan
    if not doc['runs']:
        scan.integrity.append('SARIF output has an empty runs array: the tool analyzed nothing')
        return scan
    advisory_levels = set(guard.get('advisory_levels', ['note', 'none']))
    files = set()
    for run in doc['runs']:
        driver = (run.get('tool') or {}).get('driver') or {}
        if not isinstance(run.get('results'), list):
            # SARIF 2.1.0 §3.14.23: an absent results array means the tool did not compute results.
            scan.integrity.append(f"SARIF run of {driver.get('name') or 'the tool'} has no results array: "
                                  f"analysis did not complete")
        scan.tool = {'name': driver.get('name'), 'version': driver.get('semanticVersion') or driver.get('version')}
        for inv in run.get('invocations') or []:
            if inv.get('executionSuccessful') is False:
                notes = [n.get('message', {}).get('text', '') for n in inv.get('toolExecutionNotifications') or []
                         if n.get('level', 'error') == 'error']
                scan.integrity.append(f"{driver.get('name')} reports an unsuccessful run: {'; '.join(notes)[:500]}")
        for art in run.get('artifacts') or []:
            rel = paths.rel((art.get('location') or {}).get('uri'))
            if rel:
                files.add(rel)
        rules = driver.get('rules') or []
        defaults = {r.get('id'): (r.get('defaultConfiguration') or {}).get('level') for r in rules}
        for result in run.get('results') or []:
            if result.get('suppressions') or result.get('baselineState') == 'absent' \
                    or result.get('kind', 'fail') != 'fail':
                continue
            rule = _sarif_rule_id(result, rules)
            level = result.get('level') or defaults.get(rule) or 'warning'
            path, line = _sarif_location(result, run, paths)
            message = ((result.get('message') or {}).get('text') or '').strip().splitlines()
            mode = 'advisory' if level in advisory_levels else guard.get('mode', 'ratchet')
            item = Item(rule, path or '(no location)', 1, path, line, message[0][:300] if message else '', mode)
            (scan.advisory if mode == 'advisory' else scan.findings).append(item)
    scan.coverage = {'scanned': len(files), 'unit': 'files'} if files else {'scanned': None, 'unit': 'not reported'}
    return scan


# ─── ESLint JSON ─────────────────────────────────────────────────────────────
def parse_eslint(text: str, guard: dict, paths: Paths) -> Scan:
    scan = Scan(guard['name'], tool={'name': 'eslint'})
    doc = _json(text, 'ESLint', scan)
    if doc is None:
        return scan
    if not isinstance(doc, list):
        scan.integrity.append('ESLint JSON output must be an array of file results')
        return scan
    advisory_levels = set(guard.get('advisory_levels', []))
    for result in doc:
        path = paths.rel(result.get('filePath'))
        for msg in result.get('messages', []):
            if msg.get('fatal'):
                scan.integrity.append(f"parse failure: {path}:{msg.get('line')} {msg.get('message')}")
                continue
            level = 'warning' if msg.get('severity') == 1 else 'error'
            mode = 'advisory' if level in advisory_levels else guard.get('mode', 'ratchet')
            item = Item(msg.get('ruleId') or 'eslint', path or '(no location)', 1, path, msg.get('line'),
                        msg.get('message', ''), mode)
            (scan.advisory if mode == 'advisory' else scan.findings).append(item)
    scan.coverage = {'scanned': len(doc), 'unit': 'files'}
    return scan


# ─── JUnit XML ───────────────────────────────────────────────────────────────
def parse_junit(texts: list[str], guard: dict, paths: Paths) -> Scan:
    """Test inventory. Rule `present` = the test exists, `active` = it is not skipped (keep rules).
    Failing tests are hard problems."""
    scan = Scan(guard['name'], tool={'name': 'junit'})
    cases = []
    for text in texts:
        try:
            root = ET.fromstring(text)
        except ET.ParseError as err:
            scan.integrity.append(f'JUnit report is not valid XML: {err}')
            continue
        cases += list(root.iter('testcase'))
    ids = []
    for case in cases:
        name = case.get('name') or ''
        owner = case.get('classname') or paths.rel(case.get('file')) or case.get('file') or ''
        ids.append((f'{owner}::{name}' if owner else name, case))
    seen: dict[str, int] = {}
    for test_id, case in ids:
        n = seen.get(test_id, 0) + 1
        seen[test_id] = n
        key = f'{test_id}~{n}' if n > 1 else test_id
        skipped = case.find('skipped') is not None
        failed = next((c for c in case if c.tag in ('failure', 'error')), None)
        scan.findings.append(Item('present', key, 1, mode=KEEP))
        if not skipped:
            scan.findings.append(Item('active', key, 1, mode=KEEP))
        if failed is not None:
            detail = (failed.get('message') or failed.text or '').strip().splitlines()
            scan.hard.append(Item('failing', key, 1, message=f"test fails: {detail[0][:300] if detail else ''}",
                                  mode='hard'))
    scan.coverage = {'scanned': len(ids), 'unit': 'tests'}
    if not ids and not scan.integrity:
        scan.integrity.append('the JUnit report contains no test cases (collection broken or tests excluded)')
    return scan


# ─── lizard ──────────────────────────────────────────────────────────────────
def parse_lizard(text: str, guard: dict, paths: Paths) -> Scan:
    """lizard --csv: nloc, ccn, token, param, length, location, file, function, long_name, start, end."""
    scan = Scan(guard['name'], tool={'name': 'lizard'})
    files, items = set(), []
    for row in csv.reader(io.StringIO(text)):
        if not row or row[0].upper() == 'NLOC':
            continue
        if len(row) < 11:
            scan.integrity.append(f'unexpected lizard CSV row: {row}')
            continue
        path = paths.rel(row[6])
        if path is None:
            continue
        try:
            ccn, nloc, start = int(row[1]), int(row[0]), int(row[9])
        except ValueError:
            scan.integrity.append(f'unexpected lizard CSV row: {row}')
            continue
        files.add(path)
        items.append((path, row[7], ccn, nloc, start))
    seen: dict[str, int] = {}
    for path, func, ccn, nloc, start in items:
        base = f'{path}#{func}'
        n = seen.get(base, 0) + 1
        seen[base] = n
        key = f'{base}~{n}' if n > 1 else base
        scan.metrics.append({'metric': 'fn-complexity', 'key': key, 'path': path, 'line': start, 'value': ccn})
        scan.metrics.append({'metric': 'fn-length', 'key': key, 'path': path, 'line': start, 'value': nloc})
    scan.coverage = {'scanned': len(files), 'unit': 'files', 'functions': len(items)}
    return scan


# ─── compiler-style text ─────────────────────────────────────────────────────
ANSI = re.compile(r'\x1b\[[0-9;]*m')
TSC_PRETTY_RE = re.compile(r'^(?P<path>\S[^:]*):(?P<line>\d+):\d+ - (?P<level>error|warning) (?P<rule>TS\d+):\s*(?P<message>.*)$')
INCLUDE_TRACE = re.compile(r'^(In file included from |\s+from |In function |At top level:)')


def parse_lines_with(text: str, guard: dict, paths: Paths, regexes, tool: str, code: int = 0) -> Scan:
    """Compiler-style text. A non-zero exit without a single recognizable diagnostic means the tool
    failed (crash, traceback, config error), not that the code is clean."""
    scan = Scan(guard['name'], tool={'name': tool})
    for raw in text.splitlines():
        line = ANSI.sub('', raw).rstrip()
        if INCLUDE_TRACE.match(line):
            continue
        match = next((m for m in (r.match(line) for r in regexes) if m), None)
        if not match:
            if tool == 'tsc' and TSC_GLOBAL_RE.match(line):
                scan.integrity.append(f'tsc configuration error: {line}')
            continue
        groups = match.groupdict()
        level = (groups.get('level') or 'error').lower()
        if level in ('note', 'info'):
            continue
        path = paths.rel(groups.get('path'))
        rule = groups.get('rule') or level
        mode = 'advisory' if level in guard.get('advisory_levels', []) else guard.get('mode', 'ratchet')
        item = Item(rule, path or '(no location)', 1, path, int(groups['line']) if groups.get('line') else None,
                    (groups.get('message') or '').strip(), mode)
        (scan.advisory if mode == 'advisory' else scan.findings).append(item)
    if code != 0 and not scan.findings and not scan.advisory and not scan.integrity:
        tail = ' / '.join(text.strip().splitlines()[-5:])[:500]
        scan.integrity.append(f'{tool} exited {code} but printed no diagnostic it could parse: {tail or "(no output)"}')
    scan.coverage = {'scanned': None, 'unit': 'not reported'}
    return scan


# ─── snapshot lines / metric numbers / exit status ───────────────────────────
def parse_lines(text: str, guard: dict) -> Scan:
    scan = Scan(guard['name'])
    lines = sorted({line.strip() for line in text.splitlines() if line.strip()})
    scan.findings = [Item('surface', line, 1, mode=KEEP) for line in lines]
    scan.coverage = {'scanned': len(lines), 'unit': 'lines'}
    if not lines:
        scan.integrity.append('the snapshot command printed nothing')
    return scan


def parse_numbers(texts: list[str], guard: dict) -> Scan:
    """A metric command prints a number or a JSON object {name: number}. With repeat > 1, the
    median of the runs is used to damp noise."""
    scan = Scan(guard['name'])
    runs: dict[str, list[float]] = {}
    for text in texts:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            scan.integrity.append(f'metric output is not a number or JSON object: {text.strip()[:200]!r}')
            return scan
        values = value if isinstance(value, dict) else {guard['name']: value}
        for name, number in values.items():
            if not _finite(number):
                scan.integrity.append(f'metric {name} is not a number: {number!r}')
                return scan
            runs.setdefault(name, []).append(number)
    for name, values in sorted(runs.items()):
        scan.findings.append(Item('metric', name, statistics.median(values), mode='budget'))
    scan.coverage = {'scanned': len(runs), 'unit': 'metrics'}
    return scan


def parse_exit(code: int, output: str, guard: dict) -> Scan:
    scan = Scan(guard['name'])
    scan.coverage = {'scanned': 1, 'unit': 'command'}
    if code != 0:
        tail = [line for line in output.strip().splitlines()[-20:]]
        scan.hard.append(Item('failed', guard['name'], 1, message=f'command exited {code}', mode='hard'))
        scan.evidence = tail
    return scan


def parse(fmt: str, outputs: list[str], code: int, guard: dict, paths: Paths) -> Scan:
    text = outputs[0] if outputs else ''
    if fmt == 'findings':
        return parse_findings(text, guard, paths)
    if fmt == 'sarif':
        return parse_sarif(text, guard, paths)
    if fmt == 'eslint':
        return parse_eslint(text, guard, paths)
    if fmt == 'junit':
        return parse_junit(outputs, guard, paths)
    if fmt == 'lizard':
        return parse_lizard(text, guard, paths)
    if fmt == 'tsc':
        return parse_lines_with(text, guard, paths, (TSC_RE, TSC_PRETTY_RE), 'tsc', code)
    if fmt == 'mypy':
        return parse_lines_with(text, guard, paths, (MYPY_RE,), 'mypy', code)
    if fmt == 'gcc':
        return parse_lines_with(text, guard, paths, (GCC_RE,), 'compiler', code)
    if fmt == 'regex':
        try:
            regex = re.compile(guard['pattern'])
        except (KeyError, re.error) as err:
            scan = Scan(guard['name'])
            scan.integrity.append(f'regex parser needs a valid pattern with named groups: {err}')
            return scan
        return parse_lines_with(text, guard, paths, (regex,), 'regex', code)
    if fmt == 'lines':
        return parse_lines(text, guard)
    if fmt == 'number':
        return parse_numbers(outputs, guard)
    raise ValueError(f'unknown format {fmt}')
