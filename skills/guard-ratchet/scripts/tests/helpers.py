"""Shared test helpers: temporary git repositories and runner invocations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(SCRIPTS, 'guard.py')
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True


def git(root: str, *args: str) -> str:
    env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 't',
           'GIT_COMMITTER_EMAIL': 't@example.com', 'GIT_CONFIG_NOSYSTEM': '1', 'HOME': root}
    proc = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f'git {args}: {proc.stderr}')
    return proc.stdout


class Repo:
    """A throwaway git repository with a main branch."""

    def __init__(self, files: dict[str, str] | None = None, commit: bool = True):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix='guard-test-'))
        git(self.root, 'init', '-q', '-b', 'main')
        git(self.root, 'config', 'commit.gpgsign', 'false')
        if files:
            self.write(files)
        if commit:
            self.commit('init')

    def write(self, files: dict[str, str | None]) -> None:
        for rel, text in files.items():
            path = os.path.join(self.root, rel)
            if text is None:
                if os.path.exists(path):
                    os.remove(path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(textwrap.dedent(text) if text.startswith('\n') else text)

    def read(self, rel: str) -> str:
        with open(os.path.join(self.root, rel), encoding='utf-8') as fh:
            return fh.read()

    def policy(self, guards: list[dict], **extra) -> None:
        self.write({'guards/policy.json': json.dumps({'version': 2, 'guards': guards, **extra}, indent=2)})

    def commit(self, message: str = 'change') -> None:
        git(self.root, 'add', '-A')
        git(self.root, 'commit', '-q', '--allow-empty', '-m', message)

    def branch(self, name: str = 'feature') -> None:
        git(self.root, 'checkout', '-q', '-b', name)

    def guard(self, *args: str) -> tuple[int, dict | str, str]:
        """Run guard.py; for check/update returns the parsed JSON report."""
        cmd = [sys.executable, GUARD, *args] + ([] if args and args[0] in ('pyapi', 'conformance') else ['--root', self.root])
        json_mode = args and args[0] in ('check', 'update') and '--format' not in args
        if json_mode:
            cmd += ['--format', 'json']
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=self.root)
        out = proc.stdout
        if json_mode and proc.returncode != 2:
            out = json.loads(proc.stdout)
        return proc.returncode, out, proc.stderr

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class RepoCase(unittest.TestCase):
    def repo(self, files=None, commit=True) -> Repo:
        repo = Repo(files, commit)
        self.addCleanup(repo.cleanup)
        return repo


def problems(report: dict, guard: str | None = None, category: str | None = None, blocking: bool | None = None):
    items = list(report['problems'])
    for g in report['guards']:
        items += g['problems']
    return [p for p in items if (guard is None or p['guard'] == guard) and (category is None or p['category'] == category)
            and (blocking is None or p.get('blocking', False) == blocking)]


def status(report: dict, guard: str) -> str:
    return next(g['status'] for g in report['guards'] if g['name'] == guard)


def detector(doc: dict) -> str:
    """A run command that prints a fixed detector@2 document (written into the repo as JSON)."""
    return json.dumps({'schema': 'guard-ratchet/detector@2', **doc})
