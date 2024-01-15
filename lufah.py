#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=fixme,missing-function-docstring
# pylint: disable=broad-exception-raised,broad-exception-caught,bare-except
# pylint: disable=too-many-branches,too-many-statements,too-many-lines
# pylint: disable=global-statement # this is for argparse OPTIONS
# pylint: disable=too-many-instance-attributes
# FIXME: this is excessive disabling

"""
lufah: Little Utility for FAH v8
"""

__version__ = '0.3.4'

__all__ = ['FahClient']

__license__   = 'MIT'
__copyright__ = 'Copyright (c) 2024 Kevin Bernhagen'
__url__       = 'https://github.com/kbernhagen/lufah'

import os
import sys
import json
import asyncio
import socket
import argparse
import re
import datetime
import errno
import math
import operator
from functools import reduce
from urllib.parse import urlparse
from urllib.request import urlopen
from subprocess import check_call

from websockets import connect # pip3 install websockets --user
from websockets.exceptions import ConnectionClosed

PROGRAM = os.path.basename(sys.argv[0])
if PROGRAM.endswith(".py"):
  PROGRAM = PROGRAM[:-3]

# TODO:
# lufah . create-group <name> # by sending pause to nonexistent group
# lufah . delete-group <name> # refuse if running WU, unless --force
# lufah file:~/peers.json units
#   { "peers": ["peer1", "peer2", ...] }


# FIXME: default is not restricted
# suggest only allow status, units, log, watch
DEFAULT_COMMAND = 'units'

HIDDEN_COMMANDS = ['x', 'fake'] # experimental stuff
NO_CLIENT_COMMANDS = ['start', 'stop', 'x']

# both as sent to client, and cli command
SIMPLE_CLIENT_COMMANDS = ['fold', 'finish', 'pause']

# TODO: multi peer support
MULTI_PEER_COMMANDS = ['units', 'info'] #, 'fold', 'finish', 'pause']

# allowed cli commands; all visible
COMMANDS = [
  'status',
  'units',
  'fold',
  'finish',
  'pause',
  'unpause',
  'config',
  'groups',
  'info',
  'log',
  'watch',
  'get',
]
if sys.platform == 'darwin':
  COMMANDS += ['start', 'stop']

COMMAND_ALIASES = {
  # alias : actual
  'unpause' : 'fold',
}

COMMANDS_HELP = {
  'status' : 'show json snapshot of client state',
  'pause'  : '',
  'fold'   : '',
  'finish' : '',
  'log'    : 'show log; use control-c to exit',
  'config' : 'get or set config values',
  'start'  : 'start local client service; peer must be "."',
  'stop'   : 'stop local client service; peer must be "."',
  'groups' : 'show json array of resource group names',
  'watch'  : 'show incoming messages; use control-c to exit',
  'units'  : 'show table of all units by group',
  'info'   : 'show peer host and client info',
  'get'    : 'show json value at dot-separated key path in client state',
}

# fah 8.3 config keys
# valid global/group keys are in json files:
# https://github.com/FoldingAtHome/fah-client-bastet/tree/master/src/resources
# note that these are the actual keys with underscore

# keys to settings possibly owned by account (if logged in)
# Joseph says it's safe to change these while logged in
# it is possible for a machine to differ from account
# web control will only show the account values when logged in
GLOBAL_CONFIG_KEYS = ['user', 'team', 'passkey', 'cause']

# keys to settings in groups under v8.3; in main config before 8.3
GROUP_CONFIG_KEYS = ['on_idle', 'beta', 'key', 'cpus',
  'on_battery', 'keep_awake']

# peers is v8.1.x only, but possibly remains as cruft
# gpus, paused, finish in main config before 8.3
READ_ONLY_GLOBAL_KEYS = ["peers", "gpus", "paused", "finish"]
# should never be changed externally for any fah version
READ_ONLY_GROUP_KEYS = ["gpus", "paused", "finish"]

READ_ONLY_CONFIG_KEYS = READ_ONLY_GLOBAL_KEYS + READ_ONLY_GROUP_KEYS
VALID_CONFIG_SET_KEYS = GLOBAL_CONFIG_KEYS + GROUP_CONFIG_KEYS
VALID_CONFIG_GET_KEYS = VALID_CONFIG_SET_KEYS + READ_ONLY_CONFIG_KEYS

# removed in 8.3
DEPRECATED_CONFIG_KEYS = ["fold_anon", "peers", "checkpoint", "priority"]

# From Web Control
# some of these are synthetic (not actual unit.state)
STATUS_STRINGS = {
  'ASSIGN':   'Requesting work',
  'DOWNLOAD': 'Downloading work',
  'CORE':     'Downloading core',
  'RUN':      'Running',
  'FINISH':   'Finishing',
  'UPLOAD':   'Uploading',
  'CLEAN':    'Cleaning up',
  'WAIT':     'Waiting',
  'PAUSE':    'Paused'
}


OPTIONS = argparse.Namespace()
_CLIENTS = {}


def eprint(*args, **kwargs):
  print(*args, file=sys.stderr, **kwargs)


def bool_from_string(value):
  if value.lower() in ['true', 'yes', 'on', '1']:
    return True
  if value.lower() in ['false', 'no', 'off', '0']:
    return False
  raise Exception(f'error: not a bool string: {value}')


def value_for_key_path(): # adict, kp):
  # kp: an array of keys or a dot-separated str of keys
  # like to handle int array indicies in str kp
  # ? import munch/addict/benedict
  return None


def get_object_at_key_path(obj, key_path):
  if isinstance(key_path, str):
    key_path = key_path.split('.')
  try:
    return reduce(operator.getitem, key_path, obj)
  except (KeyError, IndexError, TypeError):
    return None


# allowed config keys
VALID_KEYS_VALUES = {
  "fold-anon": {"type": bool_from_string},
  "user": {"default":'Anonymous', "type":str.strip, "re":r'^[^\t\n\r]{1,100}$',
    "help": 'If you are using unusual chars, please use Web Control.'},
  "team": {"default": 0, "type": int, "values": range(0, 0x7FFFFFFF)},
  "passkey": {"default": '', "type": str.lower, "re": r'^[0-9a-fA-F]{32}$',
    "help": 'passkey must be 32 hexadecimal characters'},
  "beta": {"type": bool_from_string},
  # https://api.foldingathome.org/project/cause
  "cause": {"default": 'any', "type": str.lower, "values": [
      "any", "alzheimers", "cancer", "huntingtons",
      "parkinsons", "influenza", "diabetes", "covid-19"]},
  "key": {"default": 0, "type": int, "values": range(0, 0xffffffffffffffff)},
  "on-idle": {"type": bool_from_string},
  "cpus": {"type": int, "values": range(0, 256)},
  "checkpoint": {"default": 15, "type": int, "values": range(3, 30)},
  "priority": {"default": 'idle', "type": str.lower,
    "values": ['idle', 'low', 'normal', 'inherit']},
  "on-battery": {"type": bool_from_string, "default": True},
  "keep-awake": {"type": bool_from_string, "default": True},
  # no peer editing; peers not supported by v8.2+
  # it would be an error to directly change gpus, paused, finish
  # get-only config keys
  "peers": {},
  "gpus": {},
  "paused": {},
  "finish": {},
}
# resource group r'^\/[\w.-]*$'
# user recommended ^[0-9a-zA-Z_]+$
# user not alleged reserved chars ^#|~ other disallowed \s
# user email


def _fetch_json(url):
  data = None
  # TODO: handle file:peers.json
  with urlopen(url) as response:
    if response.getcode() == 200:
      data = json.loads(response.read().decode('utf-8'))
  return data


def _fetch_causes(**_):
  data = _fetch_json('https://api.foldingathome.org/project/cause')
  if OPTIONS.verbose:
    print('causes:', json.dumps(data, indent=2))
  return data


def validate():
  if OPTIONS.debug:
    OPTIONS.verbose = True

  OPTIONS.peer = OPTIONS.peer.lstrip() # ONLY left strip
  if not OPTIONS.peer:
    raise Exception('error: no peer specified')
  # true validation of peer is done by _uri_and_group_for_peer()
  # TODO: accept file:~/peers.json containing {"peers":[".","host2","host3"]}
  #   set OPTIONS.peers; set OPTIONS.peer = None

  if OPTIONS.debug:
    print(f'   peer: {repr(OPTIONS.peer)}')
    print(f'command: {repr(OPTIONS.command)}')

  if OPTIONS.command in [None, '']:
    OPTIONS.command = DEFAULT_COMMAND
  else:
    OPTIONS.command = COMMAND_ALIASES.get(OPTIONS.command, OPTIONS.command)

  if OPTIONS.debug:
    print(f'command: {repr(OPTIONS.command)}')

  OPTIONS.peers = []
  if ',' in OPTIONS.peer and not '/' in OPTIONS.peer:
    # assume comma separated list of peers
    peers = OPTIONS.peer.split(',')
    for peer in peers:
      peer = peer.strip()
      if peer:
        OPTIONS.peers.append(peer)
    if OPTIONS.debug:
      print(f'  peers: {OPTIONS.peers!r}')
    OPTIONS.peer = None
  else:
    OPTIONS.peers = [OPTIONS.peer]

  if OPTIONS.peer and re.match(r'^[^/]*,.*/.*$', OPTIONS.peer):
    raise Exception('error: host cannot have a comma')

  if OPTIONS.peer is None and not OPTIONS.command in MULTI_PEER_COMMANDS:
    raise Exception(f'error: {OPTIONS.command!r} cannot use multiple peers')

  # validate config key value
  if OPTIONS.command in ['config']:
    key = OPTIONS.key
    value = OPTIONS.value
    keys = VALID_KEYS_VALUES.keys()
    info = VALID_KEYS_VALUES.get(key, {})
    values = info.get('values')
    regex = info.get('re')
    conv = info.get('type')
    default = info.get('default')

    if OPTIONS.debug:
      print(f'         key: {key}')
      print(f'       value: {value}')
      print(f'  valid keys: {" ".join(keys)}')
      print(f'valid values: {values}')
      print(f'     default: {default}')
      print(f'       regex: {regex}')
      print(f'type convert: {conv}')

    if not key in keys:
      k = ' '.join(keys)
      raise Exception(f'unsupported config key: {key}\nknown keys: {k}')

    if value is None:
      return

    # validate value

    if default is not None and value == '':
      OPTIONS.value = default
      return

    value0 = value
    if conv is not None and callable(conv):
      OPTIONS.value = value = conv(value)

    if conv == bool_from_string:
      return

    if 'user' == key:
      if len(value.encode('utf-8')) > 100:
        raise Exception('error: max user length is 100 bytes')
      if value != value0:
        eprint('warning: leading/trailing whitespace trimmed from user')

    if values:
      if value in values:
        return
      m = f'error: invalid value for {key}: {value}\nvalid values: {values}'
      raise Exception(m)
    if regex:
      if not re.match(regex, value):
        m = f'error: invalid {key} value: {value}'
        help1 = info.get('help')
        if help1:
          m += '\n' + help1
        raise Exception(m)
      return # valid regex match
    raise Exception(f'error: config {key} is read-only')


def parse_args():
  global OPTIONS
  description = 'Little Utility for FAH v8'
  epilog = f'''
Examples

{PROGRAM} . units
{PROGRAM} /rg2 finish
{PROGRAM} other.local/rg1 status
{PROGRAM} /mygpu1 config cpus 0
{PROGRAM} . config -h
{PROGRAM} host1,host2,host3 units
{PROGRAM} host1,host2,host3 info

Notes

If not given, the default command is {DEFAULT_COMMAND!r}.

In 8.3, /group config cpus <n> is not limited to unused cpus across groups.

Group names for fah 8.1 must:
  begin "/", have only letters, numbers, period, underscore, hyphen
Group names on 8.3 can have spaces and special chars.
Web Control 8.3 trims leading and trailing white space when creating groups.
Group "/" is taken to mean the default group, which is "".
For a group name actually starting with "/", use prefix "//".

An error may not be shown if the initial connection times out.
If group does not exist on 8.1, this script may hang until silent timeout.
Config priority does not seem to work. Cores are probably setting priority.
'''

  if sys.platform == 'darwin':
    epilog += 'Commands start and stop are macOS-only.'

  if len(sys.argv) == 2 and sys.argv[1] == 'help':
    sys.argv[1] = '-h'

  parser = argparse.ArgumentParser(
    prog=PROGRAM,
    description=description,
    epilog=epilog,
    formatter_class=argparse.RawDescriptionHelpFormatter)

  parser.set_defaults(argparser=None)
  parser.set_defaults(key=None, value=None) # do not remove this
  parser.set_defaults(peer='') # in case peer is not required in future
  parser.set_defaults(peers=[])
  parser.set_defaults(command=None)
  parser.set_defaults(keypath=None)

  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('-d', '--debug', action='store_true')
  parser.add_argument('--version', action='version', version=__version__)

  help2 = '''\
[host][:port][/group]
Use "." for localhost.
For commands "units" and "info", it can be a comma-separated list of hosts:
host[:port],host[:port],...
'''
  parser.add_argument('peer', metavar='<peer>', help = help2)

  subparsers = parser.add_subparsers(dest='command', metavar='<command>')

  for cmd in COMMANDS:
    default_help = ''
    if cmd in COMMAND_ALIASES:
      default_help = 'alias for ' + COMMAND_ALIASES.get(cmd)
    help1 = COMMANDS_HELP.get(cmd, default_help)
    par = subparsers.add_parser(cmd, description=help1, help=help1)
    if cmd == 'config':
      # TODO: add subparser for each valid config key
      par.add_argument('key', metavar='<key>',
        help = ' '.join(VALID_KEYS_VALUES.keys()))
      par.add_argument('value', nargs='?', metavar='<value>',
        help = 'a valid config value for given key')
    elif cmd == 'get':
      par.add_argument('keypath', metavar='<keypath>',
        help = 'a dot-separated path to a value in client state')


  for cmd in HIDDEN_COMMANDS:
    subparsers.add_parser(cmd)

  OPTIONS = parser.parse_args()
  OPTIONS.argparser = parser
  validate()


def _uri_and_group_for_peer(peer):
  # do not strip right; 8.3 group names might not be stripped
  # create-group should strip what is specified, as web control does
  if peer:
    peer = peer.lstrip()
  if peer in [None, '']:
    return (None, None)

  uri = peer
  if peer.startswith(':'):
    uri = 'ws://.' + peer
  elif peer.startswith('/'):
    uri = 'ws://.' + peer

  scheme = urlparse(uri).scheme

  if scheme == '':
    uri = 'ws://' + peer
  elif not scheme in ['ws', 'wss', 'http', 'https', 'file']:
    # assume misparse of 'host:port'
    uri = 'ws://' + peer

  u = urlparse(uri)

  if not u.scheme in ['ws', 'wss']:
    eprint(f'error: scheme {u.scheme} is not supported for peer {repr(peer)}')
    return (None, None)

  userpass = ''
  user = u.username
  password = u.password
  if user and password:
    userpass = f'{user}:{password}@'

  host = u.hostname # can be None
  if host:
    host = host.strip()
  if host in [None, '', '.', 'localhost', 'localhost.']:
    host = '127.0.0.1'
  else:
    # TODO: validate host regex; maybe disallow numeric IPv6 addresses
    # try to munge a resolvable host name
    # remote in vm is on another subnet; need host.local resolved to ipv4
    if host.endswith('.'):
      host = host[:-1]
    if host.endswith('.local'):
      host = host[:-6]
    if not '.' in host:
      try:
        socket.gethostbyname(host)
      except socket.gaierror:
        # cannot resolve, try again with '.local', if so use ipv4 addr
        # this will be slow if host does not exist
        # note: we do not catch exception
        # may cause lufah to always use ipv4 running on Windows w 'host.local'
        try:
          host = socket.gethostbyname(host + '.local')
        except socket.gaierror:
          eprint(f'Unable to resolve {host!r} or {(host + ".local")!r}')
          return (None, None)

  port = u.port or 7396

  uri = f'{u.scheme}://{userpass}{host}:{port}/api/websocket'

  # validate and munge group, possibly modify uri for 8.1
  # for v8.3, allow "//" prefix, spaces, special chars
  # None or '' is no group (aka all groups)
  # '/'  will be '' (default group)
  # '//' will be '/'
  # '//*' will be '/*'
  # 8.1 group name '/' requires using '//'
  group = u.path
  if group in [None, '']:
    group = None # no group
  elif group == '/':
    group = '' # default group
  elif group.startswith("/"):
    group = group[1:] # strip "/"; can now be ''
  if group and re.match(r'^\/?[\w.-]*$', group):
    # might be connecting to fah 8.1, so append /group
    if not group.startswith('/'):
      uri += '/'
    uri += group

  return (uri, group)


def munged_group_name(group, snapshot):
  # returns group name that exists, None, or throws
  # assume v8.3; old group names may persist from upgrade
  # NOTE: must have connected to have snapshot
  # group may be None
  # expect always having first leading '/' removed from cli argument
  # expect user specified '//name' for actual '/name' (already stripped)
  if group is None:
    return None # no group specified
  if snapshot is None:
    raise Exception('error: snapshot is None')
  orig_group = group
  # get array of actual group names else []
  groups = list(snapshot.get('groups', {}).keys())
  if not groups:
    # for 8.1
    peers = snapshot.get('peers', [])
    groups = [s for s in peers if s.startswith("/")]
  if len(group): # don't conflate '' with '/'; both can legit exist
    # check 'groupname' and '/groupname'
    # if both exist, throw
    # '' is always the default group and not checked here
    group0 = '/' + group
    if group0 in groups and group in groups:
      raise Exception(f'error: both "{group}" and "{group0}" exist')
    if group0 in groups and not group in groups:
      group = group0
  if not group in groups:
    raise Exception(f'error: no "{group}" in groups {groups}')
  if OPTIONS.debug:
    print(f'        groups: {groups}')
    print(f'original group: {repr(orig_group)}"')
    print(f'  munged group: {repr(group)}')
  return group


class FahClient:
  """Class to manage a remote client connection"""

  def __init__(self, peer, name=None):
    self._name = None # if exception, __del__ needs name to exist
    self._group = None
    self.ws = None
    self.data = {} # snapshot
    self._version = (0,0,0) # data.info.version as tuple after connect
    self._callbacks = [] # message callbacks
    # peer is a pseuso-uri that needs munging
    # NOTE: this may raise
    self._uri, self._group = _uri_and_group_for_peer(peer)
    self._name = name if name else self._uri
    # TODO: once connected, there is data.info.id, which is a better index
    _CLIENTS[self._name] = self
    if OPTIONS.debug:
      print(f'Created FahClient: {repr(self._name)}')

  def __del__(self):
    if OPTIONS.debug:
      print("Destructor called for", type(self).__name__, self.name)
    if self.name in _CLIENTS:
      del _CLIENTS[self.name]

  @property
  def name(self):
    return self._name

  @property
  def group(self):
    return self._group

  @property
  def version(self):
    return self._version

  @property
  def groups(self):
    groups = list(self.data.get('groups', {}).keys())
    if not groups:
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
      if OPTIONS.debug:
        eprint('error: unable to convert message to json:', e)
      return
    self._update(data)
    for callback in self._callbacks:
      asyncio.ensure_future(callback(self, data))

  async def receive(self):
    while True:
      try:
        message = await self.ws.recv()
      except ConnectionClosed:
        if OPTIONS.verbose:
          print(f'Connection closed: {self._uri}')
        break
      await self.process_message(message)

  async def connect(self):
    if self.ws is not None and self.ws.open:
      return
    if not self.ws:
      if OPTIONS.verbose:
        print(f'Opening {self._uri}')
      try:
        self.ws = await connect(self._uri, ping_interval=None)
        if OPTIONS.verbose:
          print(f"Connected to {self._uri}")
      except Exception as e:
        self.data = {}
        self._version = (0,0,0)
        raise Exception(f"Failed to connect to {self._uri}") from e
    r = await self.ws.recv()
    snapshot = json.loads(r)
    v = snapshot.get("info", {}).get("version", "0")
    self._version = tuple(map(int, v.split('.')))
    self.data.update(snapshot)
    asyncio.ensure_future(self.receive())

  async def close(self):
    if self.ws is not None:
      await self.ws.close()
    self.ws = None

  def _update(self, data): # data: json array or dict or string
    if isinstance(data, dict):
      # currently, this should not happen
      self.data.update(data)
    elif isinstance(data, list):
      pass # self._process_update_list(data)
    # else if string, ignore "ping"

  async def send(self, message):
    # TODO: check ws is open
    msgstr = None
    if isinstance(message, dict):
      msg = message.copy()
      if not 'time' in msg:
        t = datetime.datetime.utcnow().isoformat() + 'Z'
        msg['time'] = t
      msgstr = json.dumps(msg)
    elif isinstance(message, str):
      msgstr = message
    elif isinstance(message, list):
      # currently, would be invalid
      msgstr = json.dumps(message)
    if OPTIONS.debug:
      print(f'WOULD BE sending: {msgstr}')
      return
    if OPTIONS.verbose:
      print(f'sending: {msgstr}')
    if msgstr:
      await self.ws.send(msgstr)

  async def send_command(self, cmd):
    if not cmd in SIMPLE_CLIENT_COMMANDS:
      raise Exception(f'unknown client command: {cmd}')
    if self.version < (8,3):
      if cmd == 'fold':
        cmd = 'unpause'
      msg = {"cmd": cmd}
    else:
      msg = {"state": cmd, "cmd": "state"}
      # NOTE: group would be created if it doesn't exist
      if self.group is not None:
        group = munged_group_name(self.group, self.data)
        if group is not None:
          msg["group"] = group
    await self.send(msg)

  #async def send_global_config(self, config): pass
  #async def send_group_config(self, group, config):pass


async def do_status(client):
  await client.connect()
  if not OPTIONS.debug:
    print(json.dumps(client.data, indent=2))


async def do_command(client):
  await client.connect()
  await client.send_command(OPTIONS.command)


# TODO: refactor into config_get(), config_set(), get_config(snapshot,group)
async def do_config(client):
  await client.connect()
  key = OPTIONS.key
  value = OPTIONS.value
  ver = client.version
  have_acct = 0 < len(client.data.get("info", {}).get("account", ''))

  # FIXME: potential race if groups changes before we write
  # think currently client deletes groups not in group config command
  groups = client.groups # [] on < 8.3
  # we don't care about 8.1 peer groups because everything is in main config
  # just need to be mindful of possible config.available_cpus

  if (8,3) <= ver:
    group = munged_group_name(client.group, client.data)
  else:
    group = client.group

  # v8.3 splits config between global(account) and group

  key0 = key # might exist in 8.1
  key = key.replace('-', '_') # convert cli keys to actual

  if value is None:
    # print value for key
    if (8,3) <= ver and key in GROUP_CONFIG_KEYS and group is not None:
      # client.data.groups.{group}.config
      conf = client.data.get('groups',{}).get(group,{}).get("config",{})
      print(json.dumps(conf.get(key)))
    else:
      # try getting key, no matter what it is
      conf = client.data.get('config', {})
      print(json.dumps(conf.get(key, conf.get(key0))))
    return

  if 'cpus' == key:
    maxcpus0 = client.data.get('info', {}).get('cpus', 0)
    # available_cpus in fah v8.1.19 only
    maxcpus = client.data.get('config', {}).get('available_cpus', maxcpus0)
    if value > maxcpus:
      raise Exception(f'error: cpus is greater than available cpus {maxcpus}')
    # FIXME: cpus are in groups on fah 8.3; need to sum cpus across groups
    # available_cpus = maxcpus - total_group_cpus
    # if value > (available_cpus - current_group_cpus)
    # this is simpler if only have one group (the default group)
    # no need to calc available_cpus if new value is 0
    # NOTE: client will not limit cpus value sent for us

  if (8,3) <= ver:
    if key in DEPRECATED_CONFIG_KEYS:
      raise Exception(f'error: key "{key0}" is deprecated in fah 8.3')
    if not key in VALID_CONFIG_SET_KEYS:
      raise Exception(f'error: setting "{key0}" is not supported in fah 8.3')
    if have_acct and key in GLOBAL_CONFIG_KEYS:
      eprint('warning: machine is linked to an account')
      eprint(f'warning: "{key0}" "{value}" may be overwritten by account')

  # TODO: don't send if value == current_value
  conf = {key: value}
  msg = {"cmd":"config", "config":conf}
  if (8,3) <= ver and key in GROUP_CONFIG_KEYS:
    if group is None:
      raise Exception(f'error: cannot set "{key0}" on group None')
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
  if isinstance(msg, list) and len(msg) == 3 and msg[0] == 'log':
    # ignore msg[1], which is -1 or -2
    v = msg[2]
    if isinstance(v, (list, tuple)):
      for line in v:
        print(line)
    else:
      print(v)


async def do_log(client):
  client.register_callback(_print_log_lines)
  await client.connect()
  await client.send({"cmd": "log", "enable": True})
  if OPTIONS.debug:
    return
  await client.ws.wait_closed()


async def do_experimental(**_):
  # ~1 sec delay if remote host ends with '.local'
  client = FahClient(OPTIONS.peer)
  await client.connect()
  print(json.dumps(client.data, indent=2))
  # ~10 sec delay exiting if don't close first; no async context manager?
  # destructor is called immediately
  await client.close()


async def do_xpeer(**_):
  print('_uri_and_group_for_peer: ', _uri_and_group_for_peer(OPTIONS.peer))


async def do_show_groups(client):
  await client.connect()
  print(json.dumps(client.groups))


async def do_get(client):
  await client.connect()
  value = get_object_at_key_path(client.data, OPTIONS.keypath)
  print(json.dumps(value, indent=2))



async def _print_json_message(client, msg):
  _ = client
  if isinstance(msg, (list, dict, str)):
    print(json.dumps(msg))


async def do_watch(client):
  client.register_callback(_print_json_message)
  await client.connect()
  if OPTIONS.debug:
    return
  print(json.dumps(client.data, indent=2))
  await client.ws.wait_closed()


def print_units_header():
  empty = ''
  print(f'{empty:-<73}')
  print('Project  CPUs  GPUs  Status          Progress  PPD       ETA')
  print(f'{empty:-<73}')


def status_for_unit(client, unit):
  """Human-readable Status string"""
  # FIXME: should exactly match what Web Control does
  # FIXME: waiting is web control unitview.waiting
  #if unit.get('waiting'): return STATUS_STRINGS.get('WAIT', state)
  status = unit.get('pause_reason')
  if status:
    # assume paused if have pause_reason
    return status
  state = unit.get("state", '') # is never FINISH
  if state == 'RUN':
    if client.version < (8,3):
      paused = client.data.get('config',{}).get('paused', False)
      finish = client.data.get('config',{}).get('finish', False)
    else:
      group = unit.get('group', None)
      if group is not None:
        gconfig = client.data.get('groups',{}).get(group,{}).get('config',{})
        paused = gconfig.get('paused', False)
        finish = gconfig.get('finish', False)
      else:
        paused = True
        finish = False
    if paused:
      state = 'PAUSE'
    elif finish:
      state = 'FINISH'
  return STATUS_STRINGS.get(state, state)


def print_unit(client, unit):
  if unit is None:
    return
  # TODO: unit dataclass
  assignment = unit.get("assignment", {})
  project = assignment.get("project", '')
  status = status_for_unit(client, unit)
  cpus = unit.get("cpus", 0)
  gpus = len(unit.get("gpus", []))
  progress = unit.get("progress", 0)
  progress = math.floor(progress * 1000) / 10.0
  progress = str(progress) + '%'
  ppd = unit.get("ppd", 0)
  eta = unit.get("eta", '')
  print(
    f'{project:<7}  {cpus:<4}  {gpus:<4}  {status:<16}{progress:^8}'
    f'  {ppd:<8}  {eta}')


def units_for_group(client, group):
  if client is None:
    # assert ?
    raise Exception('error: units_for_group(client, group): client is None')
  all_units = client.data.get('units', [])
  if group is None or client.version < (8,3):
    units = all_units
  else:
    units = []
    for unit in all_units:
      g = unit.get('group')
      if g is not None and g == group:
        units.append(unit)
  return units


def client_machine_name(client):
  if client is None:
    return ''
  return client.data.get('info',{}).get('hostname','')


def clients_sorted_by_machine_name():
  return sorted(list(_CLIENTS.values()), key=client_machine_name)


async def do_print_units(**_):
  if _CLIENTS:
    print_units_header()
  for client in _CLIENTS.values():
    await client.connect()
  for client in clients_sorted_by_machine_name():
    r = urlparse(client.name)
    name = client_machine_name(client)
    if not name:
      name = r.hostname
    if r.port and r.port != 7396:
      name += f':{r.port}'
    if r.path and r.path.startswith('/api/websocket'):
      name += r.path[len('/api/websocket'):]
    groups = client.groups
    if not groups:
      print(name)
      units = units_for_group(client, None)
      if not units:
        #print(f' no units')
        continue
      for unit in units:
        print_unit(client, unit)
    else:
      for group in groups:
        print(f'{name}/{group}')
        units = units_for_group(client, group)
        if not units:
          #print(f' no units')
          continue
        for unit in units:
          print_unit(client, unit)


def print_info(client):
  if client is None:
    return
  info = client.data.get('info',{})
  clientver = info.get('version','') # the string, not tuple
  osname = info.get('os','')
  osver = info.get('os_version','')
  cpu = info.get('cpu','')
  brand = info.get('cpu_brand','')
  cores = info.get('cpus',0)
  host = info.get('hostname','')
  print(f'  Host: {host}')
  print(f'Client: {clientver}')
  print(f'    OS: {osname} {osver}')
  print(f'   CPU: {cores} cores, {cpu}, "{brand}"')


async def do_print_info_multi(**_):
  for client in _CLIENTS.values():
    await client.connect()
  clients = clients_sorted_by_machine_name()
  multi = len(clients) > 1
  if multi:
    print()
  for client in clients:
    print_info(client)
    if multi:
      print()


def do_start_or_stop_local_sevice(**_):
  if sys.platform == 'darwin' and OPTIONS.command in ['start', 'stop']:
    if OPTIONS.peer != '.':
      raise Exception('peer must be "." for commands start and stop')
    note = f'org.foldingathome.fahclient.nobody.{OPTIONS.command}'
    cmd = ['notifyutil', '-p', note]
    if OPTIONS.debug:
      print(f'WOULD BE running: {" ".join(cmd)}')
      return
    if OPTIONS.verbose:
      print(' '.join(cmd))
    check_call(cmd)


COMMANDS_DISPATCH = {
  "status"  : do_status,
  "pause"   : do_command,
  "unpause" : do_command,
  "fold"    : do_command,
  "finish"  : do_command,
  "log"     : do_log,
  "config"  : do_config,
  "groups"  : do_show_groups,
  "x"       : do_xpeer,
  "watch"   : do_watch,
  "start"   : do_start_or_stop_local_sevice,
  "stop"    : do_start_or_stop_local_sevice,
  "units"   : do_print_units,
  "info"    : do_print_info_multi,
  "get"     : do_get,
}


async def main_async():
  parse_args()

  if not OPTIONS.command in COMMANDS + HIDDEN_COMMANDS:
    raise Exception(f'error: unknown command: {OPTIONS.command}')

  func = COMMANDS_DISPATCH.get(OPTIONS.command)
  if func is None:
    raise Exception(f'error: command {OPTIONS.command} is not implemented')

  if OPTIONS.command in NO_CLIENT_COMMANDS:
    client = None
  elif OPTIONS.command in MULTI_PEER_COMMANDS:
    client = None
  else:
    client = FahClient(OPTIONS.peer)

  if OPTIONS.command in MULTI_PEER_COMMANDS:
    for peer in OPTIONS.peers:
      c = FahClient(peer)

  try:
    if asyncio.iscoroutinefunction(func):
      await func(client=client)
    else:
      func(client=client)
  except ConnectionClosed:
    if OPTIONS.verbose:
      eprint('Connection closed')
  finally:
    for c in _CLIENTS.values():
      try:
        await c.close()
      except:
        pass


def main():
  try:
    asyncio.run(main_async())
  except (KeyboardInterrupt, EOFError):
    print('\n')
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

if __name__ == '__main__':
  main()
