import argparse
import colorlog
import logging
import os
import sys
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

    def sync(self, backup=False):
        # Fetch the source branch
        # Add the remotes
        # Checkout each branch
        # apply each diff of a non merged branch on top of the current aggregated branch
        # Depending on the status, proceed accordingly
        # with --backup, the original branches are kept on branches suffixed by a date
        # generate a new .toml with the changes
        pass

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
    sync_args.add_argument("-b", "--backup", help="Generate backup branches")
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
            guw.sync(args.backup)
        elif args.command == "markdown":
            guw.markdown()
