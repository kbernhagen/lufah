"""FahClient class"""

import asyncio
import datetime
import json
import logging
import random
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
    """Class to manage a remote Folding@home client connection with auto-reconnect support."""

    def __init__(self, peer, name=None, should_process_updates=True, max_retries=None):
        """
        :param peer: Remote peer address
        :param name: Optional human-readable name
        :param should_process_updates: Whether to apply incoming updates to client state
        :param max_retries: Max reconnect attempts (default: None = unlimited)
        """
        peer = valid.address(peer, single=True)
        self._name = None
        self.ws = None
        self._connection_state = ""
        self.data = Updatable()  # client state
        self._version = (0, 0, 0)  # data.info.version as tuple after connect
        self._callbacks = []  # message callbacks
        self._should_process_updates = should_process_updates

        # peer is a pseuso-uri that needs munging
        self._uri, self._group = uri_and_group_for_peer(peer)
        self._connected_uri = None
        u = urlparse(self._uri)
        self._name = name or u.netloc or peer

        # Reconnect management
        self.reconnect_enabled = True
        self._reconnect_task = None
        self._base_delay = 5  # initial backoff in seconds
        self._max_delay = 10  # max backoff cap in seconds
        self._current_delay = self._base_delay
        self._max_retries = max_retries  # None = unlimited
        self._retry_count = 0

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
                "%s:_process_message(): unable to convert message to json: %s: %s",
                self._name,
                e,
                message,
            )
            return

        try:
            if self._should_process_updates and isinstance(data, (list, str)):
                self.data.do_update(data)
        except Exception as e:
            logger.error("%s: Updatable.do_update() exception: %s", self._name, type(e))
        await self._do_callbacks_with_data(data)

    async def _do_callbacks_with_data(self, data):
        for callback in self._callbacks:
            try:
                await callback(self, data)
            except Exception as e:
                logger.error(
                    "%s:_process_message() ignoring callback exception: %s: %s",
                    self._name,
                    e,
                    callback,
                )

    async def _did_change(self):
        """Notify of state change via callbacks with None"""
        # maybe use reactive properties?
        await self._do_callbacks_with_data(None)

    async def _receive_messages(self):
        """Background task: receive messages until closed, then trigger reconnect if allowed."""
        while self.is_connected:
            try:
                message = await asyncio.wait_for(self.ws.recv(), timeout=20)
                await self._process_message(message)
            except ConnectionClosed:
                logger.info("%s: Connection closed.", self._name)
                break
            except asyncio.CancelledError:  # pylint: disable=try-except-raise
                raise  # MUST re-raise
            except asyncio.TimeoutError:
                logger.info("%s: Connection recv timeout.", self._name)
                await self.close()
                break
            except Exception as e:
                logger.exception(
                    "%s: Unexpected exception in _receive_messages: %s", self._name, e
                )

        # If we end up here, the connection is closed
        await self._schedule_reconnect()

    async def _schedule_reconnect(self):
        """Schedule reconnect with exponential backoff + jitter if reconnect is enabled."""
        if not self.reconnect_enabled:
            logger.debug(
                "%s: Reconnect disabled, not scheduling reconnect.", self._name
            )
            return

        if self._max_retries is not None and self._retry_count >= self._max_retries:
            logger.error(
                "%s: Reached maximum retry limit (%d). Giving up.",
                self._name,
                self._max_retries,
            )
            return

        if self._reconnect_task and not self._reconnect_task.done():
            logger.debug("%s: Reconnect already scheduled.", self._name)
            return

        # Add jitter (±20%)
        jitter = random.uniform(0.8, 1.2)
        delay = min(self._current_delay * jitter, self._max_delay)
        self._retry_count += 1

        logger.info(
            "%s: Attempting reconnect #%d in %.1f seconds...",
            self._name,
            self._retry_count,
            delay,
        )
        self._reconnect_task = asyncio.create_task(self._delayed_reconnect(delay))

        # Increase backoff for next time, capped
        self._current_delay = min(self._current_delay * 2, self._max_delay)

    async def _delayed_reconnect(self, delay):
        try:
            await asyncio.sleep(delay)
            await self.connect()
        except asyncio.CancelledError:  # pylint: disable=try-except-raise
            raise
        except Exception as e:
            logger.warning("%s: Reconnect attempt failed: %s", self._name, e)
            await self._schedule_reconnect()  # keep retrying (if under limit)

    async def connect(self):
        if self.is_connected:
            return
        if self._uri is None:
            logger.error("%s: connect(): uri is None", self._name)
            return

        self._connection_state = "Connecting..."
        uri = await ipv4_uri_for_uri(self._uri)
        self._connected_uri = None
        try:
            self.ws = await websockets.asyncio.client.connect(
                uri,
                ping_interval=None,  # client will ping us, and may not pong
                max_size=16777216,  # first log message can be huge
            )
            self._connected_uri = uri
            self._connection_state = "Connected"
            logger.info("%s: Connected to %s", self._name, uri)

            # Reset retry/backoff after successful connection
            self._current_delay = self._base_delay
            self._retry_count = 0
        except asyncio.CancelledError:
            self._reset_state("Disconnected")
            logger.warning("%s: connect() cancelled", self._name)
            raise
        except Exception as e:
            self._reset_state(
                "Unreachable"
                if isinstance(e, (OSError, asyncio.TimeoutError))
                else "Disconnected"
            )
            logger.warning("%s: Failed to connect to %s: %s", self._name, uri, e)
            await self.close()
            await self._schedule_reconnect()
            return

        try:
            r = await self.ws.recv()
            snapshot = json.loads(r)
            v = snapshot.get("info", {}).get("version", "0")
            self._version = tuple(map(int, v.split(".")))
            old = self._version < (8, 3)
            self.data = Updatable(snapshot, compat_mode=old)
            if old:
                logger.warning("Client v%s. Support for <8.3 is deprecated.", v)
        except Exception as e:
            logger.error("%s: Failed to receive initial snapshot: %s", self._name, e)
            await self.close()
            await self._schedule_reconnect()
            return

        asyncio.create_task(self._receive_messages())

    async def close(self):
        """Close connection and disable auto-reconnect temporarily."""
        logger.debug("%s: Closing connection", self._name)
        recon_enabled = self.reconnect_enabled
        self.reconnect_enabled = False  # disable auto-reconnect temporarily

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None

        if self.ws is not None:
            self._connection_state = "Disconnecting"
            try:
                await self.ws.close()
            except Exception as e:
                logger.debug("%s: Exception while closing websocket: %s", self._name, e)
            finally:
                self.ws = None
                self._connected_uri = None

        self._reset_state("Disconnected")
        self.reconnect_enabled = recon_enabled  # restore for future use
        self._current_delay = self._base_delay  # reset backoff
        self._retry_count = 0

    def _reset_state(self, state):
        # self.data = Updatable()
        # self._version = (0, 0, 0)
        self._connection_state = state

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
        if kwargs.get("force") and cmd == "finish" and self.version >= (8, 4):
            await self._send_finish_force()
            # fall thru to also do standard finish for any other groups
            # (harmless to our targeted groups)
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

    async def _send_finish_force(self):
        # gather set of paused groups with units in RUN state
        target_groups = set()
        for unit in self.data.get("units", []):
            if unit.get("state") == "RUN":
                groupname = unit.get("group")
                if groupname is None:
                    continue
                # units can be migrated to "" if their group was deleted
                if groupname not in self.groups:
                    groupname = ""
                group = self.data.get("groups", {}).get(groupname, {})
                if group.get("config", {}).get("paused"):
                    target_groups.add(groupname)
        # create config with hack for each target group
        # but if a client group was specified, only hack that group
        all_groups_conf = {g: {} for g in self.groups}
        group = munged_group_name(self.group, self.data)
        if group is not None:
            if group in target_groups:
                # only group specified is a valid target
                target_groups = [group]
            else:
                # group specified is not a candidate
                target_groups = []
        # replace empty conf with hack conf for tageted groups
        for group in target_groups:
            if group in all_groups_conf:  # a little paranoia here
                all_groups_conf[group] = {"paused": False, "finish": True}
        if target_groups:
            await self.send({"cmd": "config", "config": {"groups": all_groups_conf}})
        else:
            logger.debug("no groups to force finish")

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

    async def delete_group(self, group):
        if self.version < (8, 3, 1):
            raise Exception("Error: delete group requires client 8.3.1+")
        if group is None:
            raise Exception("Error: no group specified")
        # strip leading/trailing whitespace, as web control does
        group = group.strip()
        if group == "":
            raise Exception("Error: default group cannot be deleted")
        if group not in self.groups:
            raise Exception(f'Error: group "{group}" does not exist')
        # TODO: require group is paused and has no units
        paused = (
            self.data.get("groups", {})
            .get(group, {})
            .get("config", {})
            .get("paused", False)
        )
        count = len(self.units_in_group(group))
        if not paused or count:
            m = f'Error: group "{group}" cannot be deleted'
            if not paused:
                m += "; group is not paused"
            if count:
                m += f"; group has {count} unit"
                if count != 1:
                    m += "s"
            raise Exception(m)
        # delete group by omitting it from groups config
        groups_conf = {g: {} for g in self.groups}
        del groups_conf[group]
        await self.send({"cmd": "config", "config": {"groups": groups_conf}})

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

    def units_in_group(self, group):
        # Note that this will not include orphaned units as belonging to "" group
        units = []
        if group is None:
            return units
        for unit in self.data.get("units", []):
            if group == unit.get("group"):
                units.append(unit)
        return units

    def paused_units_in_group(self, group):
        units = []
        for unit in self.data.get("units", []):
            if not unit.get("pause_reason"):
                continue
            if group is not None and group != unit.get("group"):
                continue
            units.append(unit)
        return units
