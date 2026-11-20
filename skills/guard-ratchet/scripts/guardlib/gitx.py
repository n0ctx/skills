"""git access: resolve the base, read files at the base, compute the change set.

Change set = merge-base(base, HEAD) versus the working tree (staged, unstaged and untracked
files that are not ignored). In CI the working tree equals HEAD; locally it includes
uncommitted work, so local runs and CI judge the same content.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from .model import GuardError

HUNK_RE = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


def git(root: str, *args: str, check: bool = True, binary: bool = False):
    # Pin the settings that change diff output format, so a user's git config cannot blind the parser.
    proc = subprocess.run(['git', '-c', 'core.quotePath=false', '-c', 'diff.noprefix=false',
                           '-c', 'diff.mnemonicPrefix=false', '-c', 'diff.relative=false', '-C', root, *args],
                          capture_output=True)
    if check and proc.returncode != 0:
        raise GuardError(f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace').strip()}")
    if binary:
        return proc.stdout if proc.returncode == 0 else None
    return proc.stdout.decode('utf-8', errors='replace') if proc.returncode == 0 else None


def is_repo(root: str) -> bool:
    return shutil.which('git') is not None and git(root, 'rev-parse', '--git-dir', check=False) is not None


def toplevel(path: str) -> str | None:
    if not is_repo(path):
        return None
    out = git(path, 'rev-parse', '--show-toplevel', check=False)
    return out.strip() if out else None


def resolve_base(root: str, ref: str | None) -> str | None:
    """Return the merge-base of `ref` and HEAD. ref 'none' means an empty base (returns None).

    An explicit ref that cannot be resolved is an error: silently falling back to "no base"
    would switch off every lock check.
    """
    if ref == 'none':
        return None
    if not is_repo(root):
        if ref:
            raise GuardError(f'{root} is not a git repository, cannot use base {ref}; without git pass --base none')
        return None
    if git(root, 'rev-parse', '--verify', '-q', 'HEAD', check=False) is None:
        return None  # no commits yet: everything is new
    candidates = [ref] if ref else []
    if not ref:
        head = git(root, 'symbolic-ref', '-q', 'refs/remotes/origin/HEAD', check=False)
        candidates += [head.strip()] if head else []
        candidates += ['origin/main', 'origin/master', 'main', 'master']
    for cand in candidates:
        sha = git(root, 'rev-parse', '--verify', '-q', f'{cand}^{{commit}}', check=False)
        if sha:
            mb = git(root, 'merge-base', sha.strip(), 'HEAD', check=False)
            if not mb:
                raise GuardError(f'base {cand} has no common ancestor with HEAD')
            return mb.strip()
    if ref:
        raise GuardError(f'cannot resolve base {ref} (in CI, fetch the target branch, e.g. fetch-depth: 0)')
    raise GuardError('no default base found (origin/HEAD, main and master are all missing); pass --base <ref>, or --base none')


def show(root: str, commit: str | None, path: str) -> bytes | None:
    if not commit:
        return None
    return git(root, 'show', f'{commit}:{path}', check=False, binary=True)


def show_text(root: str, commit: str | None, path: str) -> str | None:
    data = show(root, commit, path)
    return data.decode('utf-8', errors='replace') if data is not None else None


def tracked_files(root: str) -> list[str]:
    """Tracked or untracked-but-not-ignored files present in the working tree, sorted, repo-relative."""
    if not is_repo(root):
        out = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith('.') and d != 'node_modules')
            for name in filenames:
                out.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, '/'))
        return sorted(out)
    listed = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    files = {p for p in listed.split('\0') if p}
    return sorted(p for p in files if os.path.isfile(os.path.join(root, p)))


def base_files(root: str, commit: str | None) -> list[str]:
    if not commit:
        return []
    out = git(root, 'ls-tree', '-r', '-z', '--name-only', commit)
    return sorted(p for p in out.split('\0') if p)


@dataclass
class FileChange:
    path: str
    status: str                     # A added / M modified / D deleted / R renamed
    old_path: str | None = None
    added: list[tuple[int, str]] = field(default_factory=list)    # (line number in new file, text)
    removed: list[tuple[int, str]] = field(default_factory=list)  # (line number in old file, text)
    binary: bool = False


@dataclass
class ChangeSet:
    base: str | None
    files: dict[str, FileChange] = field(default_factory=dict)

    @property
    def renames(self) -> dict[str, str]:
        return {c.old_path: p for p, c in self.files.items() if c.status == 'R' and c.old_path}

    def paths(self, *statuses: str) -> list[str]:
        return sorted(p for p, c in self.files.items() if not statuses or c.status in statuses)

    def added_lines(self, path: str) -> set[int]:
        change = self.files.get(path)
        return {n for n, _ in change.added} if change else set()

    @property
    def changed_lines(self) -> int:
        return sum(len(c.added) + len(c.removed) for c in self.files.values())


def _read_lines(root: str, rel: str) -> list[str] | None:
    try:
        with open(os.path.join(root, rel), 'rb') as fh:
            data = fh.read()
    except OSError:
        return None
    if b'\0' in data[:8000]:
        return None
    return data.decode('utf-8', errors='replace').splitlines()


def changeset(root: str, base: str | None) -> ChangeSet:
    """The full change set of the working tree against base. With no base every file is added."""
    cs = ChangeSet(base=base)
    current = tracked_files(root)
    if base is None:
        for rel in current:
            lines = _read_lines(root, rel)
            cs.files[rel] = FileChange(rel, 'A', binary=lines is None,
                                       added=list(enumerate(lines or [], start=1)))
        return cs
    status = git(root, 'diff', '--no-color', '--no-ext-diff', '-M', '--name-status', '-z', base, '--')
    parts = [p for p in status.split('\0') if p != '']
    i = 0
    while i < len(parts):
        code = parts[i]
        if code.startswith(('R', 'C')):
            old, new = parts[i + 1], parts[i + 2]
            kind = 'R' if code.startswith('R') else 'A'
            cs.files[new] = FileChange(new, kind, old_path=old if kind == 'R' else None)
            i += 3
        else:
            path = parts[i + 1]
            kind = {'A': 'A', 'D': 'D', 'T': 'M'}.get(code[0], 'M')
            cs.files[path] = FileChange(path, kind)
            i += 2
    diff = git(root, 'diff', '--no-color', '--no-ext-diff', '--src-prefix=a/', '--dst-prefix=b/', '-M', '-U0', base, '--')
    _parse_diff_files(diff, cs.files)
    untracked = git(root, 'ls-files', '-z', '--others', '--exclude-standard')
    for rel in sorted(p for p in untracked.split('\0') if p):
        if rel in cs.files or not os.path.isfile(os.path.join(root, rel)):
            continue
        lines = _read_lines(root, rel)
        cs.files[rel] = FileChange(rel, 'A', binary=lines is None, added=list(enumerate(lines or [], start=1)))
    _pair_untracked_renames(root, cs)
    return cs


def _parse_diff_files(diff: str, files: dict[str, FileChange]) -> None:
    """Split on `diff --git`, find which file each section belongs to, collect added/removed lines."""
    for chunk in re.split(r'(?m)^(?=diff --git )', diff):
        if not chunk.startswith('diff --git '):
            continue
        old = new = None
        for line in chunk.split('\n'):
            if line.startswith('--- '):
                old = _header_path(line[4:], 'a/')
            elif line.startswith('+++ '):
                new = _header_path(line[4:], 'b/')
                break
        change = files.get(new) if new else files.get(old) if old else None
        if change is None:
            continue
        if 'Binary files ' in chunk and '@@' not in chunk:
            change.binary = True
            continue
        body = chunk.split('\n@@', 1)
        if len(body) < 2:
            continue
        _collect_hunks('@@' + body[1], change)


_C_ESCAPES = {'a': 7, 'b': 8, 't': 9, 'n': 10, 'v': 11, 'f': 12, 'r': 13, '"': 34, '\\': 92}


def _header_path(raw: str, prefix: str) -> str | None:
    """Path from a `---`/`+++` header. Git appends a TAB when the path contains a space, and
    C-quotes paths with quotes, backslashes or control characters."""
    raw = raw.rstrip('\r')
    if raw.endswith('\t'):
        raw = raw[:-1]
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        out, i, body = bytearray(), 0, raw[1:-1]
        while i < len(body):
            ch = body[i]
            if ch == '\\' and i + 1 < len(body):
                nxt = body[i + 1]
                if nxt in '01234567' and re.match(r'[0-7]{3}', body[i + 1:i + 4]):
                    out.append(int(body[i + 1:i + 4], 8))
                    i += 4
                    continue
                out.append(_C_ESCAPES.get(nxt, ord(nxt)))
                i += 2
                continue
            out += ch.encode('utf-8')
            i += 1
        raw = out.decode('utf-8', errors='replace')
    return raw[len(prefix):] if raw.startswith(prefix) else None


def _collect_hunks(text: str, change: FileChange) -> None:
    old_no = new_no = 0
    for line in text.split('\n'):
        match = HUNK_RE.match(line)
        if match:
            old_no, new_no = int(match.group(1)), int(match.group(3))
        elif line.startswith('+'):
            change.added.append((new_no, line[1:].rstrip('\r')))
            new_no += 1
        elif line.startswith('-'):
            change.removed.append((old_no, line[1:].rstrip('\r')))
            old_no += 1
        elif not line.startswith('\\'):
            old_no += 1
            new_no += 1


def _pair_untracked_renames(root: str, cs: ChangeSet) -> None:
    """An untracked file identical to a deleted file is a rename (git only detects renames it can see in the index)."""
    deleted = {}
    for path in cs.paths('D'):
        data = show(root, cs.base, path)
        if data is not None:
            deleted.setdefault(hashlib.sha256(data).hexdigest(), []).append(path)
    if not deleted:
        return
    for path in cs.paths('A'):
        try:
            with open(os.path.join(root, path), 'rb') as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            continue
        olds = deleted.get(digest)
        if olds:
            old = olds.pop(0)
            del cs.files[old]
            cs.files[path] = FileChange(path, 'R', old_path=old)


class BaseWorktree:
    """Check out the base commit into a temporary directory to scan base code with current rules.

    Dependency directories (node_modules, .venv) are not versioned; they are symlinked in by
    name so tools still find their dependencies. `overlay` globs (the guard's tool config files)
    are copied from the working tree, so tools that read config from the scanned tree apply the
    current rules to the base code.
    """

    LINKS = ('node_modules', '.venv', 'venv')

    def __init__(self, root: str, commit: str, overlay: list[str] | None = None):
        self.root = root
        self.commit = commit
        self.overlay = overlay or []
        self.path = None

    def __enter__(self) -> str:
        parent = tempfile.mkdtemp(prefix='guard-base-')
        self.path = os.path.join(parent, 'tree')
        git(self.root, 'worktree', 'add', '--detach', '-q', self.path, self.commit)
        for name in self.LINKS:
            src = os.path.join(self.root, name)
            dst = os.path.join(self.path, name)
            if os.path.isdir(src) and not os.path.exists(dst):
                os.symlink(src, dst)
        if self.overlay:  # current tool configuration: "base code judged by the current rules"
            from .policy import any_match
            current = {rel for rel in tracked_files(self.root) if any_match(rel, self.overlay)}
            for rel in base_files(self.root, self.commit):
                if any_match(rel, self.overlay) and rel not in current \
                        and os.path.isfile(os.path.join(self.path, rel)):  # config the change deleted
                    os.remove(os.path.join(self.path, rel))
            for rel in sorted(current):
                dst = os.path.join(self.path, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(os.path.join(self.root, rel), dst)
        return self.path

    def __exit__(self, *exc) -> None:
        git(self.root, 'worktree', 'remove', '--force', self.path, check=False)
        shutil.rmtree(os.path.dirname(self.path), ignore_errors=True)
        git(self.root, 'worktree', 'prune', check=False)
