"""CLI argument validate functions"""

import re
from typing import Optional
from urllib.parse import urlparse

from lufah.const import KNOWN_CAUSES
from lufah.util import split_address_and_group

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 7396
_DEFAULT_HOST_PORT = f"{_DEFAULT_HOST}:{_DEFAULT_PORT}"


def account_token(value: Optional[str]) -> Optional[str]:
    """Account token must be 43 url base64 characters."""
    if value is None:
        return value
    # token is URL base64 encoding of 32 bytes, no padding '='
    if not value or not re.match(r"^[a-zA-Z0-9_\-]{43}$", value):
        raise Exception(f"Error: {account_token.__doc__}")
    return value


def address(peer: Optional[str], single=False) -> str:
    """\
    [host][:port][/group] or [host][:port],[host][:port]...
    Use "." for localhost.
    Group name must not be url-encoded, but may need escaping from shell.
    Can be a comma-separated list of hosts for commands
    units, info, fold, finish, pause
    """
    if peer is None:
        return _DEFAULT_HOST_PORT
    # separate "/group" from peer(s)
    peer, group = split_address_and_group(peer)

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
        if host.endswith("."):
            host = host[:-1]
        if host != _DEFAULT_HOST and "." not in host:
            host += ".local"  # generally needed, but this may be an error
        peer = f"{host}:{port}"
        if group:
            peer += group
    else:
        if single:
            raise Exception("Error: Cannot have multiple hosts")
        if group:
            raise Exception("Error: Cannot have multiple hosts with any group")
        # split on comma and validate each single-host address, then join, unique
        addresses = set()
        for p in peer.split(","):
            p = address(p, single=True)
            addresses.add(p)
        peer = ",".join(addresses)
    return peer


def cause(value: Optional[str]) -> Optional[str]:
    """Set cause preference."""
    if value is None:
        return None
    if value == "":
        return "any"
    value = value.strip().lower()
    if value not in KNOWN_CAUSES:
        raise Exception(f"Error: cause must be one of: {' '.join(KNOWN_CAUSES)}")
    return value


def cpus(value: Optional[str]) -> Optional[int]:
    """
    Set number of cpus to allocate to resource group.

    A group must be specified via -a option if there is more than one group.
    """
    if value is None:
        return None
    value = int(value)
    if value not in range(0, 256):
        raise Exception("Error: cpus must be 0 to 256")
    return value


def checkpoint(value: Optional[str]) -> Optional[int]:
    """Set requested CPU WU checkpoint frequency in minutes."""
    if value is None:
        return None
    if value == "":
        return 15
    value = int(value)
    if value not in range(3, 30):
        raise Exception("Error: checkpoint must be 3 to 30")
    return value


def key(value: Optional[str]) -> Optional[int]:
    """Set project key for internal beta testing of new projects."""
    if value is None:
        return None
    if value == "":
        return 0
    value = int(value, 0)
    if value not in range(0, 0xFFFFFFFFFFFFFFFF):
        raise Exception("Error: key must be 0 to 0xFFFFFFFFFFFFFFFF (in decimal)")
    return value


def machine_name(value: Optional[str]) -> Optional[str]:
    """
    machine-name is used to identify the machine.
    Must be between 1 and 64 characters and cannot include any of \\<>;&'"
    or whitespace.
    """
    if value is None:
        return value
    value = value.strip()
    if not value or not re.match(r"^[^\s\\<>;&'\"]{1,64}$", value):
        raise Exception(f"Error: {machine_name.__doc__}")
    return value


def passkey(value: Optional[str]) -> Optional[str]:
    """
    Set passkey token for quick return bonus points.

    Passkey must be "" or 32 hexadecimal characters.
    """
    if value is None:
        return None
    value = value.strip().lower()
    if value and not re.match(r"^[0-9a-f]{32}$", value):
        raise Exception(passkey.__doc__)
    return value


def priority(value: Optional[str]) -> Optional[str]:
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
        raise Exception(f"Error: priority must be one of: {' '.join(known_values)}")
    return value


def team(value: Optional[str]) -> Optional[int]:
    """Set team number. Team must already exist."""
    if value is None:
        return None
    value = int(value, 0)
    if value not in range(0, 0x7FFFFFFF):
        raise Exception("Error: team number must be 0 to 0x7FFFFFFF (in decimal)")
    return value


def user(value: Optional[str]) -> Optional[str]:
    """
    Set folding user name, up to 100 bytes.

    Leading/trailing whitespace will be trimmed.
    If you are using unusual chars, please use Web Control.
    """
    if value is None:
        return None
    if value == "":
        return "Anonymous"
    value = value.strip()
    if len(value.encode("utf-8")) > 100:
        raise Exception("Error: Max user length is 100 bytes")
    if not re.match(r"^[^\t\n\r]{1,100}$", value):
        raise Exception("Error: unexpected white space characters")
    return value
