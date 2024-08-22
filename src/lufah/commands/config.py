"""
Get or set config values.

Other than for account settings (user, team, passkey, cause),
a group must be specified if there is more than one group.
Example:
    lufah -a / config cpus 0
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

import typer  # type: ignore  pylint: disable=import-error
from typing_extensions import Optional  # type: ignore

from lufah import validate as valid
from lufah.commands.core.config import do_config
from lufah.const import KNOWN_CAUSES

# Note: trogon seems to have trouble with optional bool args, so they are opt str
from lufah.util import bool_from_string

app = typer.Typer(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Get or set config values",
    subcommand_metavar="KEY",
)


@app.callback(help=__doc__)
def config(): ...


async def _wrap_do_config_async(args: argparse.Namespace, akey: str, value: Any):
    args.key = akey
    args.value = value
    try:
        await do_config(args)
    finally:
        for client in args.clients:
            await client.close()


def _wrap_do_config(args: argparse.Namespace, akey: str, value: Any):
    try:
        asyncio.run(_wrap_do_config_async(args, akey, value))
    except KeyboardInterrupt:
        pass


def complete_bool():
    return ["true", "false", "1", "0"]


@app.command("cpus", help=valid.cpus.__doc__)
def cpus(
    ctx: typer.Context,
    count: Optional[int] = typer.Argument(
        None, min=0, max=256, help="non-negative number of cpus to use"
    ),
):
    _wrap_do_config(ctx.obj, "cpus", count)


@app.command(help=valid.user.__doc__)
def user(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(None),
):
    _wrap_do_config(ctx.obj, "user", value)


@app.command(help=valid.team.__doc__)
def team(
    ctx: typer.Context,
    value: Optional[int] = typer.Argument(None, min=0, max=0x7FFFFFFF),
):
    _wrap_do_config(ctx.obj, "team", value)


def validate_passkey(ctx: typer.Context, value: str) -> str:
    if ctx.resilient_parsing:
        return None
    return valid.passkey(value)


@app.command(help=valid.passkey.__doc__)
def passkey(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(None, callback=validate_passkey),
):
    _wrap_do_config(ctx.obj, "passkey", value)


@app.command()
def on_battery(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(
        None,
        callback=bool_from_string,
        help="bool string",
        autocompletion=complete_bool,
    ),
):
    """
    Fold even if on battery.

    Value is a boolean string (true,false,1,0).
    """
    _wrap_do_config(ctx.obj, "on-battery", value)


@app.command(deprecated=True)
def fold_anon(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(
        None,
        callback=bool_from_string,
        help="bool string",
        autocompletion=complete_bool,
    ),
):
    """
    Fold anonymously.

    Value is a boolean string (true,false,1,0).
    """
    _wrap_do_config(ctx.obj, "fold-anon", value)


@app.command(help=valid.key.__doc__)
def key(
    ctx: typer.Context,
    value: Optional[int] = typer.Argument(None, min=0, max=0xFFFFFFFFFFFFFFFF),
):
    _wrap_do_config(ctx.obj, "key", value)


@app.command()
def beta(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(
        None,
        callback=bool_from_string,
        help="bool string",
        autocompletion=complete_bool,
    ),
):
    """
    Enable beta work units. No points will be awarded.

    Value is a boolean string (true,false,1,0).
    """
    _wrap_do_config(ctx.obj, "beta", value)


def validate_cause(ctx: typer.Context, value: Optional[str]) -> str:
    if ctx.resilient_parsing:
        return None
    if value is None:
        return None
    if value:
        value = value.lower()
    if value in KNOWN_CAUSES:
        return value
    raise typer.BadParameter("unknown cause")


# https://typer.tiangolo.com/tutorial/options-autocompletion/
def complete_cause(incomplete: str):
    for name in KNOWN_CAUSES:
        if name.startswith(incomplete):
            yield name


@app.command(help=valid.cause.__doc__)
def cause(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(
        None,
        callback=validate_cause,
        autocompletion=complete_cause,
        help=",".join(KNOWN_CAUSES),
    ),
):
    _wrap_do_config(ctx.obj, "cause", value)


@app.command()
def keep_awake(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(
        None,
        callback=bool_from_string,
        help="bool string",
        autocompletion=complete_bool,
    ),
):
    """
    Prevent system sleep while folding and not on battery.

    Value is a boolean string (true,false,1,0).
    """
    _wrap_do_config(ctx.obj, "keep-awake", value)


@app.command()
def on_idle(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(
        None,
        callback=bool_from_string,
        help="bool string",
        autocompletion=complete_bool,
    ),
):
    """
    Only fold while user is idle.

    This is usually when the system blanks the screen.
    Value is a boolean string (true,false,1,0).
    """
    _wrap_do_config(ctx.obj, "on-idle", value)


@app.command()
def cuda(
    ctx: typer.Context,
    # value: Optional[bool] = typer.Argument(None),  # trogon dislikes
    value: Optional[str] = typer.Argument(
        None,
        callback=bool_from_string,
        help="bool string",
        autocompletion=complete_bool,
    ),
):
    """
    Enable CUDA for WUs in specified group.

    Value is a boolean string (true,false,1,0).
    """
    _wrap_do_config(ctx.obj, "cuda", value)


@app.command(deprecated=True, help=valid.checkpoint.__doc__)
def checkpoint(
    ctx: typer.Context,
    value: Optional[int] = typer.Argument(None, min=3, max=30),
):
    _wrap_do_config(ctx.obj, "checkpoint", value)


_VALID_PRIORITIES = ["idle", "low", "normal", "inherit"]


def complete_priority():
    return _VALID_PRIORITIES


@app.command(deprecated=True, help=valid.priority.__doc__)
def priority(
    ctx: typer.Context,
    value: Optional[str] = typer.Argument(
        None, help=",".join(_VALID_PRIORITIES), autocompletion=complete_priority
    ),
):
    _wrap_do_config(ctx.obj, "priority", value)
