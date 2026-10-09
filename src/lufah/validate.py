"""CLI argument validate functions"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from lufah.const import KNOWN_CAUSES
from lufah.util import split_address_and_group

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 7396
_DEFAULT_HOST_PORT = f"{_DEFAULT_HOST}:{_DEFAULT_PORT}"


def account_token(value: str | None) -> str | None:
    """Account token must be 43 url base64 characters."""
    if value is None:
        return value
    # token is URL base64 encoding of 32 bytes, no padding '='
    if not value or not re.match(r"^[a-zA-Z0-9_\-]{43}$", value):
        raise ValueError(f"Error: {account_token.__doc__}")
    return value


def address(peer: str | None, single=False) -> str:
    """\
    [host][:port][/group] or [host][:port],[host][:port]...
    Use "." for localhost.
    Group name must not be url-encoded, but may need escaping from shell.
    The first "/" separates the group and is not part of its name.
    "/" alone is the default group. For a group whose name begins with "/",
    use "//": host//name is the group "/name". Group names are exact matches.
    Can be a comma-separated list of hosts for commands
    units, info, fold, pause, finish, top.
    A group name cannot be used with multiple hosts.
    IPv6 is not supported by the client.
    """
    if peer is None:
        return _DEFAULT_HOST_PORT
    # separate "/group" from peer(s)
    peer, group = split_address_and_group(peer)
    # validate group name; for now that means printable chars (and space)
    if group and not group.isprintable():
        raise ValueError("Invalid group name with non-printable characters")

    if peer in ["", ".", _DEFAULT_HOST, _DEFAULT_HOST_PORT]:
        return _DEFAULT_HOST_PORT + (group or "")
    is_multi = "," in peer  # multple hosts
    if not is_multi:
        if peer.startswith(":"):
            peer = _DEFAULT_HOST + peer
        u = urlparse("ws://" + peer)
        host = u.hostname
        if host in [None, "", "."]:
            host = _DEFAULT_HOST
        port = u.port or _DEFAULT_PORT
        # TODO: validate host is hostname or IPv4, validate port is 1..maxport
        host = host.removesuffix(".")
        if host != _DEFAULT_HOST and "." not in host:
            host += ".local"  # generally needed, but this may be an error
        peer = f"{host}:{port}"
        if group:
            peer += group
    else:
        if single:
            raise ValueError("Error: Cannot have multiple hosts")
        if group:
            raise ValueError("Error: Cannot have multiple hosts with any group")
        # split on comma and validate each single-host address, then join, unique
        # ignore empty strings; keep first-seen order (dict as ordered set)
        addresses = {}
        for p in peer.split(","):
            if p:
                addresses[address(p, single=True)] = None
        peer = ",".join(addresses)
    return peer


def cause(value: str | None) -> str | None:
    """Set cause preference."""
    if value is None:
        return None
    if value == "":
        return "any"
    value = value.strip().lower()
    if value not in KNOWN_CAUSES:
        raise ValueError(f"Error: cause must be one of: {' '.join(KNOWN_CAUSES)}")
    return value


def cpus(value: str | None) -> int | None:
    """
    Set number of cpus to allocate to resource group.

    A group must be specified via -a option if there is more than one group.
    """
    if value is None:
        return None
    value = int(value)
    if value not in range(256):
        raise ValueError("Error: cpus must be 0 to 256")
    return value


def checkpoint(value: str | None) -> int | None:
    """Set requested CPU WU checkpoint frequency in minutes."""
    if value is None:
        return None
    if value == "":
        return 15
    value = int(value)
    if value not in range(3, 30):
        raise ValueError("Error: checkpoint must be 3 to 30")
    return value


def key(value: str | None) -> int | None:
    """Set project key for internal beta testing of new projects."""
    if value is None:
        return None
    if value == "":
        return 0
    value = int(value, 0)
    if value not in range(0xFFFFFFFFFFFFFFFF):
        raise ValueError("Error: key must be 0 to 0xFFFFFFFFFFFFFFFF (in decimal)")
    return value


def machine_name(value: str | None) -> str | None:
    """
    machine-name is used to identify the machine.
    Must be between 1 and 64 characters and cannot include any of \\<>;&'"
    or whitespace.
    """
    if value is None:
        return value
    value = value.strip()
    if not value or not re.match(r"^[^\s\\<>;&'\"]{1,64}$", value):
        raise ValueError(f"Error: {machine_name.__doc__}")
    return value


def passkey(value: str | None) -> str | None:
    """
    Set passkey token for quick return bonus points.

    Passkey must be "" or 30-32 hexadecimal characters.
    New passkeys are 32 characters. Do not make it up.
    Get your passkey at https://apps.foldingathome.org/getpasskey
    """
    if value is None:
        return None
    value = value.strip().lower()
    if value and not re.match(r"^[0-9a-f]{30,32}$", value):
        raise ValueError(f"Error: {passkey.__doc__}")
    return value


def priority(value: str | None) -> str | None:
    """
    Set preferred core task priority.

    This never worked because cores set their own priority.
    """
    if value is None:
        return None
    if value == "":
        return "idle"
    value = value.strip().lower()
    known_values = ["idle", "low", "normal", "inherit"]
    if value not in known_values:
        raise ValueError(f"Error: priority must be one of: {' '.join(known_values)}")
    return value


def team(value: str | None) -> int | None:
    """Set team number. Team must already exist."""
    if value is None:
        return None
    value = int(value, 0)
    if value not in range(0x7FFFFFFF):
        raise ValueError("Error: team number must be 0 to 0x7FFFFFFF (in decimal)")
    return value


def user(value: str | None, force: bool = False) -> str | None:
    """
    Set folding user name, "" or 2 to 100 bytes.

    Leading/trailing whitespace will be trimmed.
    If you are using unusual chars, please use Web Control.
    User name cannot contain any of the following: <>;&: or tab.
    Use --force to allow legacy characters for an existing old name.
    The empty string "" will become "Anonymous".
    """
    if value is None:
        return None
    if value == "":
        return "Anonymous"
    value = value.strip()
    n = len(value.encode("utf-8"))
    if not 2 <= n <= 100:
        raise ValueError("Error: user name must be empty or between 2 and 100 bytes")
    if force and not re.match(r"^[^\t\n\r]{2,100}$", value):
        raise ValueError("Error: user name cannot contain tab")
    if not force and not re.match(r"^[^<>;&:\t\n\r]{2,100}$", value):
        raise ValueError(
            "Error: user name cannot contain any of the following: <>;&: or tab"
            + "\nUse --force to allow legacy characters"
        )
    return value
