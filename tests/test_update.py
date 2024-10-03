import hashlib
import os
import shutil
import tempfile
import unittest

import git
import tomli

from guw.main import GUW


def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


class AddTestCase(unittest.TestCase):
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
            "Second commit",
            "Initial commit",
        ]
        guw = GUW(tomli.loads(config))
        guw.update(
            False,
            True,
            True,
            self.tmpdir,
            "origin/example1-feature2-update",
            "example1-feature2",
        )
        repo = git.Repo(self.tmpdir)
        # Check the proper order of the commits, like git log --pretty=%s
        commits = [x.summary for x in repo.iter_commits("example1-final")]
        self.assertEqual(commits, expected_commits)
        self.assertEqual(
            "9908e0cde59a83a448564e9096b6397f",
            md5(os.path.join(self.tmpdir, "file1.txt")),
        )
