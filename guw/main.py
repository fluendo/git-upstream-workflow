import argparse
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime
from functools import cache

import colorlog
import git
import tomli
import tomli_w

logger = logging.getLogger(__name__)
stream_handle = colorlog.StreamHandler()
formatter = colorlog.ColoredFormatter(
    "[%(asctime)s] %(log_color)s%(levelname)s%(reset)s %(filename)s:%(lineno)s %(message)s"
)

stream_handle.setFormatter(formatter)
logger.addHandler(stream_handle)

VALID_STATUS = ["integrated", "merging", "pending"]


@cache
def branch_refs(repo_url):
    g = git.Git()

    return g.ls_remote("--heads", repo_url)


def branch_exists_remote(repo_url, branch_name):
    refs = branch_refs(repo_url)

    for ref in refs.splitlines():
        if ref.endswith(f"refs/heads/{branch_name}"):
            return True
    return False


class GUW:
    def __init__(self, config):
        self.config = config
        self.to_push = []

    def _backup_name(self, name):
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_name = f"{name}-{now}"
        return backup_name

    def _get_upstream_feature(self):
        if "upstream" not in self.config:
            return self._get_source_feature()

        return {
            "remote": self.config["upstream"]["remote"],
            "name": self.config["upstream"]["branch"],
        }

    def _get_source_feature(self):
        return {
            "remote": self.config["source"]["remote"],
            "name": self.config["source"]["branch"],
        }

    def _get_target_feature(self):
        return {
            "remote": self.config["target"]["remote"],
            "name": self.config["target"]["branch"],
        }

    def _upstream_is_source(self):
        if "upstream" not in self.config:
            return True
        else:
            return False

    def _get_feature_by_name(self, feature_name):
        feature = None
        idx = 0
        for f in self.config["features"]:
            if f["name"] == feature_name:
                feature = f
                break
            idx = idx + 1
        return feature, idx

    def _backup_feature(self, repo, feature, backup=False):
        if not backup:
            return
        feature_backup_name = self._backup_name(feature["name"])
        logger.debug(f"Backing up {feature['name']} into {feature_backup_name}")
        repo.git.branch("-c", feature_backup_name)
        self.to_push.append((feature_backup_name, feature["remote"]))

    def _rebase(self, repo, from_ft, until_ft, to_ft, backup=False):
        until_ft_branch = f"{until_ft['remote']}/{until_ft['name']}"
        logger.debug(f"Rebasing {from_ft['name']} onto {to_ft['name']} until {until_ft_branch}")
        self._backup_feature(repo, from_ft)
        # Ok, let's rebase on top of the to_ft
        os.environ["GIT_SEQUENCE_EDITOR"] = ":"
        repo.git.rebase(
            "-i",
            "--autosquash",
            "--onto",
            to_ft["name"],
            until_ft_branch,
            from_ft["name"],
        )
        del os.environ["GIT_SEQUENCE_EDITOR"]
        self.to_push.append((from_ft["name"], from_ft["remote"]))

    def _push(self, repo, local):
        for branch, remote in self.to_push:
            if local:
                logger.debug(f"Should push {branch} to {remote}")
            else:
                logger.debug(f"Pushing {branch} to {remote}")
                repo.git.push("-f", remote, branch)
        self.to_push = []

    def _sync_at(self, tmpdir, backup, local, features, prev_feature):
        logger.info(f"Work directory at {tmpdir}")
        # Fetch the source branch
        source_remote = prev_feature["remote"]
        source_name = prev_feature["name"]
        source_url = [x["url"] for x in self.config["remotes"] if x["name"] == source_remote][0]
        repo = git.Repo.clone_from(
            source_url,
            tmpdir,
            branch=source_name,
            multi_options=[f"--origin={source_remote}"],
        )
        # Add the remotes
        for remote in self.config["remotes"]:
            if remote["url"] == source_url:
                continue
            else:
                logger.debug(f"Adding remote {remote['name']} at {remote['url']}")
                r = repo.create_remote(remote["name"], remote["url"])
                logger.debug(f"Fetching remote {remote['name']}")
                r.fetch()
        # Keep track of the features but the integrated ones
        prev_active_feature = prev_feature
        has_pending = False
        for feature in features:
            logger.info(f"Syncing feature {feature['name']} with previous active {prev_active_feature['name']}")
            # Checkout the remote branch
            feature_branch = f"{feature['remote']}/{feature['name']}"
            logger.debug(f"Creating local branch {feature_branch}")
            repo.git.checkout("-b", feature["name"], feature_branch)
            # Check the status to know how to proceed
            if feature["status"] == "integrated":
                if has_pending:
                    logger.critical(f"Feature {feature['name']} marked as integrated but after a pending feature")
                    return
                logger.debug(f"Feature {feature['name']} already integrated, nothing to do")
            elif feature["status"] == "_merged":
                # When a feature (feature1) is merged, we don't really know what commits went upstream
                # but we do know that the following feature (feature2) should only apply the commits
                # found on feature2 and not in feature1. This will make the feature1 to be in state
                # integrated afterwards
                logger.debug(f"Feature {feature['name']} already merged, integrating")
                prev_feature = feature
                feature["status"] = "integrated"
            elif feature["status"] == "merging" or feature["status"] == "pending":
                self._rebase(repo, feature, prev_feature, prev_active_feature, backup)
                prev_active_feature = feature
                prev_feature = feature
                has_pending = True
            elif feature["status"] == "_updating":
                logger.debug(f"Updating feature {feature['name']} with {feature['integrating_from']}")
                # Backup the feature before updating
                self._backup_feature(repo, feature)
                # Use the new branch to integrate from
                repo.git.reset("--hard", feature["integrating_from"])
                self._rebase(repo, feature, prev_feature, prev_active_feature, backup)
                prev_active_feature = feature
                prev_feature = feature
                has_pending = True
            elif feature["status"] == "_added":
                logger.debug(f"Added feature {feature['name']}")
                self._rebase(repo, feature, prev_feature, prev_active_feature, backup)
                prev_active_feature = feature
                # Reset the status
                feature["status"] = "pending"
                # We don't update prev_feature so the next branch updates not
                # to this but the previous feature
            elif feature["status"] == "_remove":
                logger.debug(f"Removing feature {feature['name']}")
                # In this case we don't do anything, just skip, so the next feature will
                # rebase on top of the previous one
                prev_feature = feature
            else:
                logger.critical(f"Feature {feature['name']} has unknown status: '{feature['status']}'")
                return
        # Now remove every feature that must be removed
        self.config["features"] = [f for f in self.config["features"] if f["status"] != "_remove"]
        # Make target branch be the last feature
        last_feature = self.config["features"][-1]
        if last_feature:
            if last_feature["status"] != "integrated":
                self._copy(repo, last_feature, self._get_target_feature(), backup)
            else:
                logger.info("All features already integrated, nothing to do")
        # If we are syncing from upstream, make sure to update source too
        upstream_feature = self._get_upstream_feature()
        if (
            source_name == upstream_feature["name"]
            and source_remote == upstream_feature["remote"]
            and not self._upstream_is_source()
        ):
            source_feature = self._get_source_feature()
            # Rename the upstream branch to avoid the case the source and upstream
            # share the same branch name (origin/main and upstream/main)
            upstream_feature_name = f"upstream-{upstream_feature['name']}"
            repo.git.branch("-M", upstream_feature["name"], upstream_feature_name)
            upstream_feature["name"] = upstream_feature_name
            self._copy(repo, upstream_feature, source_feature, backup)
        # Push every branch
        self._push(repo, local)

    def _copy(self, repo, from_feature, to_feature, backup=False):
        to_feature_branch = f"{to_feature['remote']}/{to_feature['name']}"
        logger.info(f"Copying branch {from_feature['remote']}/{from_feature['name']} to {to_feature_branch}")
        # Backup the feature to copy to
        repo.git.checkout("-b", to_feature["name"], to_feature_branch)
        if backup:
            feature_backup_name = self._backup_name(to_feature["name"])
            logger.debug(f"Backing up branch into {feature_backup_name}")
            repo.git.branch("-c", feature_backup_name)
            self.to_push.append((feature_backup_name, to_feature["remote"]))
        repo.git.reset("--hard", from_feature["name"])
        self.to_push.append((to_feature["name"], to_feature["remote"]))

    def _sync(self, backup, keep, local, folder, features=None, prev_feature=None, from_upstream=False):
        features = features if features else self.config["features"]
        if not prev_feature:
            prev_feature = self._get_upstream_feature() if from_upstream else self._get_source_feature()
        tmpdir = folder if folder else tempfile.mkdtemp()
        exception = None
        try:
            self._sync_at(tmpdir, backup, local, features, prev_feature)
        except git.exc.GitCommandError as e:
            exception = e
        if not keep:
            shutil.rmtree(tmpdir)
        if exception:
            logger.error(f"Command failed: {' '.join(exception.command)}")
            print(exception.stdout, file=sys.stdout)
            print(exception.stderr, file=sys.stderr)
            exit(1)

    def sync(self, backup, keep, local, folder):
        self._sync(backup, keep, local, folder, from_upstream=True)

    def dump(self):
        print(tomli_w.dumps(self.config))

    def markdown(self):
        # generate the markup which is something like
        # * `PR` [status] [Branch link][MR link]

        for feature in self.config["features"]:
            remote = feature["remote"]
            url = [x["url"] for x in self.config["remotes"] if x["name"] == remote][0]
            if "https://" in url:
                branch_url = url.replace(".git", "/tree/")
            elif "git@github.com:" in url:
                branch_url = url.replace("git@github.com:", "https://github.com/").replace(".git", "/tree/")
            else:
                branch_url = ""
            li = "* "
            if feature["status"] == "integrated":
                li += "🟢"
            elif feature["status"] == "merging":
                li += "🔄"
            elif feature["status"] == "pending":
                li += "⏳"
            li += f" `{feature['name']}`"
            if "summary" in feature:
                li += f": {feature['summary']}"
            if "pr" in feature:
                li += f" [(PR link)]({feature['pr']})"
            elif branch_url:
                li += f" [(Branch link)]({branch_url}{feature['name']})"
            print(li)

    def check(self):
        remotes = {}
        for remote in self.config["remotes"]:
            remotes[remote["name"]] = remote["url"]

        for feature in self.config["features"]:
            remote = feature["remote"]

            if feature["status"] not in VALID_STATUS:
                logger.error(f"Invalid status for '{feature['name']}': '{feature['status']}'")
                exit(1)

            if not branch_exists_remote(remotes.get(feature["remote"]), feature["name"]):
                logger.error(f"'{feature['name']}' in '{feature['remote']}' does not exist")
                exit(1)

        logger.info("The toml file is correct")

    def add(
        self,
        backup,
        keep,
        local,
        folder,
        new_feature,
        new_feature_remote,
        prev_feature_name,
    ):
        # Add a new feature to the list of features found in the config file
        if not prev_feature_name:
            prev_feature = self.config["features"][-1]["name"]
            idx = len(self.config["features"]) - 1
        else:
            prev_feature, idx = self._get_feature_by_name(prev_feature_name)
            if not prev_feature:
                logger.critical(f"Feature {prev_feature_name} not found")
                return
        # Modify the configuration to include this new feature
        nf = {}
        nf["name"] = new_feature
        nf["remote"] = new_feature_remote
        nf["status"] = "_added"
        # TODO check the existance of the remote
        self.config["features"].insert(idx + 1, nf)
        # If the previous feature is already integrated, it might happen that
        # branch has been deleted
        if prev_feature["status"] == "integrated":
            # If this is integrated, all previous features are also integrated
            prev_feature = None
        # Sync it again
        self._sync(
            backup,
            keep,
            local,
            folder,
            self.config["features"][idx + 1 :],
            prev_feature,
        )
        # Dump the new toml
        self.dump()

    def remove(self, backup, keep, local, folder, to_remove):
        feature, idx = self._get_feature_by_name(to_remove)
        if not feature:
            logger.critical(f"Feature {feature} not found")
            return
        if not idx:
            prev_feature = self._get_source_feature()
        else:
            prev_feature = self.config["features"][idx - 1]
        feature["status"] = "_remove"
        # Sync it again
        self._sync(backup, keep, local, folder, self.config["features"][idx:], prev_feature)
        # Dump the new toml
        self.dump()

    def update(self, backup, keep, local, folder, from_branch, feature_name):
        feature, idx = self._get_feature_by_name(feature_name)
        if not feature:
            logger.critical(f"Feature {feature_name} not found")
            return
        if not idx:
            prev_feature = self._get_source_feature()
        else:
            prev_feature = self.config["features"][idx - 1]

        feature["status"] = "_updating"
        feature["integrating_from"] = from_branch

        # Sync it again
        self._sync(backup, keep, local, folder, self.config["features"][idx:], prev_feature)

    def integrate(self, backup, keep, local, folder, feature_name):
        feature, idx = self._get_feature_by_name(feature_name)
        if not feature:
            logger.critical(f"Feature {feature_name} not found")
            return
        # The feature must be in merging state
        if feature["status"] != "merging":
            logger.critical(f"The feature {feature_name} is not in merging state")
            return
        # TODO We can not integrate a branch with previous not integrated branches
        # Now the feature must be on merged to sync properly
        feature["status"] = "_merged"
        # Sync it again to integrate
        self._sync(backup, keep, local, folder, None, from_upstream=True)
        self.dump()


def _common_command_arguments(cmd_args):
    cmd_args.add_argument("-b", "--backup", help="Generate backup branches", action="store_true")
    cmd_args.add_argument("-k", "--keep", help="Keep working folder", action="store_true")
    cmd_args.add_argument(
        "-l",
        "--local",
        help="Don't push anything, but keep everything local",
        action="store_true",
    )
    cmd_args.add_argument(
        "-d",
        "--directory",
        help="Working directory, otherwise a new temporary directory is used.",
        default=None,
    )


def run():
    levels = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
    }
    # General options
    parser = argparse.ArgumentParser(prog="guw")
    parser.add_argument(
        "-l",
        "--log",
        default="warning",
        choices=[x for x in levels],
        help=("Provide logging level"),
    )
    parser.add_argument("config", help="Configuration file")
    # Subparsers
    subparser = parser.add_subparsers(title="commands", dest="command", required=True)
    # Sync subcommand
    sync_args = subparser.add_parser("sync", help="Sync the list of branches based on the configuration")
    _common_command_arguments(sync_args)
    # Markdown subcommand
    subparser.add_parser("markdown", help="Create a markdown content")
    # Check subcommand
    subparser.add_parser("check", help="Check toml file is correct")
    # Add subcommand
    add_args = subparser.add_parser("add", help="Add a new feature branch")
    _common_command_arguments(add_args)
    add_args.add_argument("new_feature", help="Name of the new feature branch")
    add_args.add_argument("new_feature_remote", help="Remote for the new branch")
    add_args.add_argument(
        "prev_feature",
        help="Name of the feature the new feature should be on top of",
        nargs="?",
    )
    # Remove subcommand
    remove_args = subparser.add_parser("remove", help="Remove a feature")
    _common_command_arguments(remove_args)
    remove_args.add_argument("feature", help="Name of the feature to remove")
    # Update subcommand
    update_args = subparser.add_parser("update", help="Update a feature commits with other's branch commits")
    _common_command_arguments(update_args)
    update_args.add_argument("from_branch", help="Name of the branch to update from")
    update_args.add_argument("feature", help="Name of the feature to update with other branch")
    # Integrate subcommand
    integrate_args = subparser.add_parser("integrate", help="Integrate a feature")
    _common_command_arguments(integrate_args)
    integrate_args.add_argument("feature", help="Name of the feature to integrate")

    # Parse the options, if any
    args = parser.parse_args(sys.argv[1:])
    level = levels[args.log.lower()]
    logger.setLevel(level)

    # Parse the config file

    try:
        with open(args.config, "rb") as fconfig:
            config = tomli.load(fconfig)
    except FileNotFoundError:
        logger.error(f"Error opening file: {args.config}")
        exit(2)
    except tomli.TOMLDecodeError:
        logger.error(f"Error processing TOML file: {args.config}")
        exit(2)

    guw = GUW(config)
    if args.command == "sync":
        guw.sync(args.backup, args.keep, args.local, args.directory)
    elif args.command == "markdown":
        guw.markdown()
    elif args.command == "check":
        guw.check()
    elif args.command == "add":
        guw.add(
            args.backup,
            args.keep,
            args.local,
            args.directory,
            args.new_feature,
            args.new_feature_remote,
            args.prev_feature,
        )
    elif args.command == "remove":
        guw.remove(args.backup, args.keep, args.local, args.directory, args.feature)
    elif args.command == "update":
        guw.update(
            args.backup,
            args.keep,
            args.local,
            args.directory,
            args.from_branch,
            args.feature,
        )
    elif args.command == "integrate":
        guw.integrate(args.backup, args.keep, args.local, args.directory, args.feature)


if __name__ == "__main__":
    run()
