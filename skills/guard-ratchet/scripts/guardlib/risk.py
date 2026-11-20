"""Change risk: which roles a change touches and which verification tier it needs.

The tier is computed from the diff, file roles and test-change evidence. The agent does not get to
declare it. A lower tier can be requested for a quick local loop, but the result is then reported
as incomplete, never as a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import policy as pol
from .builtins import test_change_signals
from .context import Context

TIERS = pol.TIERS


@dataclass
class Risk:
    tier: str = 'standard'
    roles: dict[str, list[str]] = field(default_factory=dict)   # role -> changed files
    reasons: list[str] = field(default_factory=list)
    changed_files: int = 0
    changed_lines: int = 0

    def to_json(self) -> dict:
        return {'tier': self.tier, 'reasons': self.reasons, 'changed_files': self.changed_files,
                'changed_lines': self.changed_lines, 'roles': {r: f[:20] for r, f in sorted(self.roles.items())}}


def assess(ctx: Context) -> Risk:
    policy = ctx.policy
    risk = Risk(changed_files=len(ctx.changes.files), changed_lines=ctx.changes.changed_lines)
    for path, change in sorted(ctx.changes.files.items()):
        roles = pol.roles_of(policy, path)
        if change.old_path:
            roles |= pol.roles_of(policy, change.old_path)
        if pol.is_code(path, policy):
            roles.add(ctx.base_kind(path) if change.status == 'D' else ctx.kind(path))
        for role in roles:
            risk.roles.setdefault(role, []).append(path)
    if not ctx.changes.files:
        risk.tier = 'fast'
        risk.reasons.append('no changes against base')
        return risk
    strict = sorted(set(policy['risk']['strict_roles']) & set(risk.roles))
    for role in strict:
        risk.reasons.append(f'{role}: {", ".join(risk.roles[role][:3])}')
    if risk.changed_lines > policy['risk']['strict_changed_lines']:
        risk.reasons.append(f"{risk.changed_lines} changed lines > {policy['risk']['strict_changed_lines']}")
    if risk.changed_files > policy['risk']['strict_changed_files']:
        risk.reasons.append(f"{risk.changed_files} changed files > {policy['risk']['strict_changed_files']}")
    signals = test_change_signals(ctx)
    if signals['deleted']:
        risk.reasons.append(f"test files deleted: {', '.join(signals['deleted'][:3])}")
    if signals['reduced']:
        risk.reasons.append(f"assertions removed in {', '.join(p for p, *_ in signals['reduced'][:3])}")
    if signals['rewritten'] and signals['source_lines']:
        risk.reasons.append('test expectations rewritten alongside implementation changes')
    if risk.reasons:
        risk.tier = 'strict'
        return risk
    fast_only = set(policy['risk']['fast_roles'])
    if all(pol.roles_of(policy, p) & fast_only and not pol.is_code(p, policy) for p in ctx.changes.files):
        risk.tier = 'fast'
        risk.reasons.append('only ' + '/'.join(sorted(fast_only)) + ' changed')
    else:
        risk.reasons.append('ordinary code change')
    return risk
