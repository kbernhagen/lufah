"""FahClient class"""

import asyncio
import datetime
import json
import logging
from urllib.parse import urlparse

import websockets
import websockets.asyncio.client
import websockets.protocol
from websockets.exceptions import ConnectionClosed

from lufah import validate as valid
from lufah.const import (
    COMMAND_FINISH,
    COMMAND_FOLD,
    COMMAND_PAUSE,
)
from lufah.exceptions import FahClientUnknownCommand
from lufah.logger import logger
from lufah.updatable import Updatable
from lufah.util import (
    ipv4_uri_for_uri,
    munged_group_name,
    uri_and_group_for_peer,
)


class FahClient:
    """Class to manage a remote client connection"""

    def __init__(self, peer, name=None, should_process_updates=True):
        peer = valid.address(peer, single=True)
        self._name = None
        self.ws = None
        self._connection_state = ""
        self.data = Updatable()  # client state
        self._version = (0, 0, 0)  # data.info.version as tuple after connect
        self._callbacks = []  # message callbacks
        self._should_process_updates = should_process_updates
        # peer is a pseuso-uri that needs munging
        # NOTE: this may raise
        self._uri, self._group = uri_and_group_for_peer(peer)
        self._connected_uri = None
        u = urlparse(self._uri)
        self._name = name or u.netloc or peer
        logger.debug('Created FahClient("%s")', self._name)

    @property
    def name(self):
        return self._name

    @property
    def uri(self):
        return self._uri

    @property
    def group(self):
        return self._group

    @property
    def is_connected(self):
        return self.ws is not None and self.ws.state == websockets.protocol.State.OPEN

    @property
    def version(self):
        return self._version

    @property
    def groups(self):
        groups = list(self.data.get("groups", {}).keys())
        if not groups and self._version < (8, 2):
            peers = self.data.get("peers", [])
            groups = [s for s in peers if s.startswith("/")]
        return groups

    @property
    def machine_name(self):
        info = self.data.get("info", {})
        return info.get("mach_name", info.get("hostname", self.name))

    @property
    def state(self):
        "Human-readable connection state"
        return self._connection_state

    def register_callback(self, callback):
        self._callbacks.append(callback)

    def unregister_callback(self, callback):
        self._callbacks.remove(callback)

    async def _process_message(self, message):
        try:
            data = json.loads(message)
        except Exception as e:
            logger.error(
                "%s:_process_message():unable to convert message to json:%s:%s",
                self._name,
                e,
                message,
            )
            return
        try:
            if self._should_process_updates and isinstance(data, (list, str)):
                self.data.do_update(data)
        except Exception as e:
            logger.error("%s:Updatable.do_update() exception:%s", self._name, type(e))
        for callback in self._callbacks:
            try:
                await callback(self, data)
            except Exception as e:
                logger.error(
                    "%s:_process_message() ignoring callback exception:%s:%s",
                    self._name,
                    e,
                    callback,
                )

    async def _receive_messages(self):
        while True:
            try:
                message = await self.ws.recv()
                await self._process_message(message)
            except ConnectionClosed:
                logger.info("%s:Connection closed.", self._name)
                await self.close()
                break
            except (KeyboardInterrupt, asyncio.CancelledError):
                await self.close()
                raise  # MUST re-raise asyncio.CancelledError
            except Exception as e:
                logger.debug("%s:Ignoring unexpected exception: %s", self._name, e)

    async def connect(self):
        if self.is_connected:
            return
        if self._uri is None:
            logger.error("%s:connect(): uri is None", self._name)
            return
        if not self.ws:
            logger.info("%s:Opening %s", self._name, self._uri)
            self._connection_state = "Connecting.."  # Resolving
            uri = await ipv4_uri_for_uri(self._uri)
            self._connected_uri = None
            try:
                self._connection_state = "Connecting..."
                self.ws = await websockets.asyncio.client.connect(
                    uri,
                    ping_interval=None,  # client will ping us, and may not pong
                    max_size=16777216,  # first log message can be huge
                )
                self._connected_uri = uri
                self._connection_state = "Connected"
                logger.info("%s:Connected to %s", self._name, uri)
            except (KeyboardInterrupt, asyncio.CancelledError):
                self.data = Updatable()
                self._version = (0, 0, 0)
                self._connection_state = "Disconnected"
                logger.warning("%s:connect cancelled to %s", self._name, uri)
                raise
            except Exception as e:
                self.data = Updatable()
                self._version = (0, 0, 0)
                if isinstance(e, (OSError, asyncio.TimeoutError)):
                    self._connection_state = "Unreachable"
                elif isinstance(e, websockets.exceptions.InvalidURI):
                    self._connection_state = "Invalid address"
                else:
                    self._connection_state = type(e)  # "Disconnected"
                logger.warning("%s:Failed to connect to %s", self._name, uri)
                return
        r = await self.ws.recv()
        snapshot = json.loads(r)
        v = snapshot.get("info", {}).get("version", "0")
        self._version = tuple(map(int, v.split(".")))
        old = self._version < (8, 3)
        self.data = Updatable(snapshot, compat_mode=old)
        if old:
            logger.warning(
                "Client v%s. Support for clients older than 8.3 is deprecated.", v
            )
        asyncio.ensure_future(self._receive_messages())

    async def close(self):
        if self.ws is not None:
            self._connection_state = "Disconnecting"
            await self.ws.close()
            self._connected_uri = None
        self._connection_state = "Disconnected"

    async def send(self, message):
        if not self.is_connected:
            logger.warning("%s:send(): websocket is not open", self._name)
            return
        msgstr = None
        if isinstance(message, dict):
            msg = message
            if "time" not in msg:
                msg = message.copy()
                now = datetime.datetime.now(datetime.timezone.utc)
                t = now.replace(microsecond=0).isoformat()
                msg["time"] = t.replace("+00:00", "Z")
            msgstr = json.dumps(msg)
        elif isinstance(message, str):
            msgstr = message
        elif isinstance(message, list):
            # currently, would be invalid
            msgstr = json.dumps(message)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("%s:WOULD BE sending: %s", self._name, msgstr)
            return
        if msgstr:
            logger.info("%s:sending: %s", self._name, msgstr)
            try:
                await self.ws.send(msgstr)
            except ConnectionClosed:
                await self.close()
                raise

    async def send_command(self, cmd, **kwargs):
        if cmd not in [COMMAND_FOLD, COMMAND_FINISH, COMMAND_PAUSE]:
            raise FahClientUnknownCommand(f'Unknown client command: "{cmd}"')
        if self.version < (8, 3):
            if cmd == "fold":
                cmd = "unpause"
            msg = {"cmd": cmd}
        else:
            msg = {"state": cmd, "cmd": "state"}
            group = kwargs.get("group", self.group)
            # NOTE: group would be created if it doesn't exist
            if group is not None:
                group = munged_group_name(group, self.data)
                if group is None:
                    return  # should not reach
                msg["group"] = group
        await self.send(msg)

    # async def send_config(self, config, **kwargs):
    # default_group=self.group
    # force=False
    # def get_config_value(self, key, **kwargs):

    async def create_group(self, group):
        if self.version < (8, 3, 1):
            raise Exception("Error: create group requires client 8.3.1+")
        if group is None:
            raise Exception("Error: no group specified")
        # strip leading/trailing whitespace, as web control does
        group = group.strip()
        if group in self.groups:
            logger.warning('%s: group "%s" already exists', self._name, group)
            return
        # use side-effect that setting state on non-existant group creates it
        # FIXME: might break in future
        await self.send({"state": "pause", "cmd": "state", "group": group})

    async def dump_unit(self, unit):
        if unit is None:
            logger.error("%s: unit to dump is None", self._name)
            return
        if isinstance(unit, str):
            unit_id = unit
        else:
            unit_id = unit.get("id")
        if unit_id:
            await self.send({"cmd": "dump", "unit": unit_id})
        else:
            logger.error("%s: unit to dump has no id", self._name)

    def paused_units_in_group(self, group):
        units = []
        for unit in self.data.get("units", []):
            if not unit.get("pause_reason"):
                continue
            if group is not None and group != unit.get("group"):
                continue
            units.append(unit)
        return units
