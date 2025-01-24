import shutil
import tempfile
import unittest

import git
import tomli

from guw.main import GUW


class IntegrateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Setup git to have a proper user and email
        gitconfig = git.config.get_config_path("global")
        gc = git.GitConfigParser(gitconfig, read_only=False)

        try:
            name = gc.get_value("user", "name")
        except:
            name = None
        if not name:
            gc.set_value("user", "name", "test")
        try:
            email = gc.get_value("user", "email")
        except:
            email = None
        if not email:
            gc.set_value("user", "email", "test@guw.com")
        gc.release()

    def cleanUp(self):
        shutil.rmtree(self.tmpdir)

    def test_add(self):
        config = """
            [[remotes]]
            name = "origin"
            url = "https://github.com/fluendo/git-upstream-workflow.git"

            [target]
            remote = "origin"
            branch = "example1-final"

            [upstream]
            remote = "origin"
            branch = "example1-upstream"

            [source]
            remote = "origin"
            branch = "example1-main"

            [[features]]
            remote = "origin"
            name = "example1-feature1"
            pr = "https://github/fluendo/git-upstream-workflow/pull-requests/10"
            status = "merging"

            [[features]]
            remote = "origin"
            name = "example1-feature2"
            pr = "https://github/fluendo/git-upstream-workflow/pull-requests/10"
            status = "pending"
        """
        expected_commits_example1_final = [
            "Modify file1.txt",
            "Add file2.txt",
            "Commit after upstream review",
            "Second commit",
            "Initial commit",
        ]
        expected_commits_example1_main = [
            "Commit after upstream review",
            "Second commit",
            "Initial commit",
        ]
        guw = GUW(tomli.loads(config))
        guw.integrate(
            False,
            True,
            True,
            self.tmpdir,
            "example1-feature1",
        )
        repo = git.Repo(self.tmpdir)
        # Target must have upstream plus feature2
        commits = [x.summary for x in repo.iter_commits("example1-final")]
        self.assertEqual(commits, expected_commits_example1_final)
        # Source must have upstream
        commits = [x.summary for x in repo.iter_commits("example1-main")]
        self.assertEqual(commits, expected_commits_example1_main)
