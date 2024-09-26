import argparse
import logging
import os
import shutil
import sys
import tempfile
from datetime import date

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


class GUW:
    def __init__(self, config):
        self.config = config
        self.to_push = []

    def _backup_name(self, name):
        today = str(date.today())
        backup_name = f"{name}-{today}"
        return backup_name

    def _rebase(self, repo, from_ft, until_ft, to_ft, backup=False):
        until_ft_branch = f"{until_ft['remote']}/{until_ft['name']}"
        logger.debug(
            f"Rebasing {from_ft['name']} onto {to_ft['name']} until {until_ft_branch}"
        )
        if backup:
            feature_backup_name = self._backup_name(from_ft["name"])
            logger.debug(f"Backing up {from_ft['name']} into {feature_backup_name}")
            repo.git.branch("-c", feature_backup_name)
            self.to_push.append((feature_backup_name, from_ft["remote"]))
        # Ok, let's rebase on top of the to_ft
        repo.git.rebase("--onto", to_ft["name"], until_ft_branch, from_ft["name"])
        self.to_push.append((from_ft["name"], from_ft["remote"]))

    def _push(self, repo, local):
        if not local:
            for branch, remote in self.to_push:
                logger.debug(f"Pushing {branch} to {remote}")
                repo.git.push("-f", remote, branch)
        self.to_push = []

    def _sync_at(self, tmpdir, backup, local):
        logger.info(f"Work directory at {tmpdir}")

        # Fetch the source branch
        source_remote = self.config["source"]["remote"]
        source_url = [
            x["url"] for x in self.config["remotes"] if x["name"] == source_remote
        ][0]
        repo = git.Repo.clone_from(
            source_url,
            tmpdir,
            branch=self.config["source"]["branch"],
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
        prev_feature = {
            "remote": self.config["source"]["remote"],
            "name": self.config["source"]["branch"],
        }
        # Keep track of the features but the integrated ones
        prev_active_feature = prev_feature
        has_pending = False
        for feature in self.config["features"]:
            logger.info(
                f"Syncing feature {feature['name']} with previous active {prev_active_feature['name']}"
            )
            # Checkout the remote branch
            feature_branch = f"{feature['remote']}/{feature['name']}"
            logger.debug(f"Creating local branch {feature_branch}")
            repo.git.checkout("-b", feature["name"], feature_branch)
            # Check the status to know how to proceed
            if feature["status"] == "integrated":
                if has_pending:
                    logger.critical(
                        f"Feature {feature['name']} marked as integrated but after a pending feature"
                    )
                    return
                logger.debug(
                    f"Feature {feature['name']} already integrated, nothing to do"
                )
                prev_feature = feature
            elif feature["status"] == "merged":
                # When a feature (feature1) is merged, we don't really know what commits went upstream
                # but we do know that the following feature (feature2) should only apply the commits
                # found on feature2 and not in feature1. This will make the feature1 to be in state
                # integrated afterwards
                logger.debug(f"Feature {feature['name']} already merged nothing to do")
                prev_active_feature = feature
                prev_feature = feature
            elif feature["status"] == "merging" or feature["status"] == "pending":
                self._rebase(repo, feature, prev_feature, prev_active_feature, backup)
                prev_active_feature = feature
                prev_feature = feature
                has_pending = True
            elif feature["status"] == "_integrating":
                logger.debug(
                    f"Integrating feature {feature['name']} with {feature['integrating_from']}"
                )
                repo.git.rebase(feature["integrating_from"], "--autosquash")
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
                logger.critical(
                    f"Feature {feature['name']} has unknown status: '{feature['status']}'"
                )
                return
        # Now remove every feature that must be removed
        self.config["features"] = [
            f for f in self.config["features"] if f["status"] != "_remove"
        ]
        # Make target branch be the last feature
        last_feature = self.config["features"][-1]
        if last_feature:
            if last_feature["status"] != "integrated":
                target_branch_name = self.config["target"]["branch"]
                last_feature_branch = f"{last_feature['remote']}/{last_feature['name']}"
                logger.info(
                    f"Making target branch {target_branch_name} based on {last_feature_branch}"
                )
                repo.git.checkout("-b", target_branch_name, last_feature_branch)
                if backup:
                    feature_backup_name = self._backup_name(target_branch_name)
                    logger.debug(f"Backing up target branch into {feature_backup_name}")
                    repo.git.branch("-c", feature_backup_name)
                    self.to_push.append(
                        (feature_backup_name, self.config["target"]["remote"])
                    )
                repo.git.reset("--hard", last_feature["name"])
                self.to_push.append(
                    (target_branch_name, self.config["target"]["remote"])
                )
            else:
                logger.info("All features already integrated, nothing to do")
        # Push every branch
        self._push(repo, local)
        # TODO generate a new .toml for features from merged to integrated

    def sync(self, backup, keep, local, folder):
        tmpdir = folder if folder else tempfile.mkdtemp()
        exception = None
        try:
            self._sync_at(tmpdir, backup, local)
        except git.exc.GitCommandError as e:
            exception = e
        if not keep:
            shutil.rmtree(tmpdir)
        if exception:
            logger.error(f"Command failed: {' '.join(exception.command)}")
            print(exception.stdout, file=sys.stdout)
            print(exception.stderr, file=sys.stderr)
            exit(1)

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
                branch_url = url.replace(
                    "git@github.com:", "https://github.com/"
                ).replace(".git", "/tree/")
            else:
                branch_url = ""
            li = "* "
            if feature["status"] == "integrated":
                li += "🟢"
            elif feature["status"] == "merged":
                li += "✅"
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

    def add(
        self, backup, keep, local, folder, new_feature, new_feature_remote, prev_feature
    ):
        # Add a new feature to the list of features found in the config file
        prev = prev_feature
        if not prev:
            prev = self.config["features"][-1]["name"]
        # Modify the configuration include this new feature
        idx = 0
        found = False
        for feature in self.config["features"]:
            if feature["name"] == prev:
                found = True
                break
            idx += 1
        if not found:
            logger.critical(f"Feature {prev} not found")
            return
        else:
            nf = {}
            nf["name"] = new_feature
            nf["remote"] = new_feature_remote
            nf["status"] = "_added"
            # TODO check the existance of the remote
            self.config["features"].insert(1, nf)
        # Sync it again
        self.sync(backup, keep, local, folder)
        # Dump the new toml
        self.dump()

    def remove(self, backup, keep, local, folder, to_remove):
        found = None
        for feature in self.config["features"]:
            if feature["name"] == to_remove:
                found = feature
                break
        if not found:
            logger.critical(f"Feature {to_remove} not found")
            return
        found["status"] = "_remove"
        # Sync it again
        self.sync(backup, keep, local, folder)
        # Dump the new toml
        self.dump()

    def integrate(self, backup, keep, local, folder, from_branch, feature_name):
        feature = None
        for f in self.config["features"]:
            if f["name"] == feature_name:
                feature = f
                break
        if not feature:
            logger.critical(f"Feature {feature_name} not found")
            return

        feature["status"] = "_integrating"
        feature["integrating_from"] = from_branch

        # Sync it again
        self.sync(backup, keep, local, folder)


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
    sync_args = subparser.add_parser(
        "sync", help="Sync the list of branches based on the configuration"
    )
    sync_args.add_argument(
        "-b", "--backup", help="Generate backup branches", action="store_true"
    )
    sync_args.add_argument(
        "-k", "--keep", help="Keep working folder", action="store_true"
    )
    sync_args.add_argument(
        "-l",
        "--local",
        help="Don't push anything, but keep everything local",
        action="store_true",
    )
    sync_args.add_argument(
        "-d",
        "--directory",
        help="Working directory, otherwise a new temporary directory is used.",
        default=None,
    )
    # Markdown subcommand
    markdown_args = subparser.add_parser("markdown", help="Create a markdown content")
    # Add subcommand
    add_args = subparser.add_parser("add", help="Add a new feature branch")
    add_args.add_argument(
        "-b", "--backup", help="Generate backup branches", action="store_true"
    )
    add_args.add_argument(
        "-k", "--keep", help="Keep working folder", action="store_true"
    )
    add_args.add_argument(
        "-l",
        "--local",
        help="Don't push anything, but keep everything local",
        action="store_true",
    )
    add_args.add_argument(
        "-d",
        "--directory",
        help="Working directory, otherwise a new temporary directory is used.",
        default=None,
    )
    add_args.add_argument("new_feature", help="Name of the new feature branch")
    add_args.add_argument("new_feature_remote", help="Remote for the new branch")
    add_args.add_argument(
        "prev_feature",
        help="Name of the feature the new feature should be on top of",
        nargs="?",
    )
    # Remove subcommand
    add_args = subparser.add_parser("remove", help="Remove a feature")
    add_args.add_argument(
        "-b", "--backup", help="Generate backup branches", action="store_true"
    )
    add_args.add_argument(
        "-k", "--keep", help="Keep working folder", action="store_true"
    )
    add_args.add_argument(
        "-l",
        "--local",
        help="Don't push anything, but keep everything local",
        action="store_true",
    )
    add_args.add_argument(
        "-d",
        "--directory",
        help="Working directory, otherwise a new temporary directory is used.",
        default=None,
    )
    add_args.add_argument("feature", help="Name of the feature to remove")
    # Integrate subcommand
    integrate_args = subparser.add_parser(
        "integrate", help="Integrate the list of branches based on the configuration"
    )
    integrate_args.add_argument(
        "-b", "--backup", help="Generate backup branches", action="store_true"
    )
    integrate_args.add_argument(
        "-k", "--keep", help="Keep working folder", action="store_true"
    )
    integrate_args.add_argument(
        "-l",
        "--local",
        help="Don't push anything, but keep everything local",
        action="store_true",
    )
    integrate_args.add_argument(
        "-d",
        "--directory",
        help="Working directory, otherwise a new temporary directory is used.",
        default=None,
    )
    integrate_args.add_argument(
        "from_branch", help="Name of the branch to integrate from"
    )
    integrate_args.add_argument(
        "feature", help="Name of the feature to integrate with other branch"
    )

    # Parse the options, if any
    args = parser.parse_args(sys.argv[1:])
    level = levels[args.log.lower()]
    logger.setLevel(level)

    # Parse the config file
    with open(args.config, "rb") as fconfig:
        config = tomli.load(fconfig)
        guw = GUW(config)
        if args.command == "sync":
            guw.sync(args.backup, args.keep, args.local, args.directory)
        elif args.command == "markdown":
            guw.markdown()
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
        elif args.command == "integrate":
            guw.integrate(
                args.backup,
                args.keep,
                args.local,
                args.directory,
                args.from_branch,
                args.feature,
            )


if __name__ == "__main__":
    run()
