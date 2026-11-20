"""Change-set extraction must not depend on the user's git configuration or on unusual file names."""

from __future__ import annotations

import unittest

from helpers import RepoCase, git

from guardlib import gitx


class ChangeSetTest(RepoCase):
    def added(self, repo, path):
        cs = gitx.changeset(repo.root, git(repo.root, 'rev-parse', 'main').strip())
        return [text for _, text in cs.files[path].added]

    def test_diff_prefix_settings_do_not_hide_added_lines(self):
        for setting in ('diff.noprefix', 'diff.mnemonicPrefix'):
            with self.subTest(setting):
                repo = self.repo({'src/a.py': 'a = 1\n'})
                git(repo.root, 'config', setting, 'true')
                repo.branch()
                repo.write({'src/a.py': 'a = 1\nb = 2\n'})
                repo.commit()
                self.assertEqual(self.added(repo, 'src/a.py'), ['b = 2'])

    def test_paths_with_spaces_quotes_and_backslashes_keep_their_lines(self):
        for path in ('src/my secrets.py', 'src/say "hi".py', 'src/back\\slash.py', 'src/naïve file.py'):
            with self.subTest(path):
                repo = self.repo({path: 'a = 1\n'})
                repo.branch()
                repo.write({path: 'a = 1\nkey = 2\n'})
                repo.commit()
                self.assertEqual(self.added(repo, path), ['key = 2'])

    def test_crlf_lines_are_reported_without_the_carriage_return(self):
        repo = self.repo({'a.txt': 'x\r\n'})
        repo.branch()
        repo.write({'a.txt': 'x\r\ny\r\n'})
        repo.commit()
        self.assertEqual(self.added(repo, 'a.txt'), ['y'])


if __name__ == '__main__':
    unittest.main()
