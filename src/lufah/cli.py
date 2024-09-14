#!/usr/bin/env python3
"""
Little Utility for FAH v8
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import datetime as dt
import errno
import json
import logging
import math
import os
import platform
import sys
from subprocess import check_call
from textwrap import dedent
from urllib.parse import urlparse

from websockets.exceptions import ConnectionClosed

from . import __version__
from . import validate as valid
from .const import (
    DEPRECATED_CONFIG_KEYS,
    GLOBAL_CONFIG_KEYS,
    GROUP_CONFIG_KEYS,
    STATUS_STRINGS,
    VALID_CONFIG_SET_KEYS,
)
from .exceptions import *  # noqa: F403
from .fahclient import FahClient
from .util import (
    bool_from_string,
    diff_dicts,
    eprint,
    format_seconds,
    get_object_at_key_path,
    munged_group_name,
)

PROGRAM = os.path.basename(sys.argv[0])
if PROGRAM.endswith(".py"):
    PROGRAM = PROGRAM[:-3]
if PROGRAM == "__main__":
    PROGRAM = "lufah"

_LOGGER = logging.getLogger(__name__)

# FIXME: default is not restricted
# suggest only allow status, units, log, watch
DEFAULT_COMMAND = "units"

HIDDEN_COMMANDS = []  # experimental stuff
NO_CLIENT_COMMANDS = ["start", "stop", "x"]

MULTI_PEER_COMMANDS = ["units", "info", "fold", "finish", "pause"]

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
if sys.platform == "darwin":
    COMMANDS += ["start", "stop"]

COMMAND_ALIASES = {
    # alias : actual
    "unpause": "fold",
    "status": "state",  # fahctl has state command
}

COMMANDS_HELP = {
    "state": "show json snapshot of client state",
    "pause": "pause folding in specified group or all groups",
    "fold": "start folding in specified group or all groups",
    "finish": "finish folding and pause specified group or all groups",
    "log": "show log; use control-c to exit",
    "config": "get or set config values",
    "start": "start local client service",
    "stop": "stop local client service",
    "groups": "show json array of resource group names",
    "watch": "show incoming messages; use control-c to exit",
    "units": "show table of all units by group",
    "info": "show host and client info",
    "get": "show json value at dot-separated key path in client state",
    "link-account": "account-token [machine-name]",
    "unlink-account": "unlink account requires client 8.3.1 thru 8.3.16",
    "restart-account": "restart account/node connection",
    "create-group": "create group if it does not exist",
    "wait-until-paused": "run until specified group or all groups are paused",
    "enable-all-gpus": "enable all unclaimed gpus in specified group",
    "dump-all": "dump all paused units in specified group or all groups",
}

COMMANDS_DESC = {
    "config": f"""
        get or set config values

        Other than for account settings (user, team, passkey, cause),
        a group must be specified if there is more than one group. E.g.,

          {PROGRAM} -a / config cpus 0
        """,
    "dump-all": """
        dump all paused units in specified group or all groups

        This command is not interactive.
        To dump units, use option "--force".
        You should only dump a WU if it will not be completed before its deadline.
        The ETA may not be accuarate until progress is a few percent done.
        """,
    "link-account": """
        Requested machine-name is currently ignored by client.
        Changing machine-name must be done via Web Control.
        """,
    "restart-account": """
        restart account/node connection
        
        This is useful if the client has lost its node connection
        and is not automatically reconnecting.
        """,
}


# config keys and value validation info
VALID_KEYS_VALUES = {
    "user": {"type": valid.user, "help": valid.user.__doc__},
    "team": {"type": valid.team, "help": valid.team.__doc__},
    "passkey": {"type": valid.passkey, "help": valid.passkey.__doc__},
    "cause": {"type": valid.cause, "help": valid.cause.__doc__},
    "cpus": {"type": valid.cpus, "help": valid.cpus.__doc__},
    "on-idle": {"type": bool_from_string, "help": "fold only when user is idle"},
    "on-battery": {"type": bool_from_string, "help": "fold on battery power"},
    "keep-awake": {"type": bool_from_string, "help": "prevent sleep while folding"},
    "cuda": {"type": bool_from_string, "help": "allow CUDA cores in group"},
    "beta": {"type": bool_from_string, "help": "for internal testing"},
    "key": {"type": valid.key, "help": valid.key.__doc__},
    "checkpoint": {"type": valid.checkpoint, "help": valid.checkpoint.__doc__},
    "priority": {"type": valid.priority, "help": valid.priority.__doc__},
    "fold-anon": {"type": bool_from_string, "help": "deprecated"},
}
# 8.1 resource group name r'^\/[\w.-]*$'
# user recommended ^[0-9a-zA-Z_]+$
# user should not contain alleged reserved chars ^#|~  or \s
# user email discouraged
# in reality, most anything goes up to 100 bytes


def postprocess_parsed_args(args: argparse.Namespace):
    if args.debug:
        args.verbose = True

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    if args.command in [None, ""]:
        args.command = DEFAULT_COMMAND
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
        _LOGGER.debug("addresses: %s", repr(args.peers))
        args.peer = None
    else:
        args.peers = [args.peer]

    # FIXME: dispatched functions should handle this
    if args.peer is None and args.command not in MULTI_PEER_COMMANDS:
        raise Exception(f"Error: {args.command!r} cannot use multiple hosts")


def parse_args() -> argparse.Namespace:
    epilog = f"""
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
        epilog += "Commands start and stop are macOS-only."

    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=__doc__,
        epilog=epilog,
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.set_defaults(key=None, value=None)  # do not remove this
    parser.set_defaults(peer="")  # in case peer is not required in future
    parser.set_defaults(peers=[])
    parser.set_defaults(command=None)
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
        default_help = ""
        if cmd in COMMAND_ALIASES:
            default_help = "alias for " + COMMAND_ALIASES.get(cmd)
        help1 = dedent(COMMANDS_HELP.get(cmd, default_help))
        desc1 = dedent(COMMANDS_DESC.get(cmd, help1))
        par = subparsers.add_parser(
            cmd,
            description=desc1,
            help=help1,
            formatter_class=argparse.RawTextHelpFormatter,
        )
        if cmd == "config":
            config_parsers = par.add_subparsers(
                dest="key", metavar="KEY", required=True
            )
            # add subparser for each valid config key
            for key, info in VALID_KEYS_VALUES.items():
                conv = info.get("type")
                choices = info.get("values")
                kdesc = dedent(info.get("help", ""))
                khelp = kdesc  # TODO, maybe: util.firstline(kdesc).strip()
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
                help=valid.account_token.__doc__,
            )
            par.add_argument(
                "machine_name",
                nargs="?",
                metavar="MACHINE-NAME",
                type=valid.machine_name,
                help=valid.machine_name.__doc__,
            )
        elif cmd == "dump-all":
            par.add_argument("--force", action="store_true")

    for cmd in HIDDEN_COMMANDS:
        subparsers.add_parser(cmd)

    args = parser.parse_args()
    postprocess_parsed_args(args)
    return args


async def do_state(args: argparse.Namespace):
    client = args.client
    await client.connect()
    print(json.dumps(client.data, indent=2))


async def do_command_multi(args: argparse.Namespace):
    for client in args.clients:
        try:
            await client.connect()
            await client.send_command(args.command)
        except Exception as e:
            raise Exception(f"FahClient('{client.name}'):{e}") from e


async def do_config(args: argparse.Namespace):
    client = args.client
    await client.connect()
    key = args.key
    value = args.value
    ver = client.version
    # Note: account can be out-of-date, but does become "" when unlinked
    have_acct = 0 < len(client.data.get("info", {}).get("account", ""))

    # FIXME: potential race if groups changes before we write
    # think currently client deletes groups not in group config command
    groups = client.groups  # [] on 8.2; 8.1 may have peer groups
    # we don't care about 8.1 peer groups because everything is in main config
    # just need to be mindful of possible config.available_cpus

    if (8, 3) <= ver:
        try:
            group = munged_group_name(client.group, client.data)
        except Exception as e:
            raise Exception(f"FahClient('{client.name}'):{e}") from e
    else:
        group = client.group

    # don't require group if there is only one (the default group "")
    if group is None and len(groups) == 1:
        group = groups[0]

    # v8.3 splits config between global(account) and group

    key0 = key  # might exist in 8.1
    key = key.replace("-", "_")  # convert cli keys to actual

    if value is None:
        # print value for key
        if (8, 3) <= ver and key in GROUP_CONFIG_KEYS and group is not None:
            # client.data.groups.{group}.config
            conf = client.data.get("groups", {}).get(group, {}).get("config", {})
            print(json.dumps(conf.get(key)))
        else:
            # try getting key, no matter what it is
            conf = client.data.get("config", {})
            print(json.dumps(conf.get(key, conf.get(key0))))
        return

    if "cpus" == key:
        maxcpus0 = client.data.get("info", {}).get("cpus", 0)
        # available_cpus in fah v8.1.19 only
        maxcpus = client.data.get("config", {}).get("available_cpus", maxcpus0)
        if value > maxcpus:
            raise Exception(f"Error: cpus is greater than available cpus {maxcpus}")
        # FIXME: cpus are in groups on fah 8.3; need to sum cpus across groups
        # available_cpus = maxcpus - total_group_cpus
        # if value > (available_cpus - current_group_cpus)
        # this is simpler if only have one group (the default group)
        # no need to calc available_cpus if new value is 0
        # NOTE: client will not limit cpus value sent for us

    if (8, 3) <= ver:
        if key in DEPRECATED_CONFIG_KEYS:
            raise Exception(f'Error: key "{key0}" is deprecated in fah 8.3')
        if key not in VALID_CONFIG_SET_KEYS:
            raise Exception(f'Error: setting "{key0}" is not supported in fah 8.3')
        if have_acct and key in GLOBAL_CONFIG_KEYS:
            _LOGGER.warning("Machine is linked to an account")
            _LOGGER.warning(' "%s" "%s" may be overwritten by account', key0, value)

    # TODO: don't send if value == current_value
    conf = {key: value}
    msg = {"cmd": "config", "config": conf}
    if (8, 3) <= ver and key in GROUP_CONFIG_KEYS:
        if group is None:
            raise Exception(
                f'Error: cannot set "{key0}" on unspecified group. There are {len(groups)} groups.'
            )
        # create appropriate 8.3 config.groups dict with all current groups
        groupsconf = {}
        for g in groups:
            groupsconf[g] = {}
        groupsconf[group] = conf
        msg["config"] = {"groups": groupsconf}
    await client.send(msg)


async def _print_log_lines(client, msg):
    _ = client
    # client doesn't just send arrays
    if isinstance(msg, list) and len(msg) > 1 and msg[0] == "log":
        # ignore index, which is -1 or -2 or may not exist
        v = msg[-1]
        if isinstance(v, str):
            v = [v]
        try:
            if isinstance(v, (list, tuple)):
                for line in v:
                    if line:
                        print(line)
        except BrokenPipeError:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            await client.close()


async def do_log(args: argparse.Namespace):
    client = args.client
    client.register_callback(_print_log_lines)
    await client.connect()
    await client.send({"cmd": "log", "enable": True})
    if args.debug:
        return
    if client.is_connected:
        try:
            await client.ws.wait_closed()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass


async def do_show_groups(args: argparse.Namespace):
    client = args.client
    await client.connect()
    print(json.dumps(client.groups))


async def do_get(args: argparse.Namespace):
    client = args.client
    await client.connect()
    value = get_object_at_key_path(client.data, args.keypath)
    print(json.dumps(value, indent=2))


async def _print_json_message(client, msg):
    _ = client
    if isinstance(msg, (list, dict, str)):
        print(json.dumps(msg))


async def do_watch(args: argparse.Namespace):
    client = args.client
    client.register_callback(_print_json_message)
    client.should_process_updates = args.debug
    await client.connect()
    if args.debug:
        snapshot0 = copy.deepcopy(client.data)
    print(json.dumps(client.data, indent=2))
    try:
        await client.ws.wait_closed()
    except (KeyboardInterrupt, asyncio.CancelledError):
        _LOGGER.debug("do_watch() caught KeyboardInterrupt or asyncio.CancelledError")
    finally:
        if args.debug:
            diff = diff_dicts(snapshot0, client.data)
            print("\nChanges since connection opened:\n", json.dumps(diff, indent=2))


def print_units_header():
    empty = ""
    width = 70
    hd = "Project  CPUs  GPUs  Core  Status          Progress  PPD       ETA    "
    hd += "  Deadline"
    width = len(hd)
    print(f"{empty:-<{width}}")
    print(hd)
    print(f"{empty:-<{width}}")


def status_for_unit(client, unit):
    """Human-readable Status string"""
    # FIXME: should exactly match what Web Control does
    # FIXME: waiting is web control unitview.waiting
    # if unit.get('waiting'): return STATUS_STRINGS.get('WAIT', state)
    status = unit.get("pause_reason")
    if status:
        # assume paused if have pause_reason
        return status
    state = unit.get("state", "")  # is never FINISH
    if state == "RUN":
        if client.version < (8, 3):
            paused = client.data.get("config", {}).get("paused", False)
            finish = client.data.get("config", {}).get("finish", False)
        else:
            group = unit.get("group", None)
            if group is not None:
                gconfig = client.data.get("groups", {}).get(group, {}).get("config", {})
                paused = gconfig.get("paused", False)
                finish = gconfig.get("finish", False)
            else:
                paused = True
                finish = False
        if paused:
            state = "PAUSE"
        elif finish:
            state = "FINISH"
    return STATUS_STRINGS.get(state, state)


def shorten_eta(eta: str):
    eta = eta.replace(" days", "d").replace(" day", "d")
    eta = eta.replace(" hours", "h").replace(" hour", "h")
    eta = eta.replace(" mins", "m").replace(" min", "m")
    eta = eta.replace(" secs", "s").replace(" sec", "s")
    return eta


def print_unit(client, unit):
    if unit is None:
        return
    # TODO: unit dataclass
    assignment = unit.get("assignment", {})
    project = assignment.get("project", "")
    core = assignment.get("core", {}).get("type", "")
    status = status_for_unit(client, unit)
    cpus = unit.get("cpus", 0)
    gpus = len(unit.get("gpus", []))
    # FIXME: there can also be wait_progress
    progress = unit.get("wu_progress", unit.get("progress", 0))
    progress = math.floor(progress * 1000) / 10.0
    progress = str(progress) + "%"
    ppd = unit.get("ppd", 0)
    eta = unit.get("eta", "")
    if isinstance(eta, int):
        eta = format_seconds(eta)
    elif isinstance(eta, str):
        eta = shorten_eta(eta)
    assign_time = assignment.get("time")  # str iso UTC
    deadline_str = ""
    if assign_time:
        try:
            deadline = assignment.get("deadline", 0)  # secs from assign time
            now = dt.datetime.now(dt.timezone.utc)
            atime = dt.datetime.fromisoformat(assign_time.replace("Z", "+00:00"))
            dtime = atime + dt.timedelta(seconds=deadline)
            deadline_secs = (dtime - now).total_seconds()
            deadline_str = format_seconds(deadline_secs)
        except:  # noqa: E722
            pass
    print(
        f"{project:<7}  {cpus:<4}  {gpus:<4}  {core:<4}  {status:<16}{progress:^8}"
        f"  {ppd:<8}  {eta:<7}  {deadline_str:<8}"
    )


def units_for_group(client, group):
    if client is None:
        _LOGGER.error(" units_for_group(client, group): client is None")
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


async def do_print_units(args: argparse.Namespace):
    clients = args.clients
    for client in clients:
        await client.connect()
    if clients:
        print_units_header()
    for client in sorted(clients, key=lambda c: c.machine_name):
        r = urlparse(client.uri)
        name = client.machine_name
        if not name:
            name = r.hostname
        if r.port and r.port != 7396:
            name += f":{r.port}"
        groups = client.groups
        if not groups:
            if not client.is_connected:
                print(name + "  NOT CONNECTED")
                continue
            print(name)
            units = units_for_group(client, None)
            if not units:
                continue
            for unit in units:
                print_unit(client, unit)
        else:
            for group in groups:
                print(f"{name}/{group}")
                units = units_for_group(client, group)
                if not units:
                    continue
                for unit in units:
                    print_unit(client, unit)


def print_info(client):
    if client is None:
        return
    info = client.data.get("info", {})
    if not info:
        return
    clientver = info.get("version", "")  # the string, not tuple
    osname = info.get("os", "")
    osver = info.get("os_version", "")
    cpu = info.get("cpu", "")
    brand = info.get("cpu_brand", "")
    cores = info.get("cpus", 0)
    host = info.get("hostname", "")
    print(f"  Host: {host}")
    print(f"Client: {clientver}")
    print(f"    OS: {osname} {osver}")
    print(f'   CPU: {cores} cores, {cpu}, "{brand}"')


async def do_print_info_multi(args: argparse.Namespace):
    for client in args.clients:
        await client.connect()
    clients = sorted(args.clients, key=lambda c: c.machine_name)
    multi = len(clients) > 1
    if multi:
        print()
    for client in clients:
        print_info(client)
        if multi:
            print()


def do_start_or_stop_local_sevice(args: argparse.Namespace):
    if sys.platform == "darwin" and args.command in ["start", "stop"]:
        if args.peer not in [".", "localhost", "", None]:
            raise Exception(
                "commands start and stop only apply to local client service"
            )
        note = f"org.foldingathome.fahclient.nobody.{args.command}"
        cmd = ["notifyutil", "-p", note]
        if args.debug:
            _LOGGER.debug("WOULD BE running: %s", " ".join(cmd))
            return
        _LOGGER.info("%s", " ".join(cmd))
        check_call(cmd)


async def do_create_group(args: argparse.Namespace):
    client = args.client
    await client.connect()
    await client.create_group(client.group)


async def do_unlink_account(args: argparse.Namespace):
    client = args.client
    await client.connect()
    if (8, 3, 1) <= client.version and client.version < (8, 3, 17):
        await client.send({"cmd": "reset"})
    else:
        raise Exception("Error: unlink account requires client 8.3.1 thru 8.3.16")


async def do_restart_account(args: argparse.Namespace):
    client = args.client
    await client.connect()
    if (8, 3, 17) <= client.version:
        await client.send({"cmd": "restart"})
    else:
        raise Exception("restart account requires client 8.3.17+")


async def do_link_account(args: argparse.Namespace):
    client = args.client
    await client.connect()
    if (8, 3, 1) <= client.version:
        token = args.account_token
        name = args.machine_name
        if not token:
            token = client.data.get("info", {}).get("account", "")
        if not name:
            name = client.data.get("info", {}).get("mach_name", "")
        if not name and args.peer == ".":
            name = platform.node()
        if not (token and name):
            raise Exception("Error: unable to determine token and name")
        msg = {"cmd": "link", "token": token, "name": name}
        await client.send(msg)


async def _close_if_paused(client, _):
    # unused: msg
    group = client.group
    if group is None:
        groups = client.groups
    elif group not in client.groups:
        raise Exception(f'group "{group}" does not exist')
    else:
        groups = [group]
    for group in groups:
        # return if any group is not paused
        gconfig = client.data.get("groups", {}).get(group, {}).get("config", {})
        paused = gconfig.get("paused", None)
        # finish = gconfig.get('finish', False)
        if paused is False:
            return
        if paused is None:
            _LOGGER.warning('no value for paused in group "%s"', group)
    # all target groups are assumed paused
    await client.close()


async def do_wait_until_paused(args: argparse.Namespace):
    client = args.client
    client.register_callback(_close_if_paused)
    client.should_process_updates = True
    await client.connect()
    if client.version < (8, 3, 17):
        raise Exception("wait-until-paused requires client 8.3.17+")
    if args.debug:
        return
    # process initial connection snapshot
    await _close_if_paused(client, None)
    if client.is_connected:
        await client.ws.wait_closed()


async def do_enable_all_gpus(args: argparse.Namespace):
    client = args.client
    await client.connect()
    if client.version < (8, 3, 17):
        raise Exception("enable-all-gpus requires client 8.3.17+")
    if client.group is None or client.group not in client.groups:
        raise Exception("an existing group must be specified for enable-all-gpus")
    all_gpus = client.data.get("info", {}).get("gpus", {})
    # get set of all_supported gpu ids, info.gpus id with "supported" True
    all_supported = set()
    for gpuid in all_gpus.keys():
        if all_gpus.get(gpuid, {}).get("supported") is True:
            all_supported.add(gpuid)
    if len(all_supported) == 0:
        _LOGGER.warning("no supported gpus found")
        return
    # get set of already_enabled gpus across all groups
    already_enabled = set()
    groups_dict = client.data.get("groups", {})
    for group in client.groups:
        gconfgpus = groups_dict.get(group, {}).get("config", {}).get("gpus", {})
        for gpuid in gconfgpus.keys():
            if gconfgpus.get(gpuid, {}).get("enabled") is True:
                already_enabled.add(gpuid)

    to_enable = all_supported - already_enabled
    _LOGGER.debug("all_supported: %s", repr(all_supported))
    _LOGGER.debug("already_enabled: %s", repr(already_enabled))
    _LOGGER.info("to_enable: %s", repr(to_enable))
    if len(to_enable) == 0:
        _LOGGER.warning("no gpus to enable")
        return
    # create group config with to_enable gpus, {gpuid = {enabled = True}}
    # start with existing gpus, so we don't disable any in target group
    groupconf = client.data.get("groups", {}).get(client.group, {}).get("config", {})
    target_group_conf_gpus = groupconf.get("gpus", {}).copy()
    for gpuid in to_enable:
        target_group_conf_gpus[gpuid] = {"enabled": True}
    # create config dict {"groups" = {groupname = {},...}}
    # need empty conf for each existing group
    groupsconf = {}
    for g in client.groups:
        groupsconf[g] = {}
    groupsconf[client.group] = {"gpus": target_group_conf_gpus}
    conf = {"groups": groupsconf}
    # send config
    await client.send({"cmd": "config", "config": conf})


async def do_dump_all(args: argparse.Namespace):
    client = args.client
    await client.connect()
    if client.version < (8, 3):
        raise Exception("dump-all requires client 8.3+")
    group = client.group
    units = client.paused_units_in_group(group)
    if len(units) == 0:
        msg = f"{client.name}: no paused units found"
        if group is not None:
            msg += f' in group "{group}"'
        if sys.stdout.isatty():
            print(msg)
        else:
            _LOGGER.info("%s", msg)
        return
    if sys.stdout.isatty():
        print("Units to dump:")
        print_units_header()
        for unit in units:
            print_unit(client, unit)
    if not args.force:
        msg = f"{client.name}: to dump units, use option --force"
        if sys.stdout.isatty():
            print(msg)
        else:
            _LOGGER.warning("%s", msg)
        return
    for unit in units:
        await client.dump_unit(unit)


COMMANDS_DISPATCH = {
    "state": do_state,
    "fold": do_command_multi,
    "finish": do_command_multi,
    "pause": do_command_multi,
    "log": do_log,
    "config": do_config,
    "groups": do_show_groups,
    "watch": do_watch,
    "start": do_start_or_stop_local_sevice,
    "stop": do_start_or_stop_local_sevice,
    "units": do_print_units,
    "info": do_print_info_multi,
    "get": do_get,
    "unlink-account": do_unlink_account,
    "link-account": do_link_account,
    "restart-account": do_restart_account,
    "create-group": do_create_group,
    "wait-until-paused": do_wait_until_paused,
    "enable-all-gpus": do_enable_all_gpus,
    "dump-all": do_dump_all,
}


async def main_async():
    args = parse_args()

    if args.command not in COMMANDS + HIDDEN_COMMANDS:
        raise Exception(f"Error:Unknown command: {args.command}")

    func = COMMANDS_DISPATCH.get(args.command)
    if func is None:
        raise Exception(f"Error:Command {args.command} is not implemented")

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
        _LOGGER.info("Connection closed")
    finally:
        for client in clients:
            await client.close()


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "help":
        sys.argv[1] = "-h"
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, EOFError):
        pass
    except BrokenPipeError:
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
