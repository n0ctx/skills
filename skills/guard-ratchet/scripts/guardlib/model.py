"""Data model shared by the runner: detector items, scan results, judged problems.

Terms match references/contract.md:
- Item: one finding from a detector or built-in guard (rule, stable key, count, mode).
- Scan: everything one guard produced in one run, including coverage and integrity problems.
- Problem: a verdict the runner derived (new, worse, stale, hard, ...), with a category and
  whether it blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DETECTOR_SCHEMA = 'guard-ratchet/detector@2'
REPORT_SCHEMA = 'guard-ratchet/report@1'
BASELINE_VERSION = 2

# Judgement modes, weakest first. The order is what "loosening" is measured against.
MODE_ORDER = ('off', 'advisory', 'budget', 'ratchet', 'hard')
KEEP = 'keep'  # "may only grow": test inventory, public API surface
BASELINE_MODES = ('ratchet', 'budget', KEEP)

# Blocking categories. Each fails the run unless an exception covers it;
# 'integrity' can never be excepted.
BLOCKING = (
    'integrity',      # the scan cannot be trusted: parse failure, tool error, incomplete coverage
    'hard',           # hard rule
    'new',            # new problem
    'worse',          # existing problem got worse
    'lost',           # keep-rule entry disappeared: test removed/skipped, public API removed
    'stale',          # baseline not tightened after an improvement
    'moved',          # code moved and the baseline key was not rewritten
    'unrecorded',     # new keep-rule entry not recorded (only for guards with strict_sync)
    'scope',          # scan volume dropped well below the baseline's
    'rule-change',    # rules, thresholds, tool version or tool config changed: rebuild from base
    'locked',         # policy or baseline loosened relative to base
    'protected',      # a protected file changed
    'exception',      # an exception entry is invalid or expired
)
NON_BLOCKING = ('advisory', 'excepted', 'slack', 'improved', 'within-budget')


class GuardError(Exception):
    """Configuration, argument or input error: exit code 2."""


@dataclass
class Item:
    rule: str
    key: str
    count: float = 1
    path: str | None = None
    line: int | None = None
    message: str = ''
    mode: str = 'ratchet'

    def where(self) -> str:
        if self.path and self.line:
            return f'{self.path}:{self.line}'
        return self.path or ''


@dataclass
class Scan:
    guard: str
    tool: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    integrity: list[str] = field(default_factory=list)
    hard: list[Item] = field(default_factory=list)
    advisory: list[Item] = field(default_factory=list)
    findings: list[Item] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    # Capabilities the scan lacked for part of its input (e.g. no TOML parser): the guard did not
    # fail, but it did not check everything, so the run is incomplete rather than a pass.
    missing: list[str] = field(default_factory=list)


@dataclass
class Problem:
    category: str
    guard: str
    rule: str = ''
    key: str = ''
    message: str = ''
    current: float | None = None
    baseline: float | None = None
    path: str | None = None
    line: int | None = None
    exceptable: bool = True
    excepted_by: str | None = None

    @property
    def blocking(self) -> bool:
        return self.category in BLOCKING and not self.excepted_by

    def to_json(self) -> dict:
        out = {'category': self.category, 'guard': self.guard}
        for name in ('rule', 'key', 'message', 'current', 'baseline', 'path', 'line', 'excepted_by'):
            value = getattr(self, name)
            if value not in (None, ''):
                out[name] = value
        if self.category in BLOCKING:
            out['blocking'] = self.blocking
            out['exceptable'] = self.exceptable
        return out


def mode_rank(mode: str | None) -> int:
    if mode == KEEP:
        return MODE_ORDER.index('ratchet')
    return MODE_ORDER.index(mode) if mode in MODE_ORDER else 0
