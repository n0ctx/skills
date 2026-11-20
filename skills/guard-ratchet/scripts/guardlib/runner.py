"""Run the guards a change needs, judge their output, and lock the guard configuration.

Flow of `check`:
  change set (base..working tree) -> risk tier -> select guards -> run each -> judge against
  baseline + policy -> apply exceptions -> lock checks (policy, baselines, protected files) -> report

`update` runs the same guards and writes the only baseline changes that cannot hide a regression:
tightening, renamed/moved keys, newly recorded keep-entries, and (with --rules-changed or for a
guard without a baseline) a baseline derived by scanning the *base* commit with the current rules.

`--trusted` is the CI mode: the policy, baselines, detectors and tool configs are restored from
the base commit before running, so a change cannot loosen the rules that judge it.
"""

from __future__ import annotations

import glob
import os
import re
import shlex
import shutil
import tempfile
import time
from dataclasses import dataclass, field

from . import adapters, gitx, ratchet
from . import exceptions as exc
from . import policy as pol
from .builtins import DIFF_BUILTINS, SCAN_BUILTINS
from .context import Context, stale_inputs
from .model import KEEP, GuardError, Item, Problem, Scan
from .risk import TIERS, assess

STATUS_ORDER = ('fail', 'error', 'missing-tool', 'skipped', 'pass')


@dataclass
class Options:
    root: str
    base: str | None = None
    tier: str | None = None
    full: bool = False
    only: list[str] = field(default_factory=list)
    trusted: bool = False
    update: bool = False
    rules_changed: bool = False


@dataclass
class GuardResult:
    name: str
    status: str = 'pass'
    reason: str = ''
    problems: list[Problem] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    tool: dict = field(default_factory=dict)
    seconds: float = 0.0
    evidence: list[str] = field(default_factory=list)
    baseline_entries: int = 0
    baseline_written: str | None = None
    missing: list[str] = field(default_factory=list)

    def finalize(self) -> None:
        if self.status in ('pass', 'fail'):
            self.status = 'fail' if any(p.blocking for p in self.problems) else 'pass'
        if self.status == 'pass' and self.missing:
            self.status, self.reason = 'missing-tool', f"needs {'; '.join(self.missing)}"



# ─── selecting and executing guards ──────────────────────────────────────────
def _builtin(guard: dict) -> str | None:
    return guard.get('builtin')


def _parser(guard: dict) -> str:
    return {'snapshot': 'lines', 'metric': 'number'}.get(_builtin(guard) or '', guard.get('parse', 'findings'))


def has_baseline(guard: dict) -> bool:
    """Guards whose results are compared with a stored baseline (the others judge the diff only)."""
    builtin = _builtin(guard)
    if builtin in SCAN_BUILTINS or builtin in ('snapshot', 'metric'):
        return True
    return builtin is None and _parser(guard) != 'exit'


def _missing_tools(guard: dict) -> list[str]:
    return [t for t in guard.get('requires', []) if shutil.which(t) is None]


def _expand_path(pattern: str, scan_root: str, out: str, tmp: str) -> str:
    return pattern.replace('{root}', scan_root).replace('{out}', out).replace('{tmp}', tmp)


def _tool_version(ctx: Context, guard: dict) -> str | None:
    if not guard.get('version'):
        return None
    code, out, err = ctx.run(guard['version'], 60)
    text = (out or err).strip().splitlines()
    return text[0].strip() if code == 0 and text else None


def execute(ctx: Context, guard: dict) -> Scan:
    builtin = _builtin(guard)
    if builtin in SCAN_BUILTINS:
        return SCAN_BUILTINS[builtin](ctx, guard)
    if builtin in DIFF_BUILTINS:
        return DIFF_BUILTINS[builtin](ctx, guard)
    fmt = _parser(guard)
    out = os.path.join(ctx.tmp, f"{guard['name']}.out")
    command = ctx.expand(guard['run'], out)
    runs = max(1, int(guard.get('repeat', 1))) if fmt == 'number' else 1
    outputs, code, stderr = [], 0, ''
    for _ in range(runs):
        if os.path.exists(out):
            os.remove(out)
        started = time.time()
        code, stdout, stderr = ctx.run(command, guard.get('timeout', 900))
        if fmt == 'exit':
            return adapters.parse_exit(code, stdout + stderr, guard)
        if code not in guard.get('ok_exit', adapters.OK_EXIT[fmt]):
            scan = Scan(guard['name'])
            scan.integrity.append(f'`{guard["run"]}` exited {code}' + (f': {stderr.strip()[-600:]}' if stderr.strip() else ''))
            return scan
        if guard.get('input'):
            pattern = _expand_path(guard['input'], ctx.root, out, ctx.tmp)
            files = sorted(glob.glob(pattern if os.path.isabs(pattern) else os.path.join(ctx.project, pattern)))
            if not files:
                scan = Scan(guard['name'])
                scan.integrity.append(f"`{guard['run']}` produced no report at {guard['input']}")
                return scan
            stale = set(stale_inputs(files, started))
            if len(stale) == len(files):
                scan = Scan(guard['name'])
                scan.integrity.append(f"`{guard['run']}` did not write {', '.join(os.path.relpath(f, ctx.project) for f in files)}"
                                      f" during this run: a stale or committed report is not evidence")
                return scan
            files = [f for f in files if f not in stale]  # leftovers of earlier runs (incremental builds)
            for path in files:
                with open(path, encoding='utf-8', errors='replace') as fh:
                    outputs.append(fh.read())
        elif '{out}' in guard['run']:
            if not os.path.exists(out):
                scan = Scan(guard['name'])
                detail = (stderr or stdout).strip()[-600:]
                scan.integrity.append(f"`{guard['run']}` exited {code} without writing its report to {{out}}"
                                      + (f': {detail}' if detail else ''))
                return scan
            with open(out, encoding='utf-8', errors='replace') as fh:
                outputs.append(fh.read())
        else:
            outputs.append(stdout)
    scan = adapters.parse(fmt, outputs, code, guard, adapters.Paths(ctx.root, ctx.project))
    if not scan.tool.get('version'):
        version = _tool_version(ctx, guard)
        if version:
            scan.tool = {**scan.tool, 'version': version}
        elif guard.get('version'):
            # Without the version, an upgraded tool would be compared with an old baseline as if
            # nothing but the code had changed.
            scan.integrity.append(f"version command `{guard['version']}` failed or printed nothing")
    return scan


# ─── judging a scan ──────────────────────────────────────────────────────────
@dataclass
class Judged:
    scan: Scan
    items: list[Item]           # baseline-mode findings
    meta: dict[str, ratchet.RuleMeta]
    problems: list[Problem]


def _filter_scope(ctx: Context, items: list[Item]) -> list[Item]:
    return [i for i in items if not i.path or not (pol.excluded(ctx.policy, i.path)
                                                    or ctx.kind(i.path) in pol.EXEMPT_KINDS)]


def _judge_metrics(ctx: Context, guard: dict, scan: Scan) -> tuple[list[Item], list[Item], list[Item], dict]:
    findings, hard, advisory, specs = [], [], [], {}
    for metric in scan.metrics:
        spec = pol.threshold_spec(ctx.policy, metric['metric'], guard)
        if not spec or spec.get('mode', 'ratchet') == 'off':
            continue
        path = metric.get('path')
        if path and (pol.excluded(ctx.policy, path) or ctx.kind(path) in pol.EXEMPT_KINDS):
            continue
        kind = ctx.kind(path) if path else 'logic'
        limit = pol.limit_for(spec, kind, pol.language(path, ctx.policy) if path else None) if 'limit' in spec else 0
        if 'limit' in spec and limit is None:
            continue
        value, mode = metric['value'], spec.get('mode', 'ratchet')
        specs[metric['metric']] = spec
        label = f"{metric['metric']} {value} > {limit} ({kind})" if 'limit' in spec else f"{metric['metric']} {value}"
        item = Item(metric['metric'], metric['key'], value, path, metric.get('line'), label, mode)
        if 'limit' in spec and value <= limit:
            warn = spec.get('warn')
            if warn and value >= limit * warn:
                advisory.append(Item(metric['metric'], metric['key'], value, path, metric.get('line'),
                                     f"{metric['metric']} {value} is near the {kind} limit {limit}", 'advisory'))
            continue
        {'hard': hard, 'advisory': advisory}.get(mode, findings).append(item)
    return findings, hard, advisory, specs


def judge(ctx: Context, guard: dict, scan: Scan) -> Judged:
    """Apply scope, per-rule modes and metric thresholds. Returns baseline-mode items + problems."""
    name = guard['name']
    problems = [Problem('integrity', name, message=m, exceptable=False) for m in scan.integrity]
    command_guard = _builtin(guard) is None
    findings = _filter_scope(ctx, scan.findings) if command_guard else list(scan.findings)
    hard = _filter_scope(ctx, scan.hard) if command_guard else list(scan.hard)
    advisory = _filter_scope(ctx, scan.advisory) if command_guard else list(scan.advisory)
    m_find, m_hard, m_adv, specs = _judge_metrics(ctx, guard, scan)
    findings += m_find
    hard += m_hard
    advisory += m_adv
    modes = guard.get('modes', {})
    items = []
    for item in findings:
        mode = modes.get(item.rule, item.mode)
        if mode == 'off':
            continue
        if _builtin(guard) == 'snapshot':
            mode = KEEP
        item.mode = mode
        (hard if mode == 'hard' else advisory if mode == 'advisory' else items).append(item)
    meta = {}
    budget = guard.get('budget') or {}
    for item in items:
        spec = specs.get(item.rule, {})
        growth = spec.get('growth', {}) if spec else {k: budget[k] for k in ('pct', 'abs') if k in budget}
        meta[item.rule] = ratchet.RuleMeta(
            mode=item.mode, direction=budget.get('direction', 'lower') if _builtin(guard) == 'metric' else 'lower',
            growth=growth, strict_sync=guard.get('strict_sync', _builtin(guard) == 'snapshot'))
    for item in hard:
        problems.append(Problem('hard', name, item.rule, item.key, item.message or item.rule, item.count,
                                path=item.path, line=item.line))
    for item in advisory:
        problems.append(Problem('advisory', name, item.rule, item.key, item.message or item.rule, item.count,
                                path=item.path, line=item.line))
    if command_guard or _builtin(guard) in SCAN_BUILTINS:
        scanned = scan.coverage.get('scanned')
        if scanned == 0 and not scan.integrity:
            problems.append(Problem('integrity', name, message='the guard scanned nothing; check paths and tool '
                                    'configuration (an empty scan is not a pass)', exceptable=False))
    return Judged(scan, items, meta, problems)


LOST_TEXT = {'present': 'test removed', 'active': 'test is now skipped', 'surface': 'removed from the public surface'}


def _diff_problems(guard: str, diff: ratchet.Diff, items: list[Item], meta: dict, trusted: bool) -> list[Problem]:
    info = {(i.rule, i.key): i for i in items}
    out = []

    def problem(category, d, message, exceptable=True):
        item = info.get((d.rule, d.key))
        out.append(Problem(category, guard, d.rule, d.key, message, d.current, d.baseline,
                           item.path if item else None, item.line if item else None, exceptable))

    for d in diff.new:
        item = info.get((d.rule, d.key))
        problem('new', d, (item.message if item and item.message else f'{d.rule} {d.current}') + ' (not in baseline)')
    for d in diff.worse:
        problem('worse', d, f'{d.rule}: {d.baseline} -> {d.current}')
    for d in diff.lost:
        text = LOST_TEXT.get(d.rule, 'entry disappeared')
        problem('lost', d, f'{text}: {d.key}' if d.current is None else f'{d.rule} dropped {d.baseline} -> {d.current}')
    for d in diff.stale:
        if trusted:
            problem('improved', d, f'{d.rule}: {d.baseline} -> {d.current or 0}')
        else:
            problem('stale', d, f'{d.rule}: baseline {d.baseline}, now {d.current or 0}; run `guard.py update`', False)
    for d in diff.moved:
        if not trusted:
            problem('moved', d, f'{d.old_key} -> {d.key}; run `guard.py update`', False)
    for d in diff.unrecorded:
        strict = meta.get(d.rule, ratchet.RuleMeta()).strict_sync
        if strict and not trusted:
            problem('unrecorded', d, f'new {d.rule} entry not recorded: {d.key}; run `guard.py update`', False)
        else:
            problem('advisory', d, f'new {d.rule} entry {d.key} (recorded by `guard.py update`)')
    for d in diff.slack:
        problem('slack', d, f'{d.rule}: {d.baseline} -> {d.current}; `guard.py update` tightens it')
    for d in diff.within:
        problem('within-budget', d, f'{d.rule}: {d.baseline} -> {d.current} (within the growth budget)')
    return out


def _meta_with_baseline(meta: dict, baseline: dict) -> dict:
    out = dict(meta)
    for rule, mode in baseline.get('modes', {}).items():
        out.setdefault(rule, ratchet.RuleMeta(mode=mode))
    for rule in baseline.get('entries', {}):
        out.setdefault(rule, ratchet.RuleMeta())
    return out


def _scope_problem(guard: dict, policy: dict, baseline: dict, scan: Scan) -> Problem | None:
    scanned, recorded = scan.coverage.get('scanned'), baseline.get('scanned')
    if not isinstance(scanned, (int, float)) or not recorded:
        return None
    tolerance = guard.get('scope_tolerance', policy['scope_tolerance'])
    if scanned < recorded * (1 - tolerance):
        return Problem('scope', guard['name'], 'scope', 'scanned',
                       f"scanned {scanned} {scan.coverage.get('unit', '')} but the baseline was recorded with "
                       f"{recorded}: the scan lost more than {int(tolerance * 100)}% of its scope", scanned, recorded)
    return None


# ─── baselines on disk ───────────────────────────────────────────────────────
def baseline_path(root: str, name: str) -> str:
    return os.path.join(root, pol.BASELINE_DIR, f'{name}.json')


def read_baseline(root: str, name: str) -> dict | None:
    path = baseline_path(root, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as fh:
        return ratchet.parse_baseline(fh.read(), name)


METRIC_SOURCES = {'lizard': ('fn-complexity', 'fn-length'), 'size': ('file-size',)}


def _fingerprint(ctx: Context, guard: dict) -> str:
    """Thresholds enter the fingerprint only for guards that can report those metrics: a custom
    detector (findings format) may report any metric, lizard and size report known ones."""
    source = _builtin(guard) or _parser(guard)
    if source == 'findings':
        metrics = tuple(ctx.policy['thresholds'])
    else:
        metrics = METRIC_SOURCES.get(source, ())
    return pol.fingerprint(ctx.policy, guard, pol.config_digests(ctx.project, guard.get('config_files') or []), metrics)


def _rule_change(guard: dict, baseline: dict, fingerprint: str, scan: Scan) -> Problem | None:
    if baseline.get('legacy') or not baseline.get('fingerprint'):
        return None
    tool = scan.tool.get('version')
    reasons = []
    if baseline['fingerprint'] != fingerprint:
        reasons.append('the guard definition, thresholds, kind globs, excludes or tool configuration changed')
    if baseline.get('tool') and baseline['tool'] != tool:
        reasons.append(f"tool version is {tool or 'unknown'}, the baseline was recorded with {baseline['tool']} (pin it)")
    if not reasons:
        return None
    return Problem('rule-change', guard['name'], 'rule-change', 'fingerprint',
                   '; '.join(reasons) + '. Findings may differ for reasons other than the code: rebuild with '
                   '`guard.py update --rules-changed`', exceptable=False)


# ─── locks ───────────────────────────────────────────────────────────────────
SHELL_OPERATORS = {'&&', '||', ';', '|', '&', 'then', 'do', 'else'}
# Commands that run another command: the next non-option token is the real command.
WRAPPERS = {'env', 'exec', 'time', 'nice', 'timeout', 'xargs', 'npx', 'pnpx', 'bunx', 'uv', 'uvx', 'poetry',
            'pipenv', 'pdm', 'hatch', 'rye', 'pixi', 'conda', 'mamba', 'run', 'tool', 'dlx', 'exec'}
# Interpreters: the first non-option argument is the script they run.
INTERPRETERS = {'python', 'python3', 'pypy', 'pypy3', 'node', 'deno', 'bun', 'bash', 'sh', 'zsh', 'dash', 'ruby',
                'perl', 'php', 'Rscript', 'pwsh', 'powershell', 'lua', 'tsx', 'ts-node', 'java', 'groovy',
                'kotlin', 'elixir', 'escript', 'julia'}
INLINE_CODE = {'-c', '-e', '--eval', '-p', '--print', '-Command'}
CONFIG_OPTIONS = {'--config', '--config-file', '--configfile', '--rcfile', '--rules', '--rulesdir', '--ruleset',
                  '--rule-file', '--settings'}


def _command_paths(command: str) -> list[tuple[str, str]]:
    """(kind, token) pairs for what a shell command executes: 'script' for the program or the
    interpreter's script argument, 'module' for `python -m`, 'config' for rule/config options.
    Plain arguments (scan targets, data files) are not code the command runs."""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()
    out, state, interpreter, i = [], 'command', None, 0
    while i < len(tokens):
        token = tokens[i]
        name, _, value = token.partition('=')
        if token in SHELL_OPERATORS:
            state = 'command'
        elif name in CONFIG_OPTIONS:
            if value:
                out.append(('config', value))
            elif i + 1 < len(tokens):
                out.append(('config', tokens[i + 1]))
                i += 1
        elif state == 'command':
            base = os.path.basename(token)
            if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', token) or token.startswith('-'):
                pass
            elif base == 'cd':
                i += 1  # its directory argument
            elif base in WRAPPERS:
                pass
            elif base in INTERPRETERS or re.fullmatch(r'python3?(\.\d+)?', base):
                state, interpreter = 'interpreter', base
            else:
                out.append(('script', token))
                state = 'args'
        elif state == 'interpreter':
            if token == '-m' and i + 1 < len(tokens):
                out.append(('module', tokens[i + 1]))
                state = 'args'
                i += 1
            elif token in INLINE_CODE:
                if interpreter in ('bash', 'sh', 'zsh', 'dash') and i + 1 < len(tokens):
                    out += _command_paths(tokens[i + 1])  # `bash -c "python tools/x.py"`
                state = 'args'
                i += 1
            elif not token.startswith('-'):
                out.append(('script', token))
                state = 'args'
        i += 1
    return out


def _detector_dirs(root: str, guards: list[dict], base: str | None = None) -> list[str]:
    """In-repo code and rule files a guard command runs: the program or interpreter script
    (`tools/x.py`, `{root}/x.py`, `./x.sh`), `python -m` modules, and values of rule/config options.
    A script inside a tooling directory (kind `script`, such as tools/ or scripts/) protects its whole
    directory, since helpers sit next to it; elsewhere only the file itself. A path counts when it
    exists in the working tree or at base, so deleting a detector does not drop its protection.
    Scripts reached indirectly (`npm run`, `make`, imports) cannot be seen here; list them in
    `config_files`."""
    def kind_at(rel: str) -> str | None:
        if os.path.isfile(os.path.join(root, rel)):
            return 'blob'
        if os.path.isdir(os.path.join(root, rel)):
            return 'tree'
        if base:
            return (gitx.git(root, 'cat-file', '-t', f'{base}:{rel}', check=False) or '').strip() or None
        return None

    def clean(token: str) -> str | None:
        rel = token.replace('{root}/', '')
        while rel.startswith('./'):
            rel = rel[2:]
        if not rel or '{' in rel or rel.startswith(('/', '-')) or '..' in rel.split('/'):
            return None
        return rel.rstrip('/')

    defaults = pol.effective({})
    out = set()
    for guard in guards:
        for kind, token in _command_paths(guard.get('run') or ''):
            if kind == 'module':
                if not re.fullmatch(r'[\w.]+', token):
                    continue
                module = token.replace('.', '/')
                if kind_at(f'{module}.py') == 'blob':
                    out.add(f'{module}.py')
                elif kind_at(module) == 'tree':
                    out.add(f'{module}/**')
                continue
            rel = clean(token)
            if not rel:
                continue
            found = kind_at(rel)
            if found == 'tree' and kind == 'config':
                out.add(f'{rel}/**')
            elif found == 'blob':
                folder = os.path.dirname(rel)
                tooling = folder and pol.kind_by_path(defaults, rel) == 'script'
                out.add(f'{folder}/**' if kind == 'script' and tooling else rel)
    return sorted(out)


def protected_globs(root: str, policy: dict, base: str | None = None) -> list[str]:
    return sorted(set(policy['protected']) | {policy['runner'].rstrip('/') + '/**'}
                  | set(_detector_dirs(root, policy['guards'], base)))


def lock_checks(ctx: Context) -> list[Problem]:
    """Loosening relative to base: policy and baselines. Each loosening needs an exception."""
    problems = []
    base_text = gitx.show_text(ctx.project, ctx.changes.base, pol.POLICY_PATH)
    base_policy = None
    if base_text is None:
        problems.append(Problem('advisory', 'policy', message='the guard policy is new in this change: the initial '
                                'setup (guards, thresholds, baselines) needs human review'))
    else:
        try:
            _, base_policy = pol.load(ctx.project, base_text)
        except GuardError as err:
            problems.append(Problem('advisory', 'policy', message=f'base policy unreadable ({err}); lock skipped'))
    if base_policy:
        for where, message in pol.loosenings(base_policy, ctx.policy):
            problems.append(Problem('locked', 'policy', 'loosen', where, message))
        problems += _baseline_locks(ctx, base_policy)
    return problems + protected_changes(ctx, base_policy)


def protected_changes(ctx: Context, base_policy: dict | None) -> list[Problem]:
    """Changes to guard code, CI configuration and code owners, and files that turned "generated"."""
    problems = []
    ignore = {pol.POLICY_PATH, pol.EXCEPTIONS_PATH}
    globs = protected_globs(ctx.project, ctx.policy, ctx.changes.base)
    if base_policy:
        globs = sorted(set(globs) | set(protected_globs(ctx.project, base_policy, ctx.changes.base)))
    for path, change in sorted(ctx.changes.files.items()):
        candidates = {path, change.old_path} - {None}
        if any(p in ignore or p.startswith(pol.BASELINE_DIR + '/') for p in candidates):
            continue
        if any(pol.any_match(p, globs) for p in candidates):
            problems.append(Problem('protected', 'protected', 'changed', path,
                                    f'protected file {"deleted" if change.status == "D" else "changed"}: guard code, '
                                    f'CI configuration and code owners need an approved exception'))
    problems += _reclassified(ctx)
    return problems


# Kinds every source guard judges. Moving code out of them loosens or removes its guards; moving
# between them changes only the limits (a .js file renamed to .jsx is judged as UI).
SOURCE_KINDS = ('logic', 'model', 'ui')


def _reclassified(ctx: Context) -> list[Problem]:
    """Code that escapes its guards by changing kind: a file that gains a generated header, moves
    into vendor/, tests, scripts or migrations, or is added already marked generated."""
    problems = []
    for path, change in sorted(ctx.changes.files.items()):
        if not pol.is_code(path, ctx.policy) or change.status == 'D':
            continue
        kind = ctx.kind(path)
        if change.status == 'A':
            if kind == 'generated' and pol.kind_by_path(ctx.policy, path) != 'generated':
                folder = os.path.dirname(path)
                problems.append(Problem('locked', 'policy', 'reclassified', path,
                                        'new file is exempt from every source guard only because of its generated-code '
                                        'header; approve the generator output with one exception for its directory '
                                        f"(--guard policy --rule reclassified --key '{folder + '/*' if folder else path}')"))
            elif kind == 'vendor':
                problems.append(Problem('advisory', 'policy', 'vendored', path,
                                        'new file under a vendor path: no source guard looks at it'))
            continue
        old = change.old_path or path
        before = ctx.base_kind(old)
        if before not in SOURCE_KINDS or kind == before:
            continue
        how = 'gained a generated-code header' if change.status == 'M' else f'moved from {old}'
        if kind in SOURCE_KINDS:
            problems.append(Problem('advisory', 'policy', 'reclassified', path,
                                    f'{before} code is now judged with the {kind} limits ({how})'))
        else:
            problems.append(Problem('locked', 'policy', 'reclassified', path,
                                    f'{before} code became {kind} ({how}), which loosens or removes its guards'))
    return problems


def _baseline_locks(ctx: Context, base_policy: dict) -> list[Problem]:
    problems = []
    names = {g['name'] for g in ctx.policy['guards']} & {g['name'] for g in base_policy['guards']}
    for name in sorted(names):
        rel = f'{pol.BASELINE_DIR}/{name}.json'
        base_text = gitx.show_text(ctx.project, ctx.changes.base, rel)
        if base_text is None:
            continue
        try:
            base_doc = ratchet.parse_baseline(base_text, name)
            cur_doc = read_baseline(ctx.project, name)
        except GuardError as err:
            problems.append(Problem('locked', name, 'baseline', rel, f'baseline unreadable: {err}'))
            continue
        if cur_doc is None:
            problems.append(Problem('locked', name, 'baseline', rel, 'baseline deleted while the guard still exists'))
            continue
        if base_doc.get('fingerprint') and not cur_doc.get('fingerprint'):
            problems.append(Problem('locked', name, 'baseline', rel, 'baseline fingerprint removed'))
            continue
        if base_doc.get('fingerprint') != cur_doc.get('fingerprint') and not base_doc.get('legacy'):
            problems.append(Problem('advisory', name, 'baseline', rel,
                                    'baseline rebuilt for a rule change; the trusted CI run verifies it against '
                                    'the base rules'))
            continue
        meta = _meta_with_baseline({}, cur_doc)
        meta.update(_meta_with_baseline({}, base_doc))
        # Renames apply to both sides: a baseline not yet updated after a rename still names the old
        # path, and that is `moved` (fixed by update), not an entry added by hand.
        cur_entries, _ = ratchet.rewrite_renames(cur_doc['entries'], ctx.changes.renames)
        diff = ratchet.compare(cur_entries, base_doc['entries'], meta, ctx.changes.renames)
        for d in diff.new + diff.worse:
            change = f'added with {d.current}' if d.baseline is None else f'raised {d.baseline} -> {d.current}'
            problems.append(Problem('locked', name, d.rule, d.key, f'baseline entry {change} by hand', d.current,
                                    d.baseline))
        for d in diff.lost:
            problems.append(Problem('locked', name, d.rule, d.key, f'keep-entry removed from the baseline: {d.key}'))
        tolerance = ctx.policy['scope_tolerance']
        if base_doc.get('scanned') and (cur_doc.get('scanned') or 0) < base_doc['scanned'] * (1 - tolerance):
            problems.append(Problem('locked', name, 'scope', 'scanned',
                                    f"baseline scan size lowered {base_doc['scanned']} -> {cur_doc.get('scanned')}"))
    return problems


# ─── trusted mode ────────────────────────────────────────────────────────────
class TrustedTree:
    """Restore guard configuration from base into the (disposable) CI working tree, then put the
    change's versions back. Files the change added under those globs (a new nested lint config, a
    new baseline) are set aside for the run, so only the base configuration is in force. Refuses
    to run over uncommitted edits to those paths."""

    def __init__(self, root: str, base: str, globs: list[str]):
        self.root, self.base = root, base
        base_paths = set(gitx.base_files(root, base))
        self.paths = sorted(p for p in base_paths if pol.any_match(p, globs))
        self.head_paths = {p for p in gitx.git(root, 'ls-files', '-z').split('\0') if p}
        self.added = sorted(p for p in self.head_paths - base_paths if pol.any_match(p, globs))
        self.originals: dict[str, bytes | None] = {}

    def __enter__(self):
        touched = self.paths + self.added
        if touched:
            dirty = gitx.git(self.root, 'status', '--porcelain', '--', *touched)
            if dirty.strip():
                raise GuardError('--trusted needs a clean working tree for guard configuration:\n' + dirty)
            self.originals = {p: gitx.show(self.root, 'HEAD', p) if p in self.head_paths else None for p in touched}
        if self.paths:
            gitx.git(self.root, 'checkout', self.base, '--', *self.paths)
        for path in self.added:
            if os.path.exists(os.path.join(self.root, path)):
                os.remove(os.path.join(self.root, path))
        return self

    def __exit__(self, *exc_info):
        keep = [p for p in self.paths if p in self.head_paths] + self.added
        if keep:
            gitx.git(self.root, 'checkout', 'HEAD', '--', *keep)
        if self.paths:
            gitx.git(self.root, 'reset', '-q', '--', *self.paths, check=False)
        for path in self.paths:
            if path not in self.head_paths and os.path.exists(os.path.join(self.root, path)):
                os.remove(os.path.join(self.root, path))


def trusted_globs(root: str, base: str) -> list[str]:
    text = gitx.show_text(root, base, pol.POLICY_PATH)
    if text is None:
        raise GuardError('--trusted: the base commit has no guard policy (bootstrap change: review it by hand)')
    _, base_policy = pol.load(root, text)
    configs = [c for g in base_policy['guards'] for c in g.get('config_files') or []]
    runner = base_policy['runner'].rstrip('/') + '/**'
    return sorted({pol.POLICY_PATH, pol.BASELINE_DIR + '/**', runner, *_detector_dirs(root, base_policy['guards'], base),
                   *configs})


# ─── baseline derivation and update ──────────────────────────────────────────
def _base_scan(ctx: Context, guard: dict) -> tuple[Judged | None, str | None]:
    """Run a guard against the base commit with the current rules."""
    if _builtin(guard) is None and '{root}' not in guard.get('run', ''):
        return None, 'its run command does not use {root}, so it cannot scan the base commit'
    if not ctx.changes.files:
        return judge(ctx, guard, execute(ctx, guard)), None
    with gitx.BaseWorktree(ctx.project, ctx.changes.base, guard.get('config_files')) as tree:
        base_ctx = Context(tree, ctx.project, ctx.policy, None, ctx.tmp)
        judged = judge(base_ctx, guard, execute(base_ctx, guard))
    return judged, None


def _derive_baseline(ctx: Context, guard: dict, old: dict | None, fingerprint: str, exceptions, result: GuardResult):
    """New baseline = findings of the base commit under current rules. Entries the old baseline had
    but the new rules no longer see on the same code are detection changes: each needs an exception."""
    if ctx.changes.base is None:
        judged = judge(ctx, guard, execute(ctx, guard))
        result.problems.append(Problem('advisory', guard['name'], message='no base commit: baseline taken from the '
                                       'working tree, review it as part of the initial setup'))
    else:
        judged, why = _base_scan(ctx, guard)
        if judged is None:
            result.problems.append(Problem('integrity', guard['name'], message=f'cannot rebuild the baseline: {why}',
                                           exceptable=False))
            return None
    if any(p.category == 'integrity' for p in judged.problems):
        result.problems += [p for p in judged.problems if p.category == 'integrity']
        return None
    entries = ratchet.entries_of(judged.items)
    if old is None and ctx.changes.base:
        # A baseline deleted in the working tree still has its base version: compare against that,
        # or deleting it would skip the check below.
        text = gitx.show_text(ctx.project, ctx.changes.base, f"{pol.BASELINE_DIR}/{guard['name']}.json")
        old = ratchet.parse_baseline(text, guard['name']) if text else None
    if old:
        meta = _meta_with_baseline(judged.meta, old)
        diff = ratchet.compare(entries, old['entries'], meta)
        dropped = diff.stale + diff.slack + diff.lost
        blocked = [d for d in dropped if not exceptions.match(guard['name'], 'rule-change', d.key)
                   and not exceptions.match(guard['name'], d.rule, d.key)]
        if blocked:
            for d in blocked:
                result.problems.append(Problem('rule-change', guard['name'], d.rule, d.key,
                                               f'the new rules no longer report {d.rule} {d.key} '
                                               f'({d.baseline} -> {d.current or 0}) on unchanged base code: detection '
                                               f'was loosened; add an exception (rule "rule-change") if intended'))
            return None
    return {'version': 2, 'guard': guard['name'], 'fingerprint': fingerprint,
            'tool': judged.scan.tool.get('version'), 'scanned': judged.scan.coverage.get('scanned'),
            'modes': {r: m.mode for r, m in judged.meta.items()}, 'entries': entries}


def _updated_baseline(ctx: Context, guard: dict, judged: Judged, old: dict, fingerprint: str, exceptions) -> dict:
    meta = _meta_with_baseline(judged.meta, old)
    current = ratchet.entries_of(judged.items)
    entries = ratchet.updated_entries(current, old['entries'], meta, ctx.changes.renames,
                                      lambda rule, key, count: exceptions.match(guard['name'], rule, key) is not None)
    scanned, recorded = judged.scan.coverage.get('scanned'), old.get('scanned')
    tolerance = guard.get('scope_tolerance', ctx.policy['scope_tolerance'])
    if isinstance(scanned, (int, float)) and recorded and scanned < recorded * (1 - tolerance) \
            and not exceptions.match(guard['name'], 'scope', 'scanned'):
        scanned = recorded
    modes = {**old.get('modes', {}), **{r: m.mode for r, m in judged.meta.items()}}
    return {'version': 2, 'guard': guard['name'], 'fingerprint': fingerprint,
            'tool': judged.scan.tool.get('version') or old.get('tool'),
            'scanned': scanned if scanned is not None else recorded, 'modes': modes, 'entries': entries}


def _write_baseline(root: str, doc: dict) -> str:
    path = baseline_path(root, doc['guard'])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(ratchet.dump_baseline(doc))
    return os.path.relpath(path, root)


# ─── one guard ───────────────────────────────────────────────────────────────
def run_guard(ctx: Context, guard: dict, opts: Options, exceptions) -> GuardResult:
    result = GuardResult(guard['name'])
    start = time.monotonic()
    try:
        _run_guard(ctx, guard, opts, exceptions, result)
    finally:
        result.seconds = round(time.monotonic() - start, 2)
    return result


def _run_guard(ctx: Context, guard: dict, opts: Options, exceptions, result: GuardResult) -> None:
    name = guard['name']
    missing = _missing_tools(guard)
    if missing:
        result.status, result.reason = 'missing-tool', f'not installed: {", ".join(missing)}'
        return
    scan = execute(ctx, guard)
    judged = judge(ctx, guard, scan)
    result.coverage, result.tool, result.evidence = scan.coverage, scan.tool, scan.evidence
    result.missing = list(scan.missing)
    result.problems += judged.problems
    if any(p.category == 'integrity' for p in judged.problems):
        result.status = 'error'
        return
    if not has_baseline(guard):
        return
    stored = read_baseline(ctx.project, name)
    fingerprint = _fingerprint(ctx, guard)
    if opts.update and (opts.rules_changed or stored is None):
        doc = _derive_baseline(ctx, guard, stored, fingerprint, exceptions, result)
        if doc is None:
            result.status = 'error' if any(p.category == 'integrity' for p in result.problems) else 'fail'
            return
        result.baseline_written = _write_baseline(ctx.project, doc)
        stored = ratchet.parse_baseline(ratchet.dump_baseline(doc), name)
    baseline = stored or ratchet.empty_baseline(name)
    change = _rule_change(guard, baseline, fingerprint, scan) if stored else None
    if change:
        result.problems.append(change)
        return
    if opts.update and stored is not None and not result.baseline_written:
        doc = _updated_baseline(ctx, guard, judged, baseline, fingerprint, exceptions)
        if ratchet.dump_baseline(doc) != ratchet.dump_baseline({**baseline, 'version': 2}):
            result.baseline_written = _write_baseline(ctx.project, doc)
        baseline = ratchet.parse_baseline(ratchet.dump_baseline(doc), name)
    if baseline.get('legacy'):
        result.problems.append(Problem('advisory', name, message='legacy v1 baseline: `guard.py update` records the '
                                       'rule fingerprint and scan size'))
    meta = _meta_with_baseline(judged.meta, baseline)
    diff = ratchet.compare(ratchet.entries_of(judged.items), baseline['entries'], meta, ctx.changes.renames
                           if ctx.changes else None)
    result.problems += _diff_problems(name, diff, judged.items, meta, opts.trusted)
    scope = _scope_problem(guard, ctx.policy, baseline, scan)
    if scope:
        result.problems.append(scope)
    result.baseline_entries = sum(len(v) for v in baseline['entries'].values())
    if stored is None and judged.items and not opts.update:
        result.problems.append(Problem('advisory', name, message='no baseline yet: `guard.py update` derives it '
                                       'from the base commit'))


def _apply_exceptions(problems: list[Problem], exceptions) -> None:
    for p in problems:
        if p.category in ('new', 'worse', 'lost', 'hard', 'locked', 'protected', 'scope') and p.exceptable:
            p.excepted_by = exceptions.match(p.guard, p.rule, p.key, p.current)


# ─── whole run ───────────────────────────────────────────────────────────────
@dataclass
class Run:
    root: str
    base: str | None
    risk: dict
    tier: str
    requested_tier: str | None
    trusted: bool
    guards: list[GuardResult]
    global_problems: list[Problem]
    exceptions: list[dict]

    @property
    def problems(self) -> list[Problem]:
        return self.global_problems + [p for g in self.guards for p in g.problems]

    @property
    def verdict(self) -> str:
        if any(p.blocking for p in self.problems):
            return 'fail'
        if self.incomplete:
            return 'incomplete'
        return 'pass'

    @property
    def incomplete(self) -> list[str]:
        reasons = [f'{g.name}: {g.reason}' for g in self.guards if g.status == 'missing-tool' and g.reason
                   and not g.reason.startswith('optional')]
        if self.requested_tier and TIERS.index(self.requested_tier) < TIERS.index(self.risk['tier']):
            reasons.append(f"ran tier {self.requested_tier}, the change needs {self.risk['tier']}")
        return reasons

    @property
    def exit_code(self) -> int:
        return {'fail': 1, 'incomplete': 3, 'pass': 0}[self.verdict]


def select(policy: dict, risk_roles: set[str], tier: str, opts: Options) -> list[tuple[dict, str | None]]:
    """Each guard with the reason it is skipped (None = run it)."""
    out = []
    for guard in policy['guards']:
        if opts.only and guard['name'] not in opts.only:
            continue
        reason = None
        if TIERS.index(guard.get('tier', 'standard')) > TIERS.index(tier):
            reason = f"tier {guard.get('tier')} not required for this change (tier {tier})"
        elif guard.get('when') and not opts.full and not set(guard['when']) & risk_roles:
            reason = f"no change in {'/'.join(guard['when'])}"
        out.append((guard, reason))
    return out


def run(opts: Options) -> Run:
    root = opts.root
    raw, policy = pol.load(root)
    if opts.trusted and not opts.base:
        # The policy's `base` belongs to the change being judged; a change could point it at itself.
        raise GuardError('--trusted needs an explicit --base (the target branch or commit), not the policy value')
    unknown = sorted(set(opts.only or ()) - {g['name'] for g in policy['guards']})
    if unknown:
        raise GuardError(f"--only names unknown guards: {', '.join(unknown)}")
    base = gitx.resolve_base(root, opts.base or policy.get('base'))
    changes = gitx.changeset(root, base) if gitx.is_repo(root) else gitx.changeset(root, None)
    if opts.trusted:
        if base is None:
            raise GuardError('--trusted needs a base commit')
        with TrustedTree(root, base, trusted_globs(root, base)) as tree:
            raw, policy = pol.load(root)
            return _run(opts, root, raw, policy, changes, tree.originals)
    return _run(opts, root, raw, policy, changes)


def _run(opts: Options, root: str, raw: dict, policy: dict, changes, originals=None) -> Run:
    tmp = tempfile.mkdtemp(prefix='guard-run-')
    try:
        ctx = Context(root, root, policy, changes, tmp, originals or {})
        risk = assess(ctx)
        tier = risk.tier
        if opts.full:
            tier = 'strict'
        elif opts.tier:
            tier = opts.tier
        exceptions = exc.load(root)
        global_problems = list(exceptions.problems)
        if changes.base and opts.trusted:
            global_problems += protected_changes(ctx, None)
        elif changes.base:
            global_problems += lock_checks(ctx)
        results = []
        for guard, reason in select(policy, set(risk.roles), tier, opts):
            if reason:
                results.append(GuardResult(guard['name'], 'skipped', reason))
                continue
            result = run_guard(ctx, guard, opts, exceptions)
            if result.status == 'missing-tool' and not guard.get('required', True):
                result.reason = f'optional, {result.reason}'
            results.append(result)
        _apply_exceptions(global_problems, exceptions)
        for result in results:
            _apply_exceptions(result.problems, exceptions)
            result.finalize()
        for entry in exceptions.unused():
            global_problems.append(Problem('advisory', 'exceptions', key=entry['id'],
                                           message=f"exception {entry['id']} matched nothing in this run "
                                                   f"(delete it once the base branch no longer needs it)"))
        return Run(root, changes.base, risk.to_json(), tier, opts.tier, opts.trusted, results, global_problems,
                   exceptions.listing())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
