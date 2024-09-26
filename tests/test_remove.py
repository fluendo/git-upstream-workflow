import shutil
import tempfile
import unittest

import git
import tomli

from guw.main import GUW


class RemoveTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def cleanUp(self):
        shutil.rmtree(self.tmpdir)

    def test_remove(self):
        config = """
            [[remotes]]
            name = "origin"
            url = "https://github.com/fluendo/git-upstream-workflow.git"

            [target]
            remote = "origin"
            branch = "example1-final"

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
        expected_commits = ["Second commit", "Initial commit"]
        guw = GUW(tomli.loads(config))
        guw.remove(False, True, True, self.tmpdir, "example1-feature2")
        # Check the proper order of the commits, like git log --pretty=%s
        repo = git.Repo(self.tmpdir)
        commits = [x.summary for x in repo.iter_commits("example1-final")]
        self.assertEqual(commits, expected_commits)
