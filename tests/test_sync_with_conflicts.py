import shutil
import tempfile
import unittest
from pathlib import Path

import git
import tomli

from guw.main import GUW

class TestSyncWithConflicts(unittest.TestCase):
    file_name = "file.txt"
    fc_init = """
        init
    """
    fc_a1 = """
        init
        A fo
    """
    fc_b = """
        B bar
        init
        A fo
    """
    fc_a2 = """
        init
        A foo
    """
    fc_expected = """
        B bar
        init
        A foo
    """

    @classmethod
    def _commit_file(cls, repo, file_path, file_contents, commit_message, *args):
        with open(file_path, "w") as f:
            f.write(file_contents)
        repo.index.add(file_path)
        repo.git.commit("--message", commit_message, *args)

    @classmethod
    def _prepare_repo(cls, repo_dir):
        repo = git.Repo.init(repo_dir)
        fp = repo_dir / cls.file_name

        cls._commit_file(repo, fp, cls.fc_init, "init")
        repo.git.branch("final")

        repo.git.checkout("HEAD", b = "A")
        cls._commit_file(repo, fp, cls.fc_a1, "foo")

        repo.git.checkout("HEAD", b = "B")
        cls._commit_file(repo, fp, cls.fc_b, "bar")
        
        # Reviewer asked for changes: fix and ammend this branch
        repo.git.checkout("A")
        cls._commit_file(repo, fp, cls.fc_a2, "foo", "--amend")

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.guw_dir = self.tmpdir / "guw"
        self.repo_dir = self.tmpdir / "remote"

        self._prepare_repo(self.repo_dir)
        config = f"""
            [[remotes]]
            name = "origin"
            url = "file://{self.repo_dir}"

            [target]
            remote = "origin"
            branch = "final"

            [source]
            remote = "origin"
            branch = "main"

            [[features]]
            remote = "origin"
            name = "A"
            status = "merging"

            [[features]]
            remote = "origin"
            name = "B"
            status = "pending"
        """

        self.guw = GUW(tomli.loads(config))

    def cleanUp(self):
        shutil.rmtree(self.tmpdir)

    def check_file_contents(self, repo_path):
        with open(repo_path / self.file_name) as f:
            file_contents = f.read()
        self.assertEqual(self.fc_expected, file_contents)

    def test_sync_with_conflict(self):
        self.guw.sync(
            backup = False,
            keep   = True,
            local  = True,
            folder = self.guw_dir,
        )
        repo = git.Repo(self.guw_dir)
        self.check_file_contents(self.guw_dir)

    def test_manual_rebase(self):
        repo = git.Repo(self.repo_dir)
        repo.git.rebase("B~", "B", "--onto", "A")
        self.check_file_contents(self.repo_dir)
