#!/usr/bin/env python3
"""Little Utility for FAH v8"""

from __future__ import annotations

import argparse
import asyncio
import errno
import logging
import os
import sys
from textwrap import dedent

from websockets.exceptions import ConnectionClosed

from lufah import __version__
from lufah import validate as valid
from lufah.commands.core.config import do_config
from lufah.commands.core.create_group import do_create_group
from lufah.commands.core.dump_all import do_dump_all
from lufah.commands.core.enable_all_gpus import do_enable_all_gpus
from lufah.commands.core.finish_fold_pause import do_finish, do_fold, do_pause
from lufah.commands.core.get import do_get
from lufah.commands.core.groups import do_groups
from lufah.commands.core.info import do_info
from lufah.commands.core.link_account import do_link_account
from lufah.commands.core.log import do_log
from lufah.commands.core.not_implemented import not_implemented
from lufah.commands.core.restart_account import do_restart_account
from lufah.commands.core.start_stop import do_start, do_stop
from lufah.commands.core.state import do_state
from lufah.commands.core.top import HAVE_CURSES, do_top
from lufah.commands.core.units import do_units
from lufah.commands.core.unlink_account import do_unlink_account
from lufah.commands.core.wait_until_paused import do_wait_until_paused
from lufah.commands.core.watch import do_watch
from lufah.exceptions import *  # noqa: F403
from lufah.fahclient import FahClient
from lufah.logger import logger, simple_log_handler
from lufah.util import bool_from_string, eprint, first_non_blank_line

PROGRAM = os.path.basename(sys.argv[0])
if PROGRAM.endswith(".py"):
    PROGRAM = PROGRAM[:-3]
if PROGRAM == "__main__":
    PROGRAM = "lufah"

DEFAULT_COMMAND = "units"

_EPILOG = f"""
Examples

{PROGRAM} units
{PROGRAM} -a //rg2 finish
{PROGRAM} -a other.local state
{PROGRAM} -a /mygpu1 config cpus 0
{PROGRAM} config -h
{PROGRAM} -a host1,host2,host3 units
{PROGRAM} -a host1,host2,host3 info

Notes

If not given, the default command is {DEFAULT_COMMAND!r}.

In 8.3+, if there are multiple groups, config requires a group name,
except for account settings (user, team, passkey, cause).
In 8.3, -a /group config cpus <n> is not limited to unused cpus across groups.

Group names for fah 8.1 must:
  begin "/", have only letters, numbers, period, underscore, hyphen
Group names on 8.3 can have spaces and special chars.
Web Control 8.3 trims leading and trailing white space when creating groups.
Group "/" is taken to mean the default group, which is "".

For a group name actually starting with "/", use prefix "//".
Example: lufah -a somehost//rg1 finish

An error may not be shown if the initial connection times out.
If group does not exist on 8.1, this script may hang until silent timeout.
"""
if sys.platform == "darwin":
    _EPILOG += "Commands start and stop are macOS-only."

HIDDEN_COMMANDS = []  # experimental stuff
NO_CLIENT_COMMANDS = ["start", "stop"]
MULTI_PEER_COMMANDS = ["units", "info", "fold", "finish", "pause", "top"]

# allowed cli commands; all visible
COMMANDS = [
    "state",
    "status",
    "units",
    "fold",
    "finish",
    "pause",
    "unpause",
    "config",
    "groups",
    "create-group",
    "info",
    "log",
    "watch",
    "get",
    "unlink-account",
    "link-account",
    "restart-account",
    "wait-until-paused",
    "enable-all-gpus",
    "dump-all",
]
if HAVE_CURSES:
    COMMANDS += ["top"]
if sys.platform == "darwin":
    COMMANDS += ["start", "stop"]

COMMAND_ALIASES = {
    # alias : actual
    "unpause": "fold",
    "status": "state",  # fahctl has state command
}

# config keys and value validation info
VALID_KEYS_VALUES = {
    "user": {"type": valid.user, "help": valid.user.__doc__},
    "team": {"type": valid.team, "help": valid.team.__doc__},
    "passkey": {"type": valid.passkey, "help": valid.passkey.__doc__},
    "cause": {"type": valid.cause, "help": valid.cause.__doc__},
    "cpus": {"type": valid.cpus, "help": valid.cpus.__doc__},
    "on-idle": {"type": bool_from_string, "help": "Only fold while user is idle."},
    "on-battery": {"type": bool_from_string, "help": "Fold even if on battery."},
    "keep-awake": {
        "type": bool_from_string,
        "help": "Prevent system sleep while folding and not on battery.",
    },
    "cuda": {
        "type": bool_from_string,
        "help": "Enable CUDA for WUs in specified group.",
    },
    "beta": {
        "type": bool_from_string,
        "help": "Enable beta work units. No points will be awarded.",
    },
    "key": {"type": valid.key, "help": valid.key.__doc__},
    "checkpoint": {"type": valid.checkpoint, "help": valid.checkpoint.__doc__},
    "priority": {"type": valid.priority, "help": valid.priority.__doc__},
    "fold-anon": {"type": bool_from_string, "help": "Fold anonymously. (deprecated)"},
}


def postprocess_parsed_args(args: argparse.Namespace):
    if args.debug and args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logger.addHandler(simple_log_handler)

    if args.debug:
        logger.setLevel(logging.DEBUG)
    elif args.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)

    if args.command in [None, ""]:
        args.command = DEFAULT_COMMAND
        args.func = COMMANDS_DISPATCH.get(DEFAULT_COMMAND) or not_implemented
    else:
        args.command = COMMAND_ALIASES.get(args.command, args.command)

    # create peers from peer
    args.peers = []
    if "," in args.peer and "/" not in args.peer:
        # assume comma separated list of peers with no group
        peers = args.peer.split(",")
        for peer in peers:
            peer = peer.strip()
            if peer:
                args.peers.append(peer)
        logger.debug("addresses: %s", repr(args.peers))
        args.peer = None
    else:
        args.peers = [args.peer]

    # FIXME: dispatched functions should handle this
    if args.peer is None and args.command not in MULTI_PEER_COMMANDS:
        raise Exception(f"Error: {args.command!r} cannot use multiple hosts")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=__doc__,
        epilog=_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.set_defaults(key=None, value=None)  # do not remove this
    parser.set_defaults(peer="")  # in case peer is not required in future
    parser.set_defaults(peers=[])
    parser.set_defaults(command=None, func=None)
    parser.set_defaults(keypath=None)
    parser.set_defaults(account_token=None, machine_name=None)

    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)

    parser.add_argument(
        "-a",
        "--address",
        metavar="ADDRESS",
        dest="peer",
        default=".",
        type=valid.address,
        help=dedent(valid.address.__doc__),
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    for cmd in COMMANDS:
        alias_help = None
        true_cmd = cmd
        if cmd in COMMAND_ALIASES:
            true_cmd = COMMAND_ALIASES.get(cmd)
            alias_help = "alias for " + true_cmd
        # if an alias, we will get not_implemented, which we use for description
        func = COMMANDS_DISPATCH.get(cmd) or not_implemented
        desc1 = dedent(alias_help or func.__doc__ or "")
        help1 = (first_non_blank_line(desc1) or "").strip()
        par = subparsers.add_parser(
            cmd,
            description=desc1,
            help=help1,
            formatter_class=argparse.RawTextHelpFormatter,
        )
        # get true dispatch func, un-aliased
        func = COMMANDS_DISPATCH.get(true_cmd) or not_implemented
        par.set_defaults(func=func)
        if cmd == "config":
            config_parsers = par.add_subparsers(
                dest="key", metavar="KEY", required=True
            )
            # add subparser for each valid config key
            for key, info in VALID_KEYS_VALUES.items():
                conv = info.get("type")
                choices = info.get("values")
                kdesc = dedent(info.get("help", ""))
                khelp = (first_non_blank_line(kdesc) or "").strip()
                keyparser = config_parsers.add_parser(
                    key,
                    description=kdesc,
                    help=khelp,
                    formatter_class=argparse.RawTextHelpFormatter,
                )
                if conv or choices:
                    keyparser.add_argument(
                        "value",
                        metavar="VALUE",
                        nargs="?",
                        help=khelp,
                        type=conv,
                        choices=choices,
                    )
        elif cmd == "get":
            par.add_argument(
                "keypath",
                metavar="KEYPATH",
                help="a dot-separated path to a value in client state",
            )
        elif cmd == "link-account":
            par.add_argument(
                "account_token",
                metavar="ACCOUNT-TOKEN",
                type=valid.account_token,
                help=(first_non_blank_line(valid.account_token.__doc__) or "").strip(),
            )
            par.add_argument(
                "machine_name",
                nargs="?",
                metavar="MACHINE-NAME",
                type=valid.machine_name,
                help=(first_non_blank_line(valid.machine_name.__doc__) or "").strip(),
            )
        elif cmd == "dump-all":
            par.add_argument("--force", action="store_true")

    for cmd in HIDDEN_COMMANDS:
        par = subparsers.add_parser(cmd)
        func = COMMANDS_DISPATCH.get(cmd) or not_implemented
        par.set_defaults(func=func)

    args = parser.parse_args()
    postprocess_parsed_args(args)
    return args


COMMANDS_DISPATCH = {
    "state": do_state,
    "fold": do_fold,
    "finish": do_finish,
    "pause": do_pause,
    "log": do_log,
    "config": do_config,
    "groups": do_groups,
    "watch": do_watch,
    "start": do_start,
    "stop": do_stop,
    "units": do_units,
    "info": do_info,
    "get": do_get,
    "unlink-account": do_unlink_account,
    "link-account": do_link_account,
    "restart-account": do_restart_account,
    "create-group": do_create_group,
    "wait-until-paused": do_wait_until_paused,
    "enable-all-gpus": do_enable_all_gpus,
    "dump-all": do_dump_all,
    "top": do_top,
}


async def main_async():
    args = parse_args()

    if args.command not in COMMANDS + HIDDEN_COMMANDS:
        raise Exception(f"Error: Unknown command: {args.command}")

    func = args.func
    if func is None:
        raise Exception(f"Error: Command {args.command} is not implemented")

    client = None
    clients = []
    if args.command not in NO_CLIENT_COMMANDS:
        for peer in args.peers:
            c = FahClient(peer)
            if c is not None:
                clients.append(c)
        if len(clients) == 1:
            client = clients[0]

    args.client = client
    args.clients = clients

    try:
        if asyncio.iscoroutinefunction(func):
            await func(args)
        else:
            func(args)
    except ConnectionClosed:
        logger.info("Connection closed")
    finally:
        for client in clients:
            await client.close()
        await asyncio.sleep(0)


def main():
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, EOFError):
        pass
    except BrokenPipeError:
        # This is common if piping to 'head' or 'more'
        # Python flushes standard streams on exit; redirect remaining output
        # to devnull to avoid another BrokenPipeError at shutdown
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except IOError as e:
        if e.errno != errno.EPIPE:
            eprint(e)
            sys.exit(1)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except Exception as e:
        eprint(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
