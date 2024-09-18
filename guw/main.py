import argparse
import colorlog
from datetime import date
import git
import logging
import os
import shutil
import sys
import tempfile
import tomli

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

    def _backup_name(self, name):
        today = str(date.today())
        backup_name = f"{name}-{today}"
        return backup_name

    def _sync_at(self, tmpdir, backup, local):
        logger.info(f"Work directory at {tmpdir}")
        to_push = []

        # Fetch the source branch
        source_remote = self.config["source"]["remote"]
        source_url = [x["url"] for x in self.config["remotes"] if x["name"] == source_remote][0]
        repo = git.Repo.clone_from(source_url, tmpdir, branch=self.config["source"]["branch"], multi_options=[f"--origin={source_remote}"])
        # Add the remotes
        for remote in self.config["remotes"]:
            if remote["url"] == source_url:
                continue
            else:
                logger.debug(f"Adding remote {remote['name']} at {remote['url']}")
                r = repo.create_remote(remote["name"], remote["url"])
                logger.debug(f"Fetching remote {remote['name']}")
                r.fetch()
        prev_feature = {"remote": self.config["source"]["remote"], "name": self.config["source"]["branch"]}
        # Keep track of the features but the integrated ones
        prev_active_feature = prev_feature
        has_pending = False
        for feature in self.config["features"]:
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
            elif feature["status"] == "merged":
                # When a feature (feature1) is merged, we don't really know what commits went upstream
                # but we do know that the following feature (feature2) should only apply the commits
                # found on feature2 and not in feature1. This will make the feature1 to be in state
                # integrated afterwards
                logger.debug(f"Feature {feature['name']} already merged nothing to do")
                prev_active_feature = feature
            elif feature["status"] == "merging" or feature["status"] == "pending":
                prev_feature_branch = f"{prev_feature['remote']}/{prev_feature['name']}"
                logger.debug(f"Rebasing {feature['name']} onto {prev_active_feature['name']} until {prev_feature_branch}")
                if backup:
                    feature_backup_name = self._backup_name(feature['name'])
                    logger.debug(f"Backing up {feature['name']} into {feature_backup_name}")
                    repo.git.branch("-c", feature_backup_name)
                    to_push.append((feature_backup_name, feature["remote"]))
                # Ok, let's rebase on top of the prev_active_feature
                repo.git.rebase("--onto", prev_active_feature["name"], prev_feature_branch, feature["name"])
                to_push.append((feature["name"], feature["remote"]))
                prev_active_feature = feature
                has_pending = True
            else:
                logger.critical(f"Feature {feature['name']} has unknown status: '{feature['status']}'")
                return
            prev_feature = feature
        # Make target branch be the last feature
        last_feature = self.config["features"][-1]
        if last_feature:
            if last_feature["status"] != "integrated":
                target_branch_name = self.config['target']['branch']
                last_feature_branch = f"{last_feature['remote']}/{last_feature['name']}"
                logger.info(f"Making target branch {target_branch_name} based on {last_feature_branch}")
                repo.git.checkout("-b", target_branch_name, last_feature_branch)
                if backup:
                    feature_backup_name = self._backup_name(target_branch_name)
                    logger.debug(f"Backing up target branch into {feature_backup_name}")
                    repo.git.branch("-c", feature_backup_name)
                    to_push.append((feature_backup_name, self.config["target"]["remote"]))
                repo.git.reset("--hard", last_feature["name"])
                to_push.append((target_branch_name, self.config["target"]["remote"]))
            else:
                logger.info("All features already integrated, nothing to do")
        # Push every branch
        if not local:
            for branch,remote in to_push:
                logger.debug(f"Pushing {branch} to {remote}")
                repo.git.push("-f", remote, branch)
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
    sync_args.add_argument("-b", "--backup", help="Generate backup branches", action="store_true")
    sync_args.add_argument("-k", "--keep", help="Keep working folder", action="store_true")
    sync_args.add_argument("-l", "--local", help="Don't push anything, but keep everything local", action="store_true")
    sync_args.add_argument("-d", "--folder", help="Working folder, otherwise a new temporary folder is used.", default=None)
    # Markdown subcommand
    markdown_args = subparser.add_parser("markdown", help="Create a markdown content")

    # Parse the options, if any
    args = parser.parse_args(sys.argv[1:])
    level = levels[args.log.lower()]
    logger.setLevel(level)

    # Parse the config file
    with open(args.config, "rb") as fconfig:
        config = tomli.load(fconfig)
        guw = GUW(config)
        if args.command == "sync":
            guw.sync(args.backup, args.keep, args.local, args.folder)
        elif args.command == "markdown":
            guw.markdown()

if __name__ == '__main__':
    run()
