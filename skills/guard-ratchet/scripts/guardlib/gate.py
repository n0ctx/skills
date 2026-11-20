"""Local merge gate: judge a branch the way the CI template does, then merge it only if it passes.

For repositories without CI. The gate
  1. merges the branch into the target's tip in a scratch worktree (hooks off), producing the merge
     commit M that would land; a conflict stops here;
  2. runs M's own `check` in a fresh worktree (keeps baselines in sync, runs new guards);
  3. extracts the target's runner (blob by blob, verified against the target's tree) and runs it as
     `check --trusted` on another fresh worktree of M, so the change is judged by the policy,
     baselines, detectors and tool configuration of the target's tip;
  4. with --merge, fast-forwards the checked-out target to exactly M, if both checks exit 0, the
     target has not moved, and any change to the guard configuration was approved with
     --approve-guard-changes (the local stand-in for code-owner review).

The gate itself must be trusted, so it refuses to run unless the runner executing it is exactly the
target's committed runner (same file set, same content as git stores it).

Boundary: the branch's tests and detectors run on this machine as the current user, exactly as in
CI. The gate stops a branch from rewriting the rules that judge it; it does not sandbox code that
is malicious. Judge untrusted branches inside a container or VM.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile

from . import gitx
from . import policy as pol
from .model import GuardError

SCHEMA = 'guard-ratchet/gate@1'
GRACE_SECONDS = 5
# Files a desktop or a tool drops next to the runner. Names starting with a dot cannot be imported,
# so they cannot change what the runner executes.
JUNK = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}


def _git(root: str, *args: str, check: bool = True):
    return gitx.git(root, *args, check=check)  # gitx never runs repository hooks


def _git_or_fail(root: str, message: str, *args: str) -> str:
    proc = gitx.run(root, *args)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode('utf-8', 'replace').strip().splitlines()
        raise GuardError(f"{message}: {' / '.join(detail[-4:]) or f'git exited {proc.returncode}'}")
    return proc.stdout.decode('utf-8', 'replace')


def _commit(root: str, ref: str, branch_first: bool = True) -> tuple[str, str | None]:
    """(sha, refs/heads/<name> if ref names a local branch). Branches win over tags of the same name."""
    if branch_first and not ref.startswith('refs/'):
        sha = _git(root, 'rev-parse', '--verify', '-q', '--end-of-options', f'refs/heads/{ref}^{{commit}}', check=False)
        if sha:
            return sha.strip(), f'refs/heads/{ref}'
    sha = _git(root, 'rev-parse', '--verify', '-q', '--end-of-options', f'{ref}^{{commit}}', check=False)
    if not sha:
        raise GuardError(f'unknown branch or commit: {ref}')
    full = ref if ref.startswith('refs/heads/') else None
    return sha.strip(), full


def _target(root: str, into: str | None) -> str:
    if into:
        return into
    head = _git(root, 'symbolic-ref', '-q', 'HEAD', check=False)
    if not head:
        raise GuardError('HEAD is detached: name the branch to merge into with --into')
    return head.strip()


def _launcher_mismatch(root: str, target_sha: str, runner: str, scripts_dir: str) -> list[str]:
    """Files where the runner executing this gate differs from the target's committed runner:
    changed, missing or extra (anything Python could import from the script directory)."""
    listed = _git(root, 'ls-tree', '-r', '-z', target_sha, '--', runner) or ''
    expected = {}
    for entry in filter(None, listed.split('\0')):
        meta, path = entry.split('\t', 1)
        expected[os.path.relpath(path, runner)] = meta.split()[2]
    if not expected:
        return [f'{runner}/ is missing on the target']
    present = set()
    for folder, dirs, files in os.walk(scripts_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__' and not d.startswith('.')]
        for name in files:
            if name.endswith('.pyc') or name in JUNK or name.startswith('.'):
                continue
            present.add(os.path.relpath(os.path.join(folder, name), scripts_dir))
    differ = [f'{rel} (extra)' for rel in sorted(present - set(expected))]
    differ += [f'{rel} (missing)' for rel in sorted(set(expected) - present)]
    for rel in sorted(present & set(expected)):
        # hash-object applies the same filters as checkout (autocrlf, eol), so a CRLF checkout matches.
        blob = _git(root, 'hash-object', f'--path={runner}/{rel}', '--', os.path.join(scripts_dir, rel), check=False)
        if (blob or '').strip() != expected[rel]:
            differ.append(f'{rel} (changed)')
    return differ


def _extract(root: str, commit: str, path: str, dest: str) -> dict[str, str]:
    """Write the files of `path` at `commit` into dest, straight from the object store (git archive
    would apply export-ignore/export-subst from .gitattributes). Returns {file: blob id}."""
    blobs = {}
    listed = _git(root, 'ls-tree', '-r', '-z', commit, '--', path) or ''
    for entry in filter(None, listed.split('\0')):
        meta, rel = entry.split('\t', 1)
        mode, kind, blob = meta.split()
        if kind != 'blob' or mode == '120000':
            raise GuardError(f'unexpected entry in the target runner: {rel} ({mode} {kind})')
        target = os.path.join(dest, rel)
        if os.path.commonpath([os.path.realpath(dest), os.path.realpath(target)]) != os.path.realpath(dest):
            raise GuardError(f'runner path escapes the extraction directory: {rel}')
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'wb') as fh:
            fh.write(gitx.git(root, 'cat-file', 'blob', blob, binary=True))
        blobs[target] = blob
    return blobs


def _altered(root: str, blobs: dict[str, str]) -> list[str]:
    """Extracted runner files that no longer hold the target's bytes."""
    out = []
    for path, blob in sorted(blobs.items()):
        now = _git(root, 'hash-object', '--no-filters', '--', path, check=False) if os.path.isfile(path) else None
        if (now or '').strip() != blob:
            out.append(path)
    return out


def _tree_changed(tree: str, commit: str) -> str | None:
    """Why the worktree no longer is a clean checkout of `commit`, if it is not."""
    head = (_git(tree, 'rev-parse', 'HEAD', check=False) or '').strip()
    if head != commit:
        return f'HEAD moved to {head[:12] or "nothing"}'
    dirty = [line for line in (_git(tree, 'status', '--porcelain', '--untracked-files=no', check=False) or '').splitlines()
             if line.strip()]
    return f"tracked files changed: {', '.join(line[3:] for line in dirty[:5])}" if dirty else None


class _Worktree:
    """A detached worktree of one commit, removed afterwards; dependency folders are linked in."""

    def __init__(self, root: str, commit: str, parent: str, name: str):
        self.root, self.commit = root, commit
        self.path = os.path.join(parent, name)

    def __enter__(self) -> str:
        _git(self.root, 'worktree', 'add', '--detach', '-q', self.path, self.commit)
        for name in gitx.BaseWorktree.LINKS:
            src, dst = os.path.join(self.root, name), os.path.join(self.path, name)
            if os.path.isdir(src) and not os.path.exists(dst):
                os.symlink(src, dst)
        return self.path

    def __exit__(self, *exc) -> None:
        _git(self.root, 'worktree', 'remove', '--force', self.path, check=False)
        _git(self.root, 'worktree', 'prune', check=False)


def _stop(proc: subprocess.Popen) -> None:
    """Stop a step and everything it started: SIGTERM so the runner can clean up, then SIGKILL."""
    if os.name != 'posix':
        proc.kill()
        proc.wait()
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            continue


def _run_step(command: list[str], report_path: str) -> tuple[int, str, dict | None]:
    """Run one check. Returns (exit code, text report, JSON report). The JSON report is read from
    a file the step writes, and its own verdict is compared with the exit code."""
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    popen = {'start_new_session': True} if os.name == 'posix' else {}
    proc = subprocess.Popen(command + ['--format', 'json', '--output', report_path], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, **popen)
    try:
        out, err = proc.communicate()
    except BaseException:
        _stop(proc)
        raise
    try:
        with open(report_path, encoding='utf-8') as fh:
            report = json.load(fh)
    except (OSError, json.JSONDecodeError):
        report = None
    return proc.returncode, out + err, report


def _step_code(code: int, report: dict | None) -> tuple[int, str | None]:
    """The step's result: its exit code, unless the report it wrote says something worse or is missing."""
    if report is None or not isinstance(report.get('exit_code'), int):
        return (2 if code in (0, 3) else code), 'the step wrote no readable report'
    if report['exit_code'] != code:  # a tampered or broken runner; never a pass
        return 2, f"exit code {code} contradicts the report's {report['exit_code']}"
    return code, None


def _verdict(codes: list[int]) -> int:
    """Worst step result. Anything but 0, 1 or 3 (a crash, a signal) is an error, never a pass."""
    if any(code not in (0, 1, 3) for code in codes):
        return 2
    for code in (1, 3):
        if code in codes:
            return code
    return 0


HOOK_GLOBS = ('.githooks/**', '.husky/**', '.hooks/**', 'githooks/**', 'lefthook.yml', '.lefthook.yml',
              '.pre-commit-config.yaml')


def _guard_changes(root: str, target_policy: dict, target_sha: str, merge_sha: str) -> list[str]:
    """Changed paths that alter the guards or run on later git commands. Renames count on both sides."""
    from .runner import (
        protected_globs,  # runner imports this module's siblings; avoid a cycle
    )
    changed = (_git(root, 'diff', '--no-renames', '--name-only', '-z', target_sha, merge_sha) or '').split('\0')
    hooks_path = (_git(root, 'config', '--get', 'core.hooksPath', check=False) or '').strip()
    globs = [pol.POLICY_PATH, pol.EXCEPTIONS_PATH, *protected_globs(root, target_policy, target_sha), *HOOK_GLOBS]
    if hooks_path and not os.path.isabs(hooks_path):
        globs.append(hooks_path.rstrip('/') + '/**')
    return [path for path in changed if path and pol.any_match(path, globs)]


def _trial_merge(root: str, target_sha: str, branch_sha: str, label: str, parent: str) -> str:
    path = os.path.join(parent, 'merge')
    _git(root, 'worktree', 'add', '--detach', '-q', path, target_sha)
    try:
        proc = gitx.run(path, 'merge', '--no-ff', '--no-squash', '-m', label, branch_sha)
        if proc.returncode != 0:
            _git(path, 'merge', '--abort', check=False)
            detail = (proc.stdout + proc.stderr).decode('utf-8', 'replace').strip().splitlines()
            conflict = any('CONFLICT' in line for line in detail)
            hint = ('merge the target into the branch, resolve the conflicts there, then run the gate again'
                    if conflict else 'git refused the merge')
            raise GuardError(f"the trial merge failed ({hint}): {' / '.join(detail[-4:])}")
        merge_sha = _git(path, 'rev-parse', 'HEAD').strip()
    finally:
        _git(root, 'worktree', 'remove', '--force', path, check=False)
        _git(root, 'worktree', 'prune', check=False)
    parents = _git(root, 'rev-parse', f'{merge_sha}^1', f'{merge_sha}^2', check=False)
    if (parents or '').split() != [target_sha, branch_sha]:
        raise GuardError('the trial merge did not produce a merge of exactly the target and the branch')
    return merge_sha


def _raise_on_signal(signum, _frame):
    raise KeyboardInterrupt(f'signal {signum}')


def gate(root: str, branch: str, into: str | None, merge: bool, fmt: str, scripts_dir: str,
         approve: bool = False) -> int:
    signals = [getattr(signal, name) for name in ('SIGTERM', 'SIGHUP') if hasattr(signal, name)]
    previous = {s: signal.signal(s, _raise_on_signal) for s in signals}
    try:
        return _gate(root, branch, into, merge, fmt, scripts_dir, approve)
    except (GuardError, KeyboardInterrupt) as err:
        code = 130 if isinstance(err, KeyboardInterrupt) else 2
        if fmt == 'json':
            print(json.dumps({'schema': SCHEMA, 'branch': branch, 'exit_code': code,
                              'error': str(err) if code == 2 else 'interrupted'}, indent=2))
            return code
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _gate(root: str, branch: str, into: str | None, merge: bool, fmt: str, scripts_dir: str, approve: bool) -> int:
    if not gitx.is_repo(root):
        raise GuardError(f'{root} is not a git repository')
    target = _target(root, into)
    target_sha, target_ref = _commit(root, target)
    branch_sha, _ = _commit(root, branch)
    name = target_ref.removeprefix('refs/heads/') if target_ref else target
    policy_text = gitx.show_text(root, target_sha, pol.POLICY_PATH)
    if policy_text is None:
        raise GuardError(f'{name} has no {pol.POLICY_PATH}: a change that introduces the guards needs a human review')
    _, target_policy = pol.load(root, policy_text)
    runner = target_policy['runner'].rstrip('/')
    differ = _launcher_mismatch(root, target_sha, runner, scripts_dir)
    if differ:
        raise GuardError(f"this runner is not {name}'s committed runner ({', '.join(differ[:3])} differ); "
                         f'run `python3 {runner}/guard.py gate` from a clean checkout of {name}')
    if _git(root, 'merge-base', '--is-ancestor', branch_sha, target_sha, check=False) is not None:
        if fmt == 'json':
            print(json.dumps({'schema': SCHEMA, 'branch': branch, 'commit': branch_sha, 'target': name,
                              'target_commit': target_sha, 'exit_code': 0, 'merged': None,
                              'note': 'already contained in the target', 'steps': []}, indent=2))
        else:
            print(f'{branch} is already contained in {name}: nothing to judge')
        return 0
    if merge:
        _check_mergeable(root, target_ref, name, target_sha)

    if _git(root, 'var', 'GIT_COMMITTER_IDENT', check=False) is None:
        raise GuardError('git has no committer identity for the trial merge: set user.name and user.email')
    with tempfile.TemporaryDirectory(prefix='guard-gate-') as tmp:
        merge_sha = _trial_merge(root, target_sha, branch_sha, f'Merge {branch} into {name}', tmp)
        guard_changes = _guard_changes(root, target_policy, target_sha, merge_sha)
        steps, codes, texts, reports, issues = [], [], [], [], []

        def record(label, result, problem=None):
            code, text, report = result
            code, why = _step_code(code, report)
            for extra in (why, problem):
                if extra:
                    code = 2 if code in (0, 3) else code
                    text += f'\n✗ {extra}\n'
                    issues.append(f'{label}: {extra}')
            steps.append(label)
            codes.append(code)
            texts.append(text)
            reports.append(report)

        with _Worktree(root, merge_sha, tmp, 'own') as tree:
            own = os.path.join(tree, runner, 'guard.py')
            if os.path.isfile(own):
                result = _run_step([sys.executable, own, 'check', '--root', tree, '--base', target_sha],
                                   os.path.join(tmp, 'own.json'))
                record('branch rules', result, _tree_changed(tree, merge_sha))
            else:
                record('branch rules', (1, f'the branch deleted the runner ({runner}/guard.py)\n',
                                        {'exit_code': 1, 'error': 'the branch deleted the runner'}))
        # Extracted only now, after the first step finished, into a directory created now, run on
        # a fresh tree of the same commit, and verified afterwards.
        judge_dir = tempfile.mkdtemp(prefix='runner-', dir=tmp)
        blobs = _extract(root, target_sha, runner, judge_dir)
        with _Worktree(root, merge_sha, tmp, 'trusted') as tree:
            result = _run_step([sys.executable, os.path.join(judge_dir, runner, 'guard.py'), 'check', '--trusted',
                                '--root', tree, '--base', target_sha], os.path.join(tmp, 'trusted.json'))
            altered = _altered(root, blobs)
            problem = _tree_changed(tree, merge_sha) or (
                f"the target runner was modified while it ran: {', '.join(os.path.relpath(p, judge_dir) for p in altered[:3])}"
                if altered else None)
            record(f'{name} rules (trusted)', result, problem)

    verdict = _verdict(codes)
    merged, note = None, None
    if verdict == 0 and guard_changes and not approve:
        # Without approval the change is not accepted, whether or not this run was asked to merge,
        # so `gate X && git merge X` cannot skip the review either.
        verdict = 1
        note = (f'needs approval: the change edits guard configuration or hooks ({", ".join(guard_changes[:5])}). '
                f'Review `git diff {target_sha[:12]} {merge_sha[:12]} -- {" ".join(guard_changes[:5])}`, then '
                f're-run with --approve-guard-changes')
    elif merge and verdict == 0:
        _check_mergeable(root, target_ref, name, target_sha)  # nothing moved while the checks ran
        option = f'branch.{name}.mergeOptions='  # a configured --squash or --no-ff would not land M itself
        _git_or_fail(root, f'could not fast-forward {name} to the judged merge {merge_sha[:12]}',
                     '-c', option, 'merge', '--ff-only', '--no-squash', merge_sha)
        if _git(root, 'rev-parse', 'HEAD').strip() != merge_sha:
            raise GuardError(f'{name} is not at the judged merge {merge_sha[:12]} after merging; inspect it by hand')
        merged = merge_sha
    _print(fmt, branch, branch_sha, name, target_sha, merge_sha, verdict, merged, note, guard_changes, issues,
           list(zip(steps, codes, texts, reports, strict=True)), merge)
    return verdict


def _check_mergeable(root: str, target_ref: str | None, name: str, target_sha: str) -> None:
    current = (_git(root, 'symbolic-ref', '-q', 'HEAD', check=False) or '').strip()
    if not target_ref or current != target_ref:
        raise GuardError(f'--merge merges into the checked-out branch: check out {name} first')
    if _git(root, 'rev-parse', 'HEAD').strip() != target_sha:
        raise GuardError(f'{name} moved while the gate ran; run it again')
    if _git(root, 'status', '--porcelain', '--untracked-files=no').strip():
        raise GuardError('--merge needs a clean working tree (commit or stash your changes first)')


def _print(fmt, branch, branch_sha, name, target_sha, merge_sha, verdict, merged, note, guard_changes, issues,
           steps, merge):
    if fmt == 'json':
        print(json.dumps({'schema': SCHEMA, 'branch': branch, 'commit': branch_sha, 'target': name,
                          'target_commit': target_sha, 'merge_commit': merge_sha, 'exit_code': verdict,
                          'merged': merged, 'guard_changes': guard_changes, 'note': note, 'issues': issues,
                          'steps': [{'name': label, 'exit_code': code, 'report': report}
                                    for label, code, _text, report in steps]}, indent=2))
        return
    for label, code, text, _report in steps:
        sys.stdout.write(f'── {label} (exit {code}) ──\n{text}')
    if guard_changes:
        print(f'guard configuration changed: {", ".join(guard_changes)}')
    if note:
        print(note)
    word = {0: 'PASS', 1: 'FAIL', 2: 'ERROR', 3: 'INCOMPLETE'}[verdict]
    tail = f'; merged as {merged[:12]}' if merged else ('; not merged' if merge else '')
    print(f'gate {word}: {branch} ({branch_sha[:12]}) into {name}{tail}')
