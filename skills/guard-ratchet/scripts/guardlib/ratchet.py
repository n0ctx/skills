"""Baseline ratchet: compare current entries with a baseline and compute a safe updated baseline.

Rule modes (see references/contract.md):
- ratchet: lower is better. New key = new; count up = worse; count down or gone = stale.
- budget:  lower is better with tolerated growth. New key = new; growth beyond tolerance = worse;
           growth within tolerance passes but is never written back; decrease = slack (update
           lowers it); gone = stale.
           With direction 'higher' (e.g. total coverage) the same applies upside down.
- keep:    presence is required (test inventory, API surface). Missing or lower = lost; new key =
           unrecorded (blocking only when strict_sync).

update() never adds a ratchet/budget key and never raises a lower-is-better count. New problems
are tolerated only through exceptions (guards/exceptions.json), never through the baseline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .model import BASELINE_VERSION, KEEP, GuardError


@dataclass
class RuleMeta:
    mode: str = 'ratchet'
    direction: str = 'lower'
    growth: dict = field(default_factory=dict)
    strict_sync: bool = False


@dataclass
class Delta:
    rule: str
    key: str
    baseline: float | None = None
    current: float | None = None
    old_key: str | None = None


@dataclass
class Diff:
    new: list[Delta] = field(default_factory=list)
    worse: list[Delta] = field(default_factory=list)
    stale: list[Delta] = field(default_factory=list)
    lost: list[Delta] = field(default_factory=list)
    unrecorded: list[Delta] = field(default_factory=list)
    moved: list[Delta] = field(default_factory=list)
    slack: list[Delta] = field(default_factory=list)
    within: list[Delta] = field(default_factory=list)
    carried: int = 0


# ─── baseline documents ──────────────────────────────────────────────────────
def empty_baseline(guard: str) -> dict:
    return {'version': BASELINE_VERSION, 'guard': guard, 'fingerprint': None, 'tool': None, 'scanned': None,
            'modes': {}, 'entries': {}}


def parse_baseline(text: str, guard: str) -> dict:
    """Accept v1 ({version: 1, guard, entries}) and v2 baselines; return a normalized v2 document."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as err:
        raise GuardError(f'baseline of {guard} is not valid JSON: {err}') from err
    if not isinstance(doc, dict) or doc.get('version') not in (1, BASELINE_VERSION):
        raise GuardError(f'baseline of {guard}: unsupported version {doc.get("version") if isinstance(doc, dict) else doc}')
    if doc.get('guard') != guard:
        raise GuardError(f'baseline belongs to guard {doc.get("guard")!r}, not {guard!r}')
    entries = doc.get('entries', {})
    if not isinstance(entries, dict) or not all(isinstance(v, dict) for v in entries.values()):
        raise GuardError(f'baseline of {guard}: entries must be {{rule: {{key: count}}}}')
    for rule, keys in entries.items():
        for key, count in keys.items():
            if not isinstance(count, (int, float)) or isinstance(count, bool) or count < 0:
                raise GuardError(f'baseline of {guard}: {rule}:{key} has invalid count {count!r}')
    out = empty_baseline(guard)
    out.update({k: doc.get(k) for k in ('fingerprint', 'tool', 'scanned') if k in doc})
    out['modes'] = dict(doc.get('modes', {}))
    out['entries'] = {rule: dict(keys) for rule, keys in entries.items()}
    out['legacy'] = doc.get('version') == 1
    return out


def dump_baseline(doc: dict) -> str:
    entries = {rule: dict(sorted(keys.items())) for rule, keys in sorted(doc['entries'].items()) if keys}
    modes = {rule: mode for rule, mode in sorted(doc['modes'].items()) if rule in entries and mode != 'ratchet'}
    out = {'version': BASELINE_VERSION, 'guard': doc['guard'], 'fingerprint': doc.get('fingerprint'),
           'tool': doc.get('tool'), 'scanned': doc.get('scanned'), 'modes': modes, 'entries': entries}
    return json.dumps(out, ensure_ascii=False, indent=2, sort_keys=False) + '\n'


def entries_of(items) -> dict[str, dict[str, float]]:
    """Sum counts per rule+key; drop zero counts."""
    out: dict[str, dict[str, float]] = {}
    for item in items:
        bucket = out.setdefault(item.rule, {})
        bucket[item.key] = bucket.get(item.key, 0) + item.count
    return {rule: {k: v for k, v in keys.items() if v > 0} for rule, keys in out.items()}


# ─── renames and moves ───────────────────────────────────────────────────────
def _path_token(old: str) -> re.Pattern:
    return re.compile(r'(?<![\w./-])' + re.escape(old) + r'(?![\w./-])')


def rewrite_renames(entries: dict, renames: dict[str, str]) -> tuple[dict, list[Delta]]:
    """Rewrite baseline keys that mention a renamed file. Returns (entries, moved deltas)."""
    if not renames:
        return entries, []
    patterns = [(_path_token(old), new) for old, new in sorted(renames.items())]
    out, moved = {}, []
    for rule, keys in entries.items():
        bucket = out.setdefault(rule, {})
        for key, count in keys.items():
            new_key = key
            for pattern, new in patterns:
                new_key = pattern.sub(new, new_key)
            bucket[new_key] = bucket.get(new_key, 0) + count
            if new_key != key:
                moved.append(Delta(rule, new_key, count, None, old_key=key))
    return out, moved


def _symbol(key: str) -> str | None:
    return key.split('#', 1)[1] if '#' in key and not key.endswith('#') else None


def pair_moves(base: dict, cur: dict, meta: dict[str, RuleMeta]) -> list[Delta]:
    """Pair a vanished key with a new key of the same rule and symbol (moved between files).

    Only unambiguous one-to-one pairs whose value did not get worse are moves; anything else
    stays new + stale, so splitting or duplicating code cannot hide behind a "move".
    """
    moves = []
    for rule, keys in base.items():
        m = meta.get(rule, RuleMeta())
        if m.mode == KEEP or m.direction == 'higher':
            continue
        now = cur.get(rule, {})
        gone = [k for k in keys if k not in now and _symbol(k)]
        added = [k for k in now if k not in keys and _symbol(k)]
        for symbol in sorted({_symbol(k) for k in gone}):
            g = [k for k in gone if _symbol(k) == symbol]
            a = [k for k in added if _symbol(k) == symbol]
            if len(g) == 1 and len(a) == 1 and now[a[0]] <= keys[g[0]]:
                moves.append(Delta(rule, a[0], keys[g[0]], now[a[0]], old_key=g[0]))
    return moves


def _apply_moves(base: dict, moves: list[Delta]) -> dict:
    out = {rule: dict(keys) for rule, keys in base.items()}
    for mv in moves:
        bucket = out.setdefault(mv.rule, {})
        bucket[mv.key] = bucket.pop(mv.old_key)
    return out


# ─── comparison ──────────────────────────────────────────────────────────────
def exceeds(base: float, delta: float, growth: dict) -> bool:
    """A change of `delta` from `base` exceeds the tolerance (every configured limit is exceeded).

    With no tolerance configured any positive delta exceeds it.
    """
    if delta <= 0:
        return False
    pct, absolute = growth.get('pct'), growth.get('abs')
    if pct is None and absolute is None:
        return True
    over_abs = absolute is None or delta > absolute
    over_pct = pct is None or base <= 0 or delta * 100 > pct * base
    return over_abs and over_pct


def _compare_rule(rule: str, base: dict, now: dict, m: RuleMeta, diff: Diff) -> None:
    for key in sorted(set(base) | set(now)):
        b, c = base.get(key), now.get(key)
        if m.mode == KEEP:
            if b is not None and (c is None or c < b):
                diff.lost.append(Delta(rule, key, b, c))
            elif c is not None and (b is None or c > b):
                diff.unrecorded.append(Delta(rule, key, b, c))
            else:
                diff.carried += 1
        elif m.direction == 'higher':
            if b is None:
                diff.unrecorded.append(Delta(rule, key, b, c))
            elif c is None:
                diff.lost.append(Delta(rule, key, b, c))
            elif (exceeds(b, b - c, m.growth) if m.mode == 'budget' else c < b):
                diff.worse.append(Delta(rule, key, b, c))
            elif c > b:
                diff.slack.append(Delta(rule, key, b, c))
            elif c < b:
                diff.within.append(Delta(rule, key, b, c))
            else:
                diff.carried += 1
        elif b is None:
            diff.new.append(Delta(rule, key, None, c))
        elif c is None:
            diff.stale.append(Delta(rule, key, b, None))
        elif c > b:
            if m.mode == 'budget' and not exceeds(b, c - b, m.growth):
                diff.within.append(Delta(rule, key, b, c))
            else:
                diff.worse.append(Delta(rule, key, b, c))
        elif c < b:
            (diff.slack if m.mode == 'budget' else diff.stale).append(Delta(rule, key, b, c))
        else:
            diff.carried += 1


def compare(current: dict, baseline: dict, meta: dict[str, RuleMeta], renames: dict[str, str] | None = None) -> Diff:
    """Compare current entries with baseline entries. Both are {rule: {key: count}}."""
    base, renamed = rewrite_renames(baseline, renames or {})
    moves = pair_moves(base, current, meta)
    base = _apply_moves(base, moves)
    diff = Diff(moved=renamed + moves)
    for rule in sorted(set(base) | set(current)):
        _compare_rule(rule, base.get(rule, {}), current.get(rule, {}), meta.get(rule, RuleMeta()), diff)
    return diff


def updated_entries(current: dict, baseline: dict, meta: dict[str, RuleMeta], renames: dict[str, str] | None,
                    excepted) -> dict:
    """The baseline a safe update writes. `excepted(rule, key, count)` says whether an exception
    allows a keep-rule entry to be dropped (a test or API removal that was approved).
    """
    base, _ = rewrite_renames(baseline, renames or {})
    base = _apply_moves(base, pair_moves(base, current, meta))
    out: dict[str, dict] = {}
    for rule in sorted(set(base) | set(current)):
        m = meta.get(rule, RuleMeta())
        b_keys, c_keys = base.get(rule, {}), current.get(rule, {})
        bucket = {}
        for key in sorted(set(b_keys) | set(c_keys)):
            b, c = b_keys.get(key), c_keys.get(key)
            value = _updated_value(m, b, c, lambda: excepted(rule, key, c))
            if value is not None and value > 0:
                bucket[key] = value
        out[rule] = bucket
    return out


def _updated_value(m: RuleMeta, b, c, is_excepted):
    if m.mode == KEEP:
        if b is not None and (c is None or c < b):
            return c if is_excepted() else b
        return c if c is not None else b
    if m.direction == 'higher':
        if b is None:
            return c
        if c is None:
            return None if is_excepted() else b
        return max(b, c)
    if b is None:
        return None          # never adopt a new lower-is-better problem
    if c is None:
        return None          # fixed: drop it
    return min(b, c)         # tighten; never raise
