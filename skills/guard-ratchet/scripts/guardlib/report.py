"""Render a run as JSON (agents, CI), text (terminal) or Markdown (CI step summary)."""

from __future__ import annotations

import json

from .model import BLOCKING, REPORT_SCHEMA

ICON = {'pass': '✓', 'fail': '✗', 'error': '✗', 'missing-tool': '!', 'skipped': '-'}
HINTS = {
    'integrity': 'the scan itself failed: fix the tool, its configuration or the unparseable file',
    'new': 'fix it; if it is genuinely acceptable, record an exception (`guard.py except add`)',
    'worse': 'bring it back to the baseline value, or record an exception with a max',
    'lost': 'restore the test / API entry, or record an exception explaining the removal',
    'hard': 'fix it; hard rules are never baselined',
    'stale': 'run `guard.py update` and commit the tightened baseline',
    'moved': 'run `guard.py update` and commit the rewritten baseline keys',
    'unrecorded': 'run `guard.py update` and commit the snapshot',
    'scope': 'the scan covers much less than before: fix the scope, or record an exception (rule "scope")',
    'rule-change': 'run `guard.py update --rules-changed` (rebuilds the baseline from the base commit)',
    'locked': 'revert the loosening, or record an exception for exactly this key',
    'protected': 'protected files need an exception and an approving review from code owners',
    'exception': 'fix or delete the invalid exception entry',
}


def to_json(run) -> dict:
    blocking = [p for p in run.problems if p.blocking]
    by_category = {}
    for p in blocking:
        by_category[p.category] = by_category.get(p.category, 0) + 1
    return {
        'schema': REPORT_SCHEMA,
        'verdict': run.verdict,
        'exit_code': run.exit_code,
        'base': run.base,
        'tier': run.tier,
        'requested_tier': run.requested_tier,
        'trusted': run.trusted,
        'risk': run.risk,
        'incomplete': run.incomplete,
        'summary': {'blocking': len(blocking), 'by_category': by_category,
                    'guards': {g.name: g.status for g in run.guards}},
        'guards': [{
            'name': g.name, 'status': g.status, 'reason': g.reason or None, 'seconds': g.seconds,
            'coverage': g.coverage or None, 'tool': g.tool or None, 'baseline_entries': g.baseline_entries,
            'baseline_written': g.baseline_written, 'evidence': g.evidence or None,
            'problems': [p.to_json() for p in g.problems],
        } for g in run.guards],
        'problems': [p.to_json() for p in run.global_problems],
        'exceptions': run.exceptions,
    }


def _coverage(cov: dict) -> str:
    if not cov:
        return ''
    scanned = cov.get('scanned')
    extra = [f'{v} {k}' for k, v in cov.items() if k not in ('scanned', 'planned', 'unit', 'min')
             and isinstance(v, (int, float))]
    head = f"{scanned} {cov.get('unit', '')}".strip() if scanned is not None else f"coverage {cov.get('unit', 'n/a')}"
    return ' / '.join([head, *extra])


def _line(p) -> str:
    where = f'{p.path}:{p.line}' if p.path and p.line else (p.path or '')
    parts = [f'{p.category:<11}', p.rule or '-', p.key or '']
    text = '  '.join(x for x in parts if x)
    if p.message:
        text += f' — {p.message}'
    if where and where not in text:
        text += f'  [{where}]'
    if p.excepted_by:
        text += f'  (excepted: {p.excepted_by})'
    return text


def to_text(run, max_advisory: int = 15) -> str:
    out = []
    reasons = '; '.join(run.risk.get('reasons', [])[:4])
    mode = ' trusted' if run.trusted else ''
    out.append(f"guard-ratchet{mode}: {run.verdict.upper()} — tier {run.tier} ({reasons})")
    if run.base:
        out.append(f'base {run.base[:12]}, {run.risk["changed_files"]} files / {run.risk["changed_lines"]} lines changed')
    out.append('')
    width = max([len(g.name) for g in run.guards] + [6])
    for g in run.guards:
        detail = g.reason or _coverage(g.coverage)
        if g.baseline_entries:
            detail += f'  ({g.baseline_entries} baseline entries)'
        if g.baseline_written:
            detail += f'  wrote {g.baseline_written}'
        out.append(f"  {ICON.get(g.status, '?')} {g.name:<{width}}  {g.status:<12} {detail}".rstrip())
    blocking_sections = [('policy, baselines and protected files', [p for p in run.global_problems if p.category in BLOCKING])]
    blocking_sections += [(g.name, [p for p in g.problems if p.category in BLOCKING]) for g in run.guards]
    categories = set()
    for title, problems in blocking_sections:
        if not problems:
            continue
        out += ['', f'{title}:']
        for p in sorted(problems, key=lambda p: (not p.blocking, BLOCKING.index(p.category), p.rule, p.key)):
            out.append('  ' + _line(p))
            if p.blocking:
                categories.add(p.category)
        g = next((g for g in run.guards if g.name == title), None)
        if g and g.evidence:
            out += ['  output:'] + [f'    {line}' for line in g.evidence]
    advisory = [p for p in run.problems if p.category not in BLOCKING]
    if advisory:
        out += ['', f'advisory ({len(advisory)}, does not fail the run):']
        for p in advisory[:max_advisory]:
            out.append(f'  {p.guard}: ' + _line(p))
        if len(advisory) > max_advisory:
            out.append(f'  … {len(advisory) - max_advisory} more in --format json')
    if run.incomplete:
        out += ['', 'incomplete (exit 3, not a pass):'] + [f'  {r}' for r in run.incomplete]
    if categories:
        out += ['', 'next steps:'] + [f'  {c}: {HINTS[c]}' for c in BLOCKING if c in categories]
    return '\n'.join(out) + '\n'


def to_markdown(run) -> str:
    out = [f"### guard-ratchet: {run.verdict.upper()} (tier {run.tier}{', trusted' if run.trusted else ''})", '']
    if run.risk.get('reasons'):
        out.append('Risk: ' + '; '.join(run.risk['reasons'][:6]))
        out.append('')
    out += ['| guard | status | detail |', '|---|---|---|']
    for g in run.guards:
        detail = (g.reason or _coverage(g.coverage)).replace('|', '\\|')
        out.append(f"| {g.name} | {ICON.get(g.status, '')} {g.status} | {detail} |")
    blocking = [p for p in run.problems if p.blocking]
    if blocking:
        out += ['', '| category | guard | rule | key | detail |', '|---|---|---|---|---|']
        for p in blocking[:100]:
            cells = [p.category, p.guard, p.rule or '', f'`{p.key}`' if p.key else '', (p.message or '')[:200]]
            out.append('| ' + ' | '.join(c.replace('|', '\\|') for c in cells) + ' |')
    if run.exceptions:
        out += ['', f'Exceptions in force: {len(run.exceptions)}']
        out += [f"- `{e['guard']}/{e['rule']}/{e['key']}` — {e['reason']} (approved_by {e['approved_by']})"
                for e in run.exceptions[:30]]
    return '\n'.join(out) + '\n'


def render(run, fmt: str) -> str:
    if fmt == 'json':
        return json.dumps(to_json(run), ensure_ascii=False, indent=2) + '\n'
    if fmt == 'markdown':
        return to_markdown(run)
    return to_text(run)
