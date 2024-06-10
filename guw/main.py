import argparse
import colorlog
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

    def _sync_at(self, tmpdir, backup):
        logger.info(f"Work directory at {tmpdir}")

        # Fetch the source branch
        source_remote = [x["url"] for x in self.config["remotes"] if x["name"] == self.config["source"]["remote"]][0]
        # TODO set the remote name instead of origin
        repo = git.Repo.clone_from(source_remote, tmpdir, branch=self.config["source"]["branch"])
        # Add the remotes
        for remote in self.config["remotes"]:
            if remote["url"] == source_remote:
                continue
            else:
                logger.debug(f"Adding remote {remote['name']} at {remote['url']}")
                r = repo.create_remote(remote["name"], remote["url"])
                logger.debug(f"Fetching remote {remote['name']}")
                r.fetch()
        # Create the target branch locally
        prev_feature = {"remote": self.config["source"]["remote"], "name": self.config["source"]["branch"]}
        # Keep track of the features but the integrated ones
        prev_active_feature = prev_feature
        has_pending = False
        for feature in self.config["features"]:
            logger.info(f"Syncing feature {feature['name']} with previous active {prev_active_feature['name']}")
            # Checkout the remote branch
            logger.debug(f"Creating local branch {feature['remote']}/{feature['name']}")
            repo.git.checkout("-b", feature["name"], "{}/{}".format(feature["remote"], feature["name"]))
            # Check the status to know how to proceed
            if feature["status"] == "integrated":
                if has_pending:
                    logger.critical(f"Feature {feature['name']} marked as integrated but after a pending feature")
                    break
                logger.debug(f"Feature {feature['name']} already integrated, nothing to do")
            elif feature["status"] == "merged":
                # When a feature (feature1) is merged, we don't really know what commits went upstream
                # but we do know that the following feature (feature2) should only apply the commits
                # found on feature2 and not in feature1.
                logger.debug(f"Feature {feature['name']} already merged nothing to do")
                prev_active_feature = feature
            elif feature["status"] == "merging" or feature["status"] == "pending":
                logger.debug(f"Rebasing {feature['name']} onto {prev_active_feature['name']} until {prev_feature['remote']}/{prev_feature['name']}")
                # Checkout the feature locally
                # Ok, let's rebase on top of the prev_active_feature
                repo.git.rebase("--onto", prev_active_feature["name"], f"{prev_feature['remote']}/{prev_feature['name']}", feature["name"])
                prev_active_feature = feature
                has_pending = True
            prev_feature = feature

        # apply each diff of a non merged branch on top of the current aggregated branch
        # Depending on the status, proceed accordingly
        # with --backup, the original branches are kept on branches suffixed by a date
        # generate a new .toml with the changes

    def sync(self, backup=True, keep=False):
        tmpdir = tempfile.mkdtemp()
        exception = None
        try:
            self._sync_at(tmpdir, backup)
        except git.exc.GitCommandError as e:
            exception = e
        if not keep:
            shutil.rmtree(tmpdir)
        if exception:
            raise exception

    def markdown(self):
        # generate the markup which is something like
        # * PR [status] [MR link]
        pass


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
    subparser = parser.add_subparsers(title="commands", dest="command")
    # Sync subcommand
    sync_args = subparser.add_parser("sync", help="Sync the list of branches based on the configuration")
    sync_args.add_argument("-b", "--backup", help="Generate backup branches", action="store_true")
    sync_args.add_argument("-k", "--keep", help="Keep temporary folder", action="store_true")
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
            guw.sync(args.backup, args.keep)
        elif args.command == "markdown":
            guw.markdown()
