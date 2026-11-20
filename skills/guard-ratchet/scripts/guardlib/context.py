"""What a guard can see while it runs: the scanned tree, the policy, the change set, a temp dir."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field

from . import gitx
from . import policy as pol


@dataclass
class Context:
    root: str                       # tree being scanned (project root, or a base worktree)
    project: str                    # project root: commands run here, tools are installed here
    policy: dict
    changes: gitx.ChangeSet | None  # None while scanning a base worktree to rebuild a baseline
    tmp: str
    # Trusted mode restores guard configuration from base on disk, so tools apply the base rules.
    # Built-in guards must still judge the change itself: they read the change's version from here.
    originals: dict[str, bytes | None] = field(default_factory=dict, repr=False)
    # Reports read through `input` must be written after this moment, so a stale or committed report
    # cannot stand in for a run.
    started: float = field(default_factory=time.time, repr=False)
    _files: list[str] | None = field(default=None, repr=False)
    _kinds: dict = field(default_factory=dict, repr=False)

    @property
    def files(self) -> list[str]:
        if self._files is None:
            self._files = [f for f in gitx.tracked_files(self.root) if not pol.excluded(self.policy, f)]
        return self._files

    def read(self, rel: str, limit: int | None = None) -> str | None:
        if rel in self.originals and self.root == self.project:
            data = self.originals[rel]
            if data is None:
                return None
            data = data[:limit] if limit else data
        else:
            try:
                with open(os.path.join(self.root, rel), 'rb') as fh:
                    data = fh.read(limit) if limit else fh.read()
            except OSError:
                return None
        if b'\0' in data[:8000]:
            return None
        return data.decode('utf-8', errors='replace')

    def base_text(self, rel: str) -> str | None:
        return gitx.show_text(self.project, self.changes.base, rel) if self.changes else None

    def kind(self, rel: str) -> str:
        if rel not in self._kinds:
            head = self.read(rel, 1024) if pol.kind_by_path(self.policy, rel) == 'logic' else None
            self._kinds[rel] = pol.classify(self.policy, rel, head)
        return self._kinds[rel]

    def base_kind(self, rel: str) -> str:
        kind = pol.kind_by_path(self.policy, rel)
        if kind == 'logic':
            text = self.base_text(rel)
            return pol.classify(self.policy, rel, text[:1024] if text else None)
        return kind

    def code_files(self) -> list[str]:
        return [f for f in self.files if pol.is_code(f, self.policy) and self.kind(f) not in pol.EXEMPT_KINDS]

    def expand(self, command: str, out: str | None = None) -> str:
        """Substitute {root}, {out}, {tmp} and {base} in a guard command."""
        base = self.changes.base if self.changes else None
        return (command.replace('{root}', shlex.quote(self.root))
                .replace('{out}', shlex.quote(out or os.path.join(self.tmp, 'out')))
                .replace('{tmp}', shlex.quote(self.tmp)).replace('{base}', base or ''))

    def run(self, command: str, timeout: int) -> tuple[int, str, str]:
        try:
            proc = subprocess.run(command, shell=True, cwd=self.project, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return 124, '', f'timed out after {timeout}s'
        return proc.returncode, proc.stdout.decode('utf-8', 'replace'), proc.stderr.decode('utf-8', 'replace')


MTIME_SLACK = 1.0  # seconds; file systems store modification times with limited precision
# Freshness stops stale and committed reports; it cannot stop a local process that touches a file
# just before the run. The trusted CI run, on a fresh checkout, is what makes it binding.


def stale_inputs(paths: list[str], since: float) -> list[str]:
    """Report files that were not written after `since`."""
    return [p for p in paths if os.path.getmtime(p) < since - MTIME_SLACK]
