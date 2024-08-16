"""lufah utility functions"""

import logging
import operator
import re
import socket
import sys
from functools import reduce
from urllib.parse import urlparse

_LOGGER = logging.getLogger(__name__)


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def bool_from_string(value):
    if value.lower() in ["true", "yes", "on", "1"]:
        return True
    if value.lower() in ["false", "no", "off", "0"]:
        return False
    raise Exception(f"ERROR: not a bool string: {value}")


# modified from bing chat answer
def get_object_at_key_path(obj, key_path):
    if isinstance(key_path, str):
        key_path = key_path.split(".")
    try:
        return reduce(operator.getitem, key_path, obj)
    except (KeyError, IndexError, TypeError):
        return None


# modified from bing chat answer
# TODO: sparse chenges in list items
def diff_dicts(dict1, dict2):
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


def uri_and_group_for_peer(peer):
    # do not strip right; 8.3 group names might not be stripped
    # create-group should strip what is specified, as web control does
    if peer:
        peer = peer.lstrip()
    if peer in [None, ""]:
        return (None, None)

    uri = peer
    if peer.startswith(":"):
        uri = "ws://." + peer
    elif peer.startswith("/"):
        uri = "ws://." + peer

    scheme = urlparse(uri).scheme

    if scheme == "":
        uri = "ws://" + peer
    elif scheme not in ["ws", "wss", "http", "https", "file"]:
        # assume misparse of 'host:port'
        uri = "ws://" + peer

    u = urlparse(uri)

    if u.scheme not in ["ws", "wss"]:
        _LOGGER.error("Scheme %s is not supported for peer %s", u.scheme, repr(peer))
        return (None, None)

    userpass = ""
    user = u.username
    password = u.password
    if user and password:
        userpass = f"{user}:{password}@"

    host = u.hostname  # can be None
    if host:
        host = host.strip()
    if host in [None, "", ".", "localhost", "localhost."]:
        host = "127.0.0.1"
    else:
        # TODO: validate host regex; maybe disallow numeric IPv6 addresses
        # try to munge a resolvable host name
        # remote in vm is on another subnet; need host.local resolved to ipv4
        if host.endswith("."):
            host = host[:-1]
        if host.endswith(".local"):
            host = host[:-6]
        if "." not in host:
            try:
                socket.gethostbyname(host)
            except socket.gaierror:
                # cannot resolve, try again with '.local', if so use ipv4 addr
                # this will be slow if host does not exist
                # note: we do not catch exception
                # may cause lufah to always use ipv4 running on Windows w 'host.local'
                try:
                    host = socket.gethostbyname(host + ".local")
                except socket.gaierror:
                    _LOGGER.error(
                        "Unable to resolve %s or %s", repr(host), repr(host + ".local")
                    )
                    return (None, None)

    port = u.port or 7396

    uri = f"{u.scheme}://{userpass}{host}:{port}/api/websocket"

    # validate and munge group, possibly modify uri for 8.1
    # for v8.3, allow "//" prefix, spaces, special chars
    # None or '' is no group (aka all groups)
    # '/'  will be '' (default group)
    # '//' will be '/'
    # '//*' will be '/*'
    # 8.1 group name '/' requires using '//'
    group = u.path
    if group in [None, ""]:
        group = None  # no group
    elif group == "/":
        group = ""  # default group
    elif group.startswith("/"):
        group = group[1:]  # strip "/"; can now be ''
    if group and re.match(r"^\/?[\w.-]*$", group):
        # might be connecting to fah 8.1, so append /group
        if not group.startswith("/"):
            uri += "/"
        uri += group

    return (uri, group)


def munged_group_name(group, snapshot):
    # return group name that exists, None, or raise
    # assume v8.3; old group names may persist from upgrade
    # NOTE: must have connected to have snapshot
    # group may be None
    # expect always having first leading '/' removed from cli argument
    # expect user specified '//name' for actual '/name' (already stripped)
    if group is None:
        return None  # no group specified
    if snapshot is None:
        _LOGGER.error("Snapshot is None")
        return None
    orig_group = group
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
            raise Exception(f'ERROR: both "{group}" and "{group0}" exist')
        if group0 in groups and group not in groups:
            group = group0
    if group not in groups:
        _LOGGER.error('Group "%s" is not in groups %s', group, groups)
        return None
    _LOGGER.debug("        groups: %s", groups)
    _LOGGER.debug("original group: %s", repr(orig_group))
    _LOGGER.debug("  munged group: %s", repr(group))
    return group


def format_seconds(secs: int):
    """Human-readable time interval"""
    secs = int(secs)  # it may not be int
    if secs < 0:
        return "-(" + format_seconds(-secs) + ")"
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
