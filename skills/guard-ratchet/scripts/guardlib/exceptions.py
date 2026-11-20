"""Exceptions: the only way to let a new or worsened problem pass.

guards/exceptions.json:
  {"version": 1, "exceptions": [
    {"guard": "complexity", "rule": "fn-complexity", "key": "src/a.py#parse", "max": 45,
     "reason": "protocol table; splitting it hides the mapping", "approved_by": "alice",
     "expires": "2027-03-31"}
  ]}

rule and key accept * as a wildcard. A key must start with a literal prefix (src/legacy/*), except
the bare "*" for rule "rule-change" (one tool upgrade); policy exceptions name the exact setting and
protected and reclassification exceptions a file or a directory prefix. max caps the
tolerated count. Each entry needs a reason and an approver. The runner cannot verify the approver: inside one working tree anybody can edit this
file. The file is meant to sit behind CODEOWNERS review, which is what turns "approved_by" into
an actual approval (see references/trust-model.md).
"""

from __future__ import annotations

import datetime as dt
import json
import os

from .model import GuardError, Problem
from .policy import EXCEPTIONS_PATH, wildcard_match

REQUIRED = ('guard', 'rule', 'key', 'reason', 'approved_by')


def _directory_prefix(key: str) -> bool:
    """A protected-file key is an exact path or 'dir/…/*' (one runner upgrade = one approval)."""
    return '*' not in key or (key.endswith('/*') and '*' not in key[:-2] and len(key) > 2)
FIELDS = set(REQUIRED) | {'max', 'expires', 'id', 'note'}


class Exceptions:
    def __init__(self, entries: list[dict], today: dt.date | None = None):
        self.today = today or dt.date.today()
        self.entries = []
        self.problems: list[Problem] = []
        for index, entry in enumerate(entries):
            self._add(index, entry)

    def _add(self, index: int, entry: dict) -> None:
        ident = entry.get('id') or f"#{index + 1} {entry.get('guard')}/{entry.get('rule')}/{entry.get('key')}"
        missing = [f for f in REQUIRED if not str(entry.get(f, '')).strip()]
        unknown = set(entry) - FIELDS
        bad = None
        if missing:
            bad = f'missing {", ".join(missing)}'
        elif unknown:
            bad = f'unknown fields {", ".join(sorted(unknown))}'
        elif len(str(entry['reason']).strip()) < 10:
            bad = 'reason is too short to audit; say why this is acceptable'
        elif entry.get('max') is not None and not isinstance(entry['max'], (int, float)):
            bad = 'max must be a number'
        elif entry['guard'] == 'policy' and entry['rule'] == 'reclassified' and not _directory_prefix(str(entry['key'])):
            bad = 'reclassification exceptions must name a file or a directory prefix such as src/api/*'
        elif entry['guard'] == 'policy' and entry['rule'] != 'reclassified' and '*' in str(entry['key']):
            bad = 'policy exceptions must name the exact setting that is loosened'
        elif entry['guard'] == 'protected' and not _directory_prefix(str(entry['key'])):
            bad = 'protected exceptions must name a file or a directory prefix such as tools/guard/*'
        elif str(entry['key']).strip().startswith('*') and not (entry['rule'] == 'rule-change' and entry['key'] == '*'):
            bad = ('a key starting with a wildcard matches everywhere and would switch the rule off; name the key or '
                   'a literal prefix such as src/legacy/*')
        expires = None
        if not bad and entry.get('expires'):
            try:
                expires = dt.date.fromisoformat(str(entry['expires']))
            except ValueError:
                bad = 'expires must be YYYY-MM-DD'
        if not bad and expires and expires < self.today:
            bad = f'expired on {expires.isoformat()}'
        if bad:
            self.problems.append(Problem('exception', 'exceptions', key=ident,
                                         message=f'exception {ident}: {bad}', exceptable=False))
            return
        self.entries.append({**entry, 'id': ident, 'used': False})

    def match(self, guard: str, rule: str, key: str, count=None) -> str | None:
        for entry in self.entries:
            if entry['guard'] != guard or not wildcard_match(rule, entry['rule']) \
                    or not wildcard_match(key, entry['key']):
                continue
            if count is not None and entry.get('max') is not None and count > entry['max']:
                continue
            entry['used'] = True
            return entry['id']
        return None

    def unused(self) -> list[dict]:
        return [e for e in self.entries if not e['used']]

    def listing(self) -> list[dict]:
        keys = ('id', 'guard', 'rule', 'key', 'max', 'reason', 'approved_by', 'expires', 'used')
        return [{k: e[k] for k in keys if e.get(k) is not None} for e in self.entries]


def load(root: str, today: dt.date | None = None) -> Exceptions:
    path = os.path.join(root, EXCEPTIONS_PATH)
    if not os.path.exists(path):
        return Exceptions([], today)
    try:
        with open(path, encoding='utf-8') as fh:
            doc = json.load(fh)
    except json.JSONDecodeError as err:
        raise GuardError(f'{EXCEPTIONS_PATH} is not valid JSON: {err}') from err
    if not isinstance(doc, dict) or doc.get('version') != 1 or not isinstance(doc.get('exceptions'), list):
        raise GuardError(f'{EXCEPTIONS_PATH} must be {{"version": 1, "exceptions": [...]}}')
    return Exceptions(doc['exceptions'], today)


def add(root: str, entry: dict) -> None:
    """Append one exception after validating it the same way load() would."""
    probe = Exceptions([entry])
    if probe.problems:
        raise GuardError(probe.problems[0].message)
    path = os.path.join(root, EXCEPTIONS_PATH)
    doc = {'version': 1, 'exceptions': []}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            doc = json.load(fh)
    doc['exceptions'].append({k: v for k, v in entry.items() if v is not None})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
