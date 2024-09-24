# pylint: disable=missing-module-docstring

import argparse
import sys
from subprocess import check_call
from urllib.parse import urlparse

from lufah.logger import logger
from lufah.util import split_address_and_group


def _start_or_stop_local_sevice(args: argparse.Namespace, command=None):
    if sys.platform == "darwin" and args.command in ["start", "stop"]:
        addr, _ = split_address_and_group(args.peer)
        host = urlparse("ws://" + addr).hostname
        if host not in [".", "", None, "localhost", "127.0.0.1"]:
            logger.error("Commands start and stop only apply to local client service")
            raise SystemExit
        note = f"org.foldingathome.fahclient.nobody.{command or args.command}"
        cmd = ["notifyutil", "-p", note]
        if args.debug:
            logger.debug("WOULD BE running: %s", " ".join(cmd))
            return
        logger.info("%s", " ".join(cmd))
        check_call(cmd)


def do_start(args: argparse.Namespace):
    "Start local client service."
    _start_or_stop_local_sevice(args, command="start")


def do_stop(args: argparse.Namespace):
    "Stop local client service."
    _start_or_stop_local_sevice(args, command="stop")
