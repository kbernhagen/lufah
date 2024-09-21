"""lufah utility functions"""

from __future__ import annotations

import importlib
import json
import operator
import re
import socket
import sys
from functools import reduce
from typing import Callable, Optional, Union
from urllib.parse import urlparse
from urllib.request import urlopen

from .exceptions import FahClientGroupDoesNotExist
from .logger import logger


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def bool_from_string(value: Optional[str]) -> bool:
    if value is None:
        return False
    value = value.lower().strip()
    if value in ["true", "yes", "on", "1"]:
        return True
    if value in ["false", "no", "off", "0"]:
        return False
    raise Exception(f"ERROR: not a bool string: '{value}'")


def split_address_and_group(peer: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if peer is None:
        return (None, None)
    group = None
    i = peer.find("/")
    if i == 0:
        group = peer
        peer = ""
    if i > 0:
        group = peer[i:]  # will have prefix "/"
        peer = peer[:i]
    peer = peer.strip()
    return (peer, group)


def first_non_blank_line(s: Optional[str]) -> Optional[str]:
    """
    Returns the first non-blank line from a multi-line string.

    A blank line is considered as one that contains only whitespace characters.
    If the input is None or all lines are blank, the function returns None.

    Parameters:
    s (Optional[str]): The input multi-line string, or None.

    Returns:
    Optional[str]: The first non-blank line, or None if no such line exists or the input is None.
    """
    if s is None:
        return None
    return next((line for line in s.splitlines() if line.strip()), None)


# modified from bing chat answer
def get_object_at_key_path(obj, key_path: Union[str, list]):
    if isinstance(key_path, str):
        key_path = key_path.split(".")
        # courtesy of chatgpt 4o:
        # Convert strings that are valid integers to integers for list indexing
        key_path = [int(k) if k.isdigit() else k for k in key_path]
    try:
        return reduce(operator.getitem, key_path, obj)
    except (KeyError, IndexError, TypeError):
        return None


# modified from bing chat answer
# TODO: sparse changes in list items
def diff_dicts(dict1: dict, dict2: dict) -> dict:
    diff = {}
    for key in dict1:
        if isinstance(dict1[key], dict) and isinstance(dict2.get(key), dict):
            nested_diff = diff_dicts(dict1[key], dict2[key])
            if nested_diff:
                diff[key] = nested_diff
        elif isinstance(dict1[key], list) and isinstance(dict2.get(key), list):
            if dict1[key] != dict2[key]:
                diff[key] = dict2[key]
        elif dict1[key] != dict2.get(key):
            diff[key] = dict2.get(key)
    for key in dict2:
        if key not in dict1:
            diff[key] = dict2[key]
    return diff


# FIXME: hacky
def func_module_docstring(func: Callable) -> str:
    if not callable(func):
        return ""
    mod = importlib.import_module(func.__module__)
    return mod.__doc__ or ""


def uri_and_group_for_peer(peer: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    # assume 'valid' single host:port[/group] as returned by validate.address(peer, single=True)
    # try to return a resolved host:port[/group]
    # host should be left as-is if unresolvable; it might be later on reconnect attempt
    if peer in [None, ""]:  # should never happen
        return (None, None)  # this should be the only way None is returned

    peer, group = split_address_and_group(peer)

    u = urlparse("ws://" + peer)
    host = u.hostname
    port = u.port or 7396
    if host:
        host = host.strip()
    if host in [None, "", ".", "localhost", "localhost.", "127.0.0.1"]:
        host = "127.0.0.1"
    else:
        # try to munge a resolvable host name
        # remote in vmware is on another subnet; need host.local resolved to ipv4 addr
        ext = ""
        if host.endswith("."):
            host = host[:-1]
        if host.endswith(".local"):
            ext = ".local"
            host = host[:-6]
        if "." not in host:
            # only attempt to resolve a single-segment host name
            try:
                socket.gethostbyname(host)  # this fails quickly when it does
            except socket.gaierror:
                # cannot resolve, try again with '.local', if so use ipv4 addr
                # this will be slow if host.local does not exist
                # note: we do not catch exception
                # may cause lufah to always use ipv4 running on Windows w 'host.local'
                try:
                    host = socket.gethostbyname(host + ".local")
                except socket.gaierror:
                    logger.error(
                        "Unable to resolve %s or %s", repr(host), repr(host + ".local")
                    )
                    # proceed with unresolved host
                    host += ext  # add .local if it had it

    uri = f"ws://{host}:{port}/api/websocket"

    # validate and munge group, possibly modify uri for 8.1
    # for v8.3, allow "//" prefix, spaces, special chars
    # group None is all groups
    # '/'  will be '' (default group)
    # '//' will be '/'
    # '//.*' will be '/.*'
    # 8.1 group name '/.*' requires using '//.*'
    if group and group.startswith("/"):
        group = group[1:]  # strip "/"; can now be ''

    # TODO: drop 8.1 support
    if group and re.match(r"^\/?[\w.-]*$", group):
        # might be connecting to fah 8.1, so append /group
        if not group.startswith("/"):
            uri += "/"
        uri += group

    return (uri, group)


def munged_group_name(group: Optional[str], snapshot: Optional[dict]) -> Optional[str]:
    # TODO: drop 8.1 support and require // if group begins / to remove ambiguity
    # return group name that exists, None, or raise
    # assume v8.3; old group names may persist from upgrade
    # NOTE: must have connected to have snapshot
    # group may be None
    # expect always having first leading '/' removed from cli argument
    # expect user specified '//name' for actual '/name' (already stripped)
    if group is None:
        return None  # no group specified; this is common
    if snapshot is None:
        raise Exception(f"Unable to look for group '{group}'. No client data.")
    # get array of actual group names else []
    groups = list(snapshot.get("groups", {}).keys())
    if not groups:
        # for 8.1
        peers = snapshot.get("peers", [])
        groups = [s for s in peers if s.startswith("/")]
    if len(group):  # don't conflate '' with '/'; both can legit exist
        # check 'groupname' and '/groupname'
        # if both exist, throw
        # '' is always the default group and not checked here
        group0 = "/" + group
        if group0 in groups and group in groups:
            raise Exception(
                f"Ambiguous group name. Both '{group}' and '{group0}' exist."
            )
        if group0 in groups and group not in groups:
            group = group0
    if group not in groups:
        raise FahClientGroupDoesNotExist(f"Group '{group}' is not in groups {groups}")
    return group


def natural_delta_from_seconds(secs: int) -> str:
    """Human-readable time interval"""
    secs = int(secs)  # it may not be int
    if secs < 0:
        return "-(" + natural_delta_from_seconds(-secs) + ")"
    if secs < 60:
        return f"{secs:02d}s"
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    # return f'{d}:{h:02d}:{m:02d}:{s:02d}'
    if h == 0:
        return f"{m:02d}m {s:02d}s"
    if d == 0:
        return f"{h}h {m:02d}m"
    return f"{d}d {h}h"


def fetch_json(url: str):
    data = None
    with urlopen(url) as response:
        if response.getcode() == 200:
            data = json.loads(response.read().decode("utf-8"))
    return data


def fetch_causes():
    return fetch_json("https://api.foldingathome.org/project/cause")


def shorten_natural_delta(eta: str) -> str:
    eta = eta.replace(" days", "d").replace(" day", "d")
    eta = eta.replace(" hours", "h").replace(" hour", "h")
    eta = eta.replace(" mins", "m").replace(" min", "m")
    eta = eta.replace(" secs", "s").replace(" sec", "s")
    return eta
