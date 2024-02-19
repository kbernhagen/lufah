"""FahClient class"""
# -*- coding: utf-8 -*-
# pylint: disable=fixme,missing-function-docstring
# pylint: disable=broad-exception-raised,broad-exception-caught,bare-except
# pylint: disable=too-many-branches,too-many-statements,too-many-lines
# pylint: disable=too-many-instance-attributes,wildcard-import,chained-comparison
# pylint: disable=chained-comparison

import asyncio
import logging
import json
import datetime

from websockets import connect # pip3 install websockets --user
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from .const import * # pylint: disable=unused-wildcard-import
from .exceptions import * # pylint: disable=unused-wildcard-import
from .util import (
  uri_and_group_for_peer,
  munged_group_name,
  get_object_at_key_path
  )

_LOGGER = logging.getLogger(__name__)


class FahClient:
  """Class to manage a remote client connection"""

  def __init__(self, peer, name=None):
    if name is None:
      name = peer
    self._name = None
    self._group = None
    self.ws = None
    self.data = {} # snapshot
    self._version = (0,0,0) # data.info.version as tuple after connect
    self._callbacks = [] # message callbacks
    self.should_process_updates = False
    # peer is a pseuso-uri that needs munging
    # NOTE: this may raise
    self._uri, self._group = uri_and_group_for_peer(peer)
    self._name = name if name else self._uri
    _LOGGER.debug('Created FahClient("%s")', self._name)

  @property
  def name(self):
    return self._name

  @property
  def group(self):
    return self._group

  @property
  def is_connected(self):
    return self.ws is not None and self.ws.open

  @property
  def version(self):
    return self._version

  @property
  def groups(self):
    groups = list(self.data.get('groups', {}).keys())
    if not groups and self._version < (8,2):
      peers = self.data.get('peers', [])
      groups = [s for s in peers if s.startswith("/")]
    return groups

  def register_callback(self, callback):
    self._callbacks.append(callback)

  def unregister_callback(self, callback):
    self._callbacks.remove(callback)

  async def process_message(self, message):
    try:
      data = json.loads(message)
    except Exception as e:
      _LOGGER.error(
        '%s:_update():unable to convert message to json:%s',
        self._name, type(e))
      return
    try:
      self._update(data)
    except Exception as e:
      _LOGGER.error('%s:_update():%s', self._name, type(e))
    for callback in self._callbacks:
      asyncio.ensure_future(callback(self, data))

  async def receive(self):
    while True:
      try:
        message = await self.ws.recv()
        await self.process_message(message)
      except (ConnectionClosed, ConnectionClosedError):
        _LOGGER.info('%s:Connection closed: %s', self._name, self._uri)
        break

  async def connect(self):
    if self.is_connected:
      return
    if self._uri is None:
      _LOGGER.error('%s:connect(): uri is None', self._name)
      return
    if not self.ws:
      _LOGGER.info('%s:Opening %s', self._name, self._uri)
      try:
        self.ws = await connect(self._uri, ping_interval=None)
        _LOGGER.info('%s:Connected to %s', self._name, self._uri)
      except Exception:
        self.data = {}
        self._version = (0,0,0)
        _LOGGER.warning('%s:Failed to connect to %s', self._name, self._uri)
        return
    r = await self.ws.recv()
    snapshot = json.loads(r)
    v = snapshot.get("info", {}).get("version", "0")
    self._version = tuple(map(int, v.split('.')))
    self.data.update(snapshot)
    asyncio.ensure_future(self.receive())

  async def close(self):
    if self.ws is not None:
      await self.ws.close()


  def _update(self, data): # data: json array or dict or string
    if not self.should_process_updates:
      return
    if isinstance(data, list):
      # last list element is value, prior elements are a key path
      # if value is None, delete destination
      if len(data) < 2:
        return
      value = data[len(data) - 1]

      x = get_object_at_key_path(self.data, data[:-2])
      # expect x is None, dict, or list
      if x is None:
        return
      key = data[len(data)-2] # final key

      if isinstance(x, list) and isinstance(key, int):
        if key == -1:
          # append value to dest list x
          if not value is None:
            x.append(value)

        if key == -2:
          # append values to dest list x
          if not value is None:
            for v in value:
              x.append(v)

        if 0 <= key and key < len(x):
          if value is None:
            del x[key]
          else:
            x[key] = value

        if len(x) <= key and not value is None:
          x.append(value)

        return

      if isinstance(x, dict) and isinstance(key, str):
        if value is None:
          del x[key]
        else:
          x[key] = value # is this ever merge?
        return

    elif isinstance(data, dict):
      # currently, this should not happen
      # FIXME: maybe use deepmerge module
      #self.data.update(data)
      pass
    # else ignore "ping"


  async def send(self, message):
    if not self.is_connected:
      _LOGGER.warning('%s:send(): websocket is not open', self._name)
      return
    msgstr = None
    if isinstance(message, dict):
      msg = message
      if not 'time' in msg:
        msg = message.copy()
        t = datetime.datetime.utcnow().isoformat() + 'Z'
        msg['time'] = t
      msgstr = json.dumps(msg)
    elif isinstance(message, str):
      msgstr = message
    elif isinstance(message, list):
      # currently, would be invalid
      msgstr = json.dumps(message)
    if _LOGGER.isEnabledFor(logging.DEBUG):
      _LOGGER.debug('%s:WOULD BE sending: %s', self._name, msgstr)
      return
    if msgstr:
      _LOGGER.info('%s:sending: %s', self._name, msgstr)
      await self.ws.send(msgstr)

  async def send_command(self, cmd):
    if not cmd in [COMMAND_FOLD, COMMAND_FINISH, COMMAND_PAUSE]:
      raise FahClientUnknownCommand(f'Unknown client command: "{cmd}"')
    if self.version < (8,3):
      if cmd == 'fold':
        cmd = 'unpause'
      msg = {"cmd": cmd}
    else:
      msg = {"state": cmd, "cmd": "state"}
      # NOTE: group would be created if it doesn't exist
      if self.group is not None:
        group = munged_group_name(self.group, self.data)
        if group is None:
          return
        msg["group"] = group
    await self.send(msg)

  #async def send_config(self, config, **kwargs):
    # default_group=self.group
    # force=False
  #def get_config_value(self, key, **kwargs):
