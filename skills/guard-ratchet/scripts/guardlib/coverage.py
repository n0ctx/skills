"""Coverage and mutation reports, judged on the lines this change added.

Coverage formats (auto-detected): LCOV (JS/TS, Rust, C/C++, Ruby, Swift converters), Cobertura XML
(coverage.py, gcovr, coverlet, PHPUnit), JaCoCo XML (Java/Kotlin), Go coverprofile.
Mutation format: the mutation-testing-elements JSON schema (Stryker JS/.NET/Scala, PIT via plugin,
and others that export it).

Measuring only changed lines keeps the check meaningful in legacy code: a change is judged on
whether its own code is exercised, not on the history of the file.
"""

from __future__ import annotations

import glob
import json
import os
import re
import time
import xml.etree.ElementTree as ET

from . import policy as pol
from .context import Context, stale_inputs
from .model import Item, Scan

DEFAULT_MIN = pol.OPTION_DEFAULTS['diff-coverage']['min']


def _norm(path: str) -> str:
    path = path.replace('\\', '/')
    while path.startswith('./'):
        path = path[2:]
    return os.path.normpath(path).replace(os.sep, '/')


class Resolver:
    """Map a report path to a repo-relative file: exact, then root-relative, then unique suffix."""

    def __init__(self, ctx: Context):
        self.root = os.path.realpath(ctx.root)
        self.files = set(ctx.files)

    def __call__(self, raw: str, sources: list[str] = ()) -> str | None:
        candidates = [raw] + [os.path.join(s, raw) for s in sources]
        for cand in candidates:
            if os.path.isabs(cand):
                real = os.path.realpath(cand)
                if real.startswith(self.root + os.sep):
                    cand = os.path.relpath(real, self.root)
                else:
                    continue
            cand = _norm(cand)
            if cand in self.files:
                return cand
        tail = '/' + _norm(raw).lstrip('/')
        hits = [f for f in self.files if ('/' + f).endswith(tail)]
        return hits[0] if len(hits) == 1 else None


def parse_report(text: str, resolve: Resolver, root: str) -> tuple[dict[str, dict[int, int]], list[str]]:
    """Return ({path: {line: hits}}, unresolved report paths)."""
    lines: dict[str, dict[int, int]] = {}
    unresolved: list[str] = []

    def add(raw, line, hits, sources=()):
        path = resolve(raw, sources)
        if path is None:
            if raw not in unresolved:
                unresolved.append(raw)
            return
        bucket = lines.setdefault(path, {})
        bucket[line] = max(bucket.get(line, 0), hits)

    stripped = text.lstrip()
    if stripped.startswith('<'):
        tree = ET.fromstring(text)
        if tree.tag == 'coverage':  # Cobertura
            sources = [s.text.strip() for s in tree.iter('source') if s.text]
            for cls in tree.iter('class'):
                for line in cls.iter('line'):
                    add(cls.get('filename', ''), int(line.get('number')), int(float(line.get('hits', 0))), sources)
                if not list(cls.iter('line')):
                    lines.setdefault(resolve(cls.get('filename', ''), sources) or '', {})
        elif tree.tag == 'report':  # JaCoCo
            for pkg in tree.iter('package'):
                for src in pkg.iter('sourcefile'):
                    raw = f"{pkg.get('name')}/{src.get('name')}"
                    for line in src.iter('line'):
                        add(raw, int(line.get('nr')), int(line.get('ci', 0)))
        else:
            raise ValueError(f'unknown XML coverage format <{tree.tag}>')
    elif stripped.startswith('mode:'):  # Go coverprofile
        module = _go_module(root)
        for row in stripped.splitlines()[1:]:
            match = re.match(r'^(.+?):(\d+)\.\d+,(\d+)\.\d+ \d+ (\d+)$', row.strip())
            if not match:
                continue
            raw = match.group(1)
            if module and raw.startswith(module + '/'):
                raw = raw[len(module) + 1:]
            for n in range(int(match.group(2)), int(match.group(3)) + 1):
                add(raw, n, int(match.group(4)))
    elif 'SF:' in text:  # LCOV
        current = None
        for row in text.splitlines():
            if row.startswith('SF:'):
                current = row[3:].strip()
                path = resolve(current)
                if path:
                    lines.setdefault(path, {})
                elif current not in unresolved:
                    unresolved.append(current)
            elif row.startswith('DA:') and current:
                parts = row[3:].split(',')
                add(current, int(parts[0]), int(float(parts[1])))
            elif row.startswith('end_of_record'):
                current = None
    else:
        raise ValueError('unrecognized coverage report (expected LCOV, Cobertura, JaCoCo or Go coverprofile)')
    lines.pop('', None)
    return lines, unresolved


def _go_module(root: str) -> str | None:
    try:
        with open(os.path.join(root, 'go.mod'), encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('module '):
                    return line.split()[1].strip()
    except OSError:
        return None
    return None


def _read_inputs(ctx: Context, guard: dict, since: float | None = None) -> tuple[list[str], list[str]]:
    """Read the guard's report files. They must have been written during this run (by its own
    command, or by an earlier guard such as the test run), never left over or committed."""
    pattern = guard['input'].replace('{tmp}', ctx.tmp).replace('{root}', ctx.root)
    paths = sorted(glob.glob(pattern if os.path.isabs(pattern) else os.path.join(ctx.project, pattern)))
    texts, errors = [], []
    if not paths:
        errors.append(f'report {pattern} not found; the producing guard or command must run first')
        return texts, errors
    stale = set(stale_inputs(paths, ctx.started if since is None else since))
    if len(stale) == len(paths):
        errors.append(f"{', '.join(os.path.relpath(p, ctx.project) for p in paths)} was not written during this run: "
                      f"a stale or committed report is not evidence (have a guard or the `run` command produce it)")
        return texts, errors
    paths = [p for p in paths if p not in stale]  # leftovers of earlier runs (incremental builds)
    for path in paths:
        with open(path, encoding='utf-8', errors='replace') as fh:
            texts.append(fh.read())
    return texts, errors


def _ranges(numbers: list[int]) -> str:
    out, start, prev = [], None, None
    for n in sorted(numbers):
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f'{start}-{prev}' if start != prev else str(start))
            start = prev = n
    if start is not None:
        out.append(f'{start}-{prev}' if start != prev else str(start))
    return ','.join(out)


def _changed_code(ctx: Context, minimums: dict) -> dict[str, tuple[str, set[int]]]:
    out = {}
    from . import policy as pol
    for path, change in ctx.changes.files.items():
        if change.status == 'D' or not change.added or not pol.is_code(path, ctx.policy) or pol.excluded(ctx.policy, path):
            continue
        kind = ctx.kind(path)
        if minimums.get(kind) is not None:
            out[path] = (kind, {n for n, _ in change.added})
    return out


def diff_coverage(ctx: Context, guard: dict) -> Scan:
    scan = Scan(guard['name'], tool={'name': 'guard-ratchet/diff-coverage'})
    since = None
    if guard.get('run'):
        since = time.time()
        code, out, err = ctx.run(ctx.expand(guard['run']), guard.get('timeout', 1800))
        if code not in guard.get('ok_exit', [0]):
            scan.integrity.append(f'coverage command exited {code}: {(err or out).strip()[-400:]}')
            return scan
    texts, errors = _read_inputs(ctx, guard, since)
    scan.integrity += errors
    report: dict[str, dict[int, int]] = {}
    resolve = Resolver(ctx)
    for text in texts:
        try:
            lines, _ = parse_report(text, resolve, ctx.root)
        except (ValueError, ET.ParseError) as err:
            scan.integrity.append(f'coverage report unreadable: {err}')
            return scan
        for path, hits in lines.items():
            bucket = report.setdefault(path, {})
            for n, h in hits.items():
                bucket[n] = max(bucket.get(n, 0), h)
    if not texts or scan.integrity:
        return scan
    if not report:
        scan.integrity.append('coverage report covers no file of this repository (paths did not resolve)')
        return scan
    minimums = {**DEFAULT_MIN, **(guard.get('min') or {})}
    totals: dict[str, list[int]] = {}
    for path, (kind, added) in sorted(_changed_code(ctx, minimums).items()):
        if path not in report:
            scan.hard.append(Item('unmeasured', path, path=path, mode='hard',
                                  message=f'changed {kind} file is missing from the coverage report: configure the '
                                          f'coverage tool to include all source files (e.g. --all / source=)'))
            continue
        measured = [n for n in added if n in report[path]]
        missed = [n for n in measured if report[path][n] == 0]
        bucket = totals.setdefault(kind, [0, 0])
        bucket[0] += len(measured) - len(missed)
        bucket[1] += len(measured)
        if missed:
            scan.advisory.append(Item('uncovered-lines', path, path=path, line=min(missed), mode='advisory',
                                      message=f'changed lines not executed by tests: {_ranges(missed)}'))
    for kind, (hit, total) in sorted(totals.items()):
        if total == 0:
            continue
        if hit * 100 < minimums[kind] * total:  # exact; rounding first would let 79.96% pass 80%
            pct = round(hit * 100 / total, 1)
            if pct >= minimums[kind]:  # 79.96% would print as 80.0%; show it truncated instead
                pct = int(hit * 1000 / total) / 10
            scan.hard.append(Item('diff-coverage', kind, mode='hard',
                                  message=f'{pct}% of {total} changed executable {kind} lines are covered '
                                          f'(minimum {minimums[kind]}%); test the new code paths'))
    scan.coverage = {'scanned': len(report), 'unit': 'files in report'}
    return scan


# ─── mutation ────────────────────────────────────────────────────────────────
KILLED = ('Killed', 'Timeout')
SURVIVED = ('Survived', 'NoCoverage')


def mutation(ctx: Context, guard: dict) -> Scan:
    """Mutation score of mutants placed on changed lines. A mutant that survives means the tests
    still pass when that line's logic is altered: the change is not really verified."""
    scan = Scan(guard['name'], tool={'name': 'guard-ratchet/mutation'})
    since = None
    if guard.get('run'):
        since = time.time()
        code, out, err = ctx.run(ctx.expand(guard['run']), guard.get('timeout', 3600))
        if code not in guard.get('ok_exit', [0, 1]):
            scan.integrity.append(f'mutation command exited {code}: {(err or out).strip()[-400:]}')
            return scan
    texts, errors = _read_inputs(ctx, guard, since)
    scan.integrity += errors
    if scan.integrity:
        return scan
    resolve = Resolver(ctx)
    killed, survived = 0, []
    files = resolved = 0
    for text in texts:
        try:
            doc = json.loads(text)
            entries = doc['files'].items()
        except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as err:
            scan.integrity.append(f'mutation report does not follow the mutation-testing-elements schema: {err}')
            return scan
        for raw, data in entries:
            files += 1
            path = resolve(raw)
            resolved += bool(path)
            added = ctx.changes.added_lines(path) if path else set()
            for mutant in data.get('mutants', []):
                line = ((mutant.get('location') or {}).get('start') or {}).get('line')
                if line not in added:
                    continue
                if mutant.get('status') in KILLED:
                    killed += 1
                elif mutant.get('status') in SURVIVED:
                    survived.append((path, line, mutant.get('mutatorName'), mutant.get('replacement', '')))
    if not files:
        scan.integrity.append('mutation report lists no files: the mutation run tested nothing')
        return scan
    if not resolved:
        scan.integrity.append('mutation report covers no file of this repository (paths did not resolve)')
        return scan
    total = killed + len(survived)
    min_score = guard.get('min_score', pol.OPTION_DEFAULTS['mutation']['min_score'])
    for path, line, mutator, replacement in survived[:30]:
        scan.advisory.append(Item('survived-mutant', f'{path}#{mutator}', path=path, line=line, mode='advisory',
                                  message=f'{mutator} survived{f" (-> {replacement})" if replacement else ""}: '
                                          f'no test fails when this line changes'))
    if total and killed * 100 < min_score * total:
        scan.hard.append(Item('mutation-score', 'changed-lines', mode='hard',
                              message=f'mutation score on changed lines {round(killed * 100 / total, 1)}% '
                                      f'({killed}/{total} killed), minimum {min_score}%'))
    scan.coverage = {'scanned': files, 'unit': 'files in report', 'mutants_on_changed_lines': total}
    return scan
