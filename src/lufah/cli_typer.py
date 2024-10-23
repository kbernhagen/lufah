"""Little Utility for FAH v8"""

from __future__ import annotations

import argparse
import asyncio
import errno
import logging
import os
import sys
from typing import Callable

try:
    from rich.markup import escape as rich_escape  # type: ignore

    _HAVE_RICH = True
except:  # noqa: E722
    _HAVE_RICH = False

    def rich_escape(s):
        return s


import typer  # type: ignore

# typer doesn't behave well with Annotated on python <3.10
# from typing_extensions import Annotated, Optional

try:
    from trogon import Trogon  # type: ignore  pylint: disable=E0401

    _HAVE_TROGON = True
except:  # noqa: E722
    _HAVE_TROGON = False

from lufah import __version__
from lufah import validate as valid
from lufah.commands import config  # typer subcommand
from lufah.commands.core.create_group import do_create_group
from lufah.commands.core.dump_all import do_dump_all
from lufah.commands.core.enable_all_gpus import do_enable_all_gpus
from lufah.commands.core.finish_fold_pause import do_finish, do_fold, do_pause
from lufah.commands.core.get import do_get
from lufah.commands.core.groups import do_groups
from lufah.commands.core.info import do_info
from lufah.commands.core.link_account import do_link_account
from lufah.commands.core.log import do_log
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
from lufah.util import eprint

COMMANDS_ORDER = [
    "fold",
    "finish",
    "pause",
    "unpause",
    "wait-until-paused",
    "config",
    "create-group",
    "dump-all",
    "enable-all-gpus",
    "state",
    "status",
    "get",
    "groups",
    "info",
    "log",
    "top",
    "units",
    "watch",
    "link-account",
    "unlink-account",
    "restart-account",
]
if _HAVE_TROGON:
    COMMANDS_ORDER += ["trogon"]
if sys.platform == "darwin":
    COMMANDS_ORDER += ["start", "stop"]


class NaturalOrderGroup(typer.core.TyperGroup):
    "Commands in help appear in source code order"

    def list_commands(self, ctx):
        return self.commands.keys()


class ManualOrderGroup(typer.core.TyperGroup):
    "Commands in help manual order"

    def list_commands(self, ctx):
        return COMMANDS_ORDER


app = typer.Typer(
    cls=ManualOrderGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
    # without explicit "rich", some escaped help is improperly rendered
    rich_markup_mode="rich" if _HAVE_RICH else None,
    # rich_help_panel=None,
    epilog="For notes and examples, see https://pypi.org/project/lufah/",
)
app.add_typer(config.app, name="config")


PROGRAM = os.path.basename(sys.argv[0])
if PROGRAM.endswith(".py"):
    PROGRAM = PROGRAM[:-3]

NO_CLIENT_COMMANDS = ["start", "stop"]
MULTI_PEER_COMMANDS = ["units", "info", "fold", "finish", "pause", "top"]


async def _wrap_do_command_async(func: Callable, args: argparse.Namespace):
    try:
        if asyncio.iscoroutinefunction(func):
            await func(args)
        else:
            func(args)
    finally:
        for client in args.clients:
            await client.close()


def _wrap_do_command(func: Callable, args: argparse.Namespace):
    try:
        asyncio.run(_wrap_do_command_async(func, args))
    except KeyboardInterrupt:
        pass


def version_callback(ctx: typer.Context, value: bool):
    """Show version and exit."""
    if ctx.resilient_parsing:
        return
    if value:
        print(__version__)
        raise typer.Exit()


@app.command(help=do_create_group.__doc__)
def create_group(ctx: typer.Context):
    _wrap_do_command(do_create_group, ctx.obj)


@app.command(help=do_dump_all.__doc__)
def dump_all(ctx: typer.Context, force: bool = typer.Option(False, "--force")):
    ctx.obj.force = force
    _wrap_do_command(do_dump_all, ctx.obj)


@app.command(help=do_enable_all_gpus.__doc__)
def enable_all_gpus(ctx: typer.Context):
    _wrap_do_command(do_enable_all_gpus, ctx.obj)


@app.command(help=do_finish.__doc__)
def finish(ctx: typer.Context):
    _wrap_do_command(do_finish, ctx.obj)


@app.command(help=do_fold.__doc__)
def fold(ctx: typer.Context):
    _wrap_do_command(do_fold, ctx.obj)


def complete_get():
    return ["info", "config", "groups", "units"]


@app.command(help=do_get.__doc__)
def get(
    ctx: typer.Context,
    keypath: str = typer.Argument(autocompletion=complete_get),
):
    ctx.obj.keypath = keypath
    _wrap_do_command(do_get, ctx.obj)


@app.command(help=do_groups.__doc__)
def groups(ctx: typer.Context):
    _wrap_do_command(do_groups, ctx.obj)


@app.command(help=do_info.__doc__)
def info(ctx: typer.Context):
    _wrap_do_command(do_info, ctx.obj)


def validate_account_token(ctx: typer.Context, value: str) -> str:
    if ctx.resilient_parsing:
        return None
    return valid.account_token(value)


def validate_machine_name(ctx: typer.Context, value: str) -> str:
    if ctx.resilient_parsing:
        return None
    return valid.machine_name(value)


@app.command(help=do_link_account.__doc__)
def link_account(
    ctx: typer.Context,
    account_token: str = typer.Argument(
        callback=validate_account_token,
        help=valid.account_token.__doc__,
    ),
    machine_name: str = typer.Argument(
        None,
        callback=validate_machine_name,
        help=valid.machine_name.__doc__,
    ),
):
    ctx.obj.account_token = account_token
    ctx.obj.machine_name = machine_name
    _wrap_do_command(do_link_account, ctx.obj)


@app.command(help=do_log.__doc__)
def log(ctx: typer.Context):
    _wrap_do_command(do_log, ctx.obj)


@app.command(help=do_pause.__doc__)
def pause(ctx: typer.Context):
    _wrap_do_command(do_pause, ctx.obj)


@app.command(help=do_restart_account.__doc__)
def restart_account(ctx: typer.Context):
    _wrap_do_command(do_restart_account, ctx.obj)


if sys.platform == "darwin":

    @app.command(help=do_start.__doc__)
    def start(ctx: typer.Context):
        _wrap_do_command(do_start, ctx.obj)


@app.command(help=do_state.__doc__)
def state(ctx: typer.Context):
    _wrap_do_command(do_state, ctx.obj)


@app.command(deprecated=True)
def status(ctx: typer.Context):
    """alias for state"""
    state(ctx)


if sys.platform == "darwin":

    @app.command(help=do_stop.__doc__)
    def stop(ctx: typer.Context):
        _wrap_do_command(do_stop, ctx.obj)


if HAVE_CURSES:

    @app.command(help=do_top.__doc__)
    def top(ctx: typer.Context):
        _wrap_do_command(do_top, ctx.obj)


@app.command(help=do_units.__doc__)
def units(ctx: typer.Context):
    _wrap_do_command(do_units, ctx.obj)


@app.command(help=do_unlink_account.__doc__)
def unlink_account(ctx: typer.Context):
    _wrap_do_command(do_unlink_account, ctx.obj)


@app.command(deprecated=True)
def unpause(ctx: typer.Context):
    """alias for fold"""
    fold(ctx)


@app.command(help=do_wait_until_paused.__doc__)
def wait_until_paused(ctx: typer.Context):
    _wrap_do_command(do_wait_until_paused, ctx.obj)


@app.command(help=do_watch.__doc__)
def watch(ctx: typer.Context):
    _wrap_do_command(do_watch, ctx.obj)


if _HAVE_TROGON:
    # https://github.com/Textualize/trogon/issues/10
    @app.command()
    def trogon(ctx: typer.Context):
        """Build CLI command via Trogon TUI."""
        Trogon(typer.main.get_group(app), click_context=ctx).run()


def validate_address(ctx: typer.Context, value: str) -> str:
    if ctx.resilient_parsing:
        return None
    return valid.address(value)


@app.callback(invoke_without_command=True, no_args_is_help=False, help=__doc__)
def cli_root(
    ctx: typer.Context,
    peer: str = typer.Option(
        "localhost:7396",
        "--address",
        "-a",
        metavar="ADDRESS",
        callback=validate_address,
        help=rich_escape(valid.address.__doc__),
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    debug: bool = typer.Option(False, "--debug", "-d"),
    _version: bool = typer.Option(
        False,
        "--version",
        is_eager=True,
        callback=version_callback,
        help=version_callback.__doc__,
    ),
):
    """typer entrypoint"""
    if debug and verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logger.addHandler(simple_log_handler)

    if debug:
        logger.setLevel(logging.DEBUG)
    elif verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)

    peers = []
    if "/" not in peer:
        peers = peer.split(",")
    if not peers:
        peers = [peer]
    elif len(peers) > 1:
        peer = None

    args = argparse.Namespace()
    args.verbose = verbose
    args.debug = debug
    args.peer = peer
    args.peers = peers
    args.command = ctx.invoked_subcommand or "units"

    if peer is None and args.command not in MULTI_PEER_COMMANDS:
        raise SystemExit(f"Error: {args.command!r} does not support multiple clients")

    clients = []
    for p in peers:
        c = FahClient(p)
        if c is not None:
            clients.append(c)

    args.clients = clients
    args.client = None
    if len(clients) == 1:
        args.client = clients[0]

    ctx.obj = args
    if ctx.invoked_subcommand is None:
        # need to give args if calling directly
        # probably should use ctx.invoke() or forward()
        units(ctx)


def main():
    """main entrypoint"""
    try:
        app()
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
