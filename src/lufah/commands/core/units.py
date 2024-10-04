"show table of all units by group"

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import math
from urllib.parse import urlparse

from lufah.const import STATUS_STRINGS, WAIT_STATUS_STRINGS
from lufah.fahclient import FahClient
from lufah.logger import logger
from lufah.util import natural_delta_from_seconds, shorten_natural_delta


def units_for_group(client, group):
    if client is None:
        logger.error("units_for_group(client, group): client is None")
        return []
    all_units = client.data.get("units", [])
    if group is None or client.version < (8, 3):
        units = all_units
    else:
        units = []
        for unit in all_units:
            g = unit.get("group")
            if g is not None and g == group:
                units.append(unit)
    return units


def _wait_until(unit):
    when_str = unit.get("wait")
    return dt.datetime.fromisoformat(when_str.replace("Z", "+00:00"))


def _waiting(unit):
    now = dt.datetime.now(dt.timezone.utc)
    return unit.get("wait") and now < _wait_until(unit)


def _finish(client, unit):
    if unit.get("state") != "RUN":
        return False
    if client.version < (8, 3):
        finish = client.data.get("config", {}).get("finish", False)
    else:
        group = unit.get("group")
        if group is not None:  # "" is the default group
            gconfig = client.data.get("groups", {}).get(group, {}).get("config", {})
        else:
            gconfig = {}
        finish = gconfig.get("finish", False)
    return finish


def _paused(client, unit):
    if unit.get("pause_reason"):
        return True
    if client.version < (8, 3):
        paused = client.data.get("config", {}).get("paused", False)
    else:
        group = unit.get("group", None)
        if group is not None:
            gconfig = client.data.get("groups", {}).get(group, {}).get("config", {})
            paused = gconfig.get("paused", False)
        else:
            paused = True
    return paused


def _state(client, unit):
    if _waiting(unit):
        return "WAIT"
    state = unit.get("state")
    if state == "DONE":
        result = unit.get("result")
        if result:
            return result.upper()
    if _finish(client, unit):
        return "FINISH"
    if _paused(client, unit):
        return "PAUSE"
    return state or ""


def status_for_unit(client, unit):
    "Human-readable Status string"
    if _waiting(unit):
        state = unit.get("state", "")
        return WAIT_STATUS_STRINGS.get(state) or STATUS_STRINGS.get(state, state)
    reason = unit.get("pause_reason")
    if reason:
        return reason
    state = _state(client, unit)
    return STATUS_STRINGS.get(state, state)


def _group_status(client, group_name):
    "Human-readable group status string"
    if client.version < (8, 3):
        # NOT TESTED, will be deprecated soon anyway
        group = client.data or {}
    else:
        group = client.data.get("groups", {}).get(group_name, {})
    if group.get("config", {}).get("paused"):
        return "Paused"
    wait_str = group.get("wait", "")
    if wait_str:
        now = dt.datetime.now(dt.timezone.utc)
        wait_time = dt.datetime.fromisoformat(wait_str.replace("Z", "+00:00"))
        interval = (wait_time - now).total_seconds()
        if interval > 1:
            wait_str = "Wait " + natural_delta_from_seconds(interval)
        else:
            wait_str = ""
    if group.get("config", {}).get("finish"):
        status = "Finish " + wait_str
    else:
        status = "Run " + wait_str
    return status


def _unit_lines(client, unit) -> list[str]:
    lines = []
    if unit is None:
        return []
    # TODO: unit dataclass
    assignment = unit.get("assignment", {})
    project = assignment.get("project", "")
    core = assignment.get("core", {}).get("type", "")
    status = status_for_unit(client, unit)
    cpus = unit.get("cpus", 0)
    gpus = len(unit.get("gpus", []))
    progress = None
    if _waiting(unit):
        progress = unit.get("wait_progress")
    if progress is None:
        progress = unit.get("wu_progress", unit.get("progress", 0))
    progress = math.floor(progress * 1000) / 10.0
    progress = str(progress) + "%"
    ppd = unit.get("ppd", 0)
    eta = unit.get("eta", "")
    if isinstance(eta, int):
        eta = natural_delta_from_seconds(eta)
    elif isinstance(eta, str):
        eta = shorten_natural_delta(eta)
    assign_time = assignment.get("time")  # str iso UTC
    deadline_str = ""
    if assign_time:
        try:
            deadline = assignment.get("deadline", 0)  # secs from assign time
            now = dt.datetime.now(dt.timezone.utc)
            atime = dt.datetime.fromisoformat(assign_time.replace("Z", "+00:00"))
            dtime = atime + dt.timedelta(seconds=deadline)
            deadline_secs = (dtime - now).total_seconds()
            if deadline_secs <= 0:
                deadline_str = "Expired"
            else:
                deadline_str = natural_delta_from_seconds(deadline_secs)
        except:  # noqa: E722
            pass
    lines.append(
        f"{project:<7}  {cpus:<4}  {gpus:<4}  {core:<4}  {status:<16}{progress:^8}"
        f"  {ppd:<8}  {eta:<7}  {deadline_str:<8}"
    )
    return lines


def _units_header_lines() -> list[str]:
    empty = ""
    width = 70
    hd = "Project  CPUs  GPUs  Core  Status          Progress  PPD       ETA    "
    hd += "  Deadline"
    width = len(hd)
    lines = []
    lines.append(f"{empty:-<{width}}")
    lines.append(hd)
    lines.append(f"{empty:-<{width}}")
    return lines


def units_table_lines(clients: list[FahClient]) -> list[str]:
    if clients is None:
        return []
    lines = []
    lines.extend(_units_header_lines())
    # sort by case insensitive machine_name, with all connected clients first
    for client in sorted(
        clients, key=lambda c: (not c.is_connected, c.machine_name.casefold())
    ):
        r = urlparse(client.uri)
        name = client.machine_name
        if not name:
            name = r.hostname
        if r.port and r.port != 7396:
            name += f":{r.port}"
        if not client.is_connected:
            lines.append(f"{name:<26} {client.state}")
            continue
        groups = client.groups
        if not groups:
            lines.append(name)
            units = units_for_group(client, None)
            if not units:
                continue
            for unit in units:
                lines.extend(_unit_lines(client, unit))
        else:
            for group in groups:
                name_group = f"{name}/{group}"
                lines.append(f"{name_group:<25}  " + _group_status(client, group))
                units = units_for_group(client, group)
                if not units:
                    continue
                for unit in units:
                    lines.extend(_unit_lines(client, unit))
    return lines


def print_unit(client, unit):
    if unit is None:
        return
    for line in _unit_lines(client, unit):
        print(line)


def print_units_header():
    for line in _units_header_lines():
        print(line)


async def do_units(args: argparse.Namespace):
    "Show table of all units by machine name and group."
    await asyncio.gather(*[c.connect() for c in args.clients])
    for line in units_table_lines(args.clients):
        print(line)
