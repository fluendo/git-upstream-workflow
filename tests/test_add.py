import shutil
import unittest
import tempfile
import tomli
import git

from guw.main import GUW

class AddTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def cleanUp(self):
        shutil.rmtree(self.tmpdir)

    def test_add(self):
        config = """
            [[remotes]]
            name = "origin"
            url = "git@github.com:turran/git-upstream-workflow.git"
            
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
        expected_commits = [
            "Modify file1.txt",
            "Add file2.txt",
            "Adding extra file",
            "Second commit",
            "Initial commit"
        ]
        guw = GUW(tomli.loads(config))
        guw.add(False, True, True, self.tmpdir, "example1-feature-to-add", "origin", "example1-feature1")
        # Check the proper order of the commits, like git log --pretty=%s
        repo = git.Repo(self.tmpdir)
        commits = [x.summary for x in repo.iter_commits("example1-final")]
        self.assertEqual(commits, expected_commits)