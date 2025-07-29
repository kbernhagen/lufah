"show wu history and exit"

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import locale
import os
import sys

from tabulate2 import tabulate

from lufah.commands.core import units
from lufah.fahclient import FahClient
from lufah.logger import logger
from lufah.util import natural_delta_from_seconds

_N = 0  # max table rows; <=0 is unlimited
_FILTERS = {}

# Unit Display values


def assigned_after(unit: dict, target_time: dt.datetime) -> bool:
    assignment = unit.get("assignment", {})
    assign_time_str = assignment.get("time", "")
    atime = dt.datetime.fromisoformat(assign_time_str.replace("Z", "+00:00"))
    return target_time <= atime


def ud_assign_delta(_: FahClient, unit: dict):
    "Human-readable time interval from assignment time to now"
    assignment = unit.get("assignment", {})
    assign_time_str = assignment.get("time", "")
    atime = dt.datetime.fromisoformat(assign_time_str.replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    ago_secs = (atime - now).total_seconds()
    return natural_delta_from_seconds(ago_secs)


def ud_core_type(_: FahClient, unit: dict):
    assignment = unit.get("assignment", {})
    core = assignment.get("core", {})
    return core.get("type", "")


def ud_ppd(_: FahClient, unit: dict):
    ppd = unit.get("ppd", 0)
    return f"{ppd:n}"


def ud_progress(_: FahClient, unit: dict):
    return units.progress(unit)


def ud_project(_: FahClient, unit: dict):
    assignment = unit.get("assignment", {})
    return assignment.get("project", "")


def ud_short_os(client: FahClient, _: dict):
    name = client.data.get("info", {}).get("os", "")
    subst = {"macosx": "Mac", "linux": "Lin", "win32": "Win"}
    return subst.get(name, name)


def ud_status(client: FahClient, unit: dict):
    s = unit.get("result", units.status_for_unit(client, unit))
    return s


def ud_tpf(_: FahClient, unit: dict):
    return units.tpf(unit)


class Column:  # pylint: disable=too-few-public-methods
    "Utility class for tabulate"

    def __init__(self, name, func=None, align="left", floatfmt=".2f"):
        self.name = name
        self.align = align
        self.floatfmt = floatfmt
        self.func = func  # Callable [client, unit]


columns = [
    Column("Project", ud_project),
    Column("Core", ud_core_type),
    Column("OS", ud_short_os),
    Column("Status", ud_status),
    Column("Progress", ud_progress, align="right"),
    Column("TPF", ud_tpf, align="right"),
    Column("PPD", ud_ppd, align="right"),
    Column("Assigned", ud_assign_delta, align="right"),
]

headers = [col.name for col in columns]
colalign = tuple(col.align for col in columns)


def _print_table(client: FahClient, wunits: list):
    data = []
    if _FILTERS:
        project = _FILTERS.get("project")
        core = _FILTERS.get("core")
        os_name = _FILTERS.get("os")
        status = _FILTERS.get("status")
        days = _FILTERS.get("within")
        if days is not None:
            now = dt.datetime.now(dt.timezone.utc)
            target_time = now - dt.timedelta(days=days)
        else:
            target_time = None
        filtered = []
        for unit in wunits:
            if (
                (project is None or project == ud_project(client, unit))
                and (core is None or "0x" + core == ud_core_type(client, unit).lower())
                and (os_name is None or os_name == ud_short_os(client, unit).lower())
                and (
                    status is None or ud_status(client, unit).lower().startswith(status)
                )
                and (days is None or assigned_after(unit, target_time))
            ):
                filtered.append(unit)
        wunits = filtered
    if _N > 0:
        wunits = wunits[:_N]
    for unit in wunits:
        row = []
        for col in columns:
            row.append(col.func(client, unit))
        data.append(row)
    print(tabulate(data, headers=headers, colalign=colalign))
    # print(wunits[0])


async def _print_history(client, msg):
    "When wus is sent, print history and trigger exit"
    if isinstance(msg, list) and len(msg) > 1 and msg[0] == "wus":
        # got wu hist (may be empty); print and exit
        try:
            v = msg[-1]
            if len(v) < 1:
                logger.info("No work units in history")
                await client.close()
                return
            _print_table(client, v)
            sys.stdout.flush()  # ensure any SIGPIPE occurs in this try block
        except BrokenPipeError:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        finally:
            await client.close()


async def do_history(args: argparse.Namespace):
    "Show work unit history and exit."
    global _N, _FILTERS  # pylint: disable=global-statement
    client = args.client
    client.register_callback(_print_history)
    locale.setlocale(locale.LC_ALL, "")
    _N = max(0, args.n)
    if args.filters:
        _FILTERS = args.filters
    await client.connect()
    if client.version < (8, 4, 8):
        raise Exception("Error: history requires client 8.4.8+")
    await client.send({"cmd": "wus", "enable": True})
    if args.debug:
        return
    if client.is_connected:
        try:
            await asyncio.wait_for(client.ws.wait_closed(), timeout=20)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
