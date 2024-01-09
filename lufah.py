#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
lufah: Little Utility for FAH v8
"""

__version__ = '0.3.3'

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
from urllib.parse import urlparse
from urllib.request import urlopen

from websockets import connect # pip3 install websockets --user
from websockets.exceptions import *

PROGRAM = os.path.basename(sys.argv[0])
if PROGRAM.endswith(".py"):
  PROGRAM = PROGRAM[:-3]

# TODO:
# lufah . get <keypath> # show json for snapshot.keypath
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
]
if sys.platform == 'darwin': COMMANDS += ['start', 'stop']

COMMAND_ALIASES = {
  # alias : actual
  'unpause' : 'fold',
}

COMMANDS_HELP = dict(
  status = 'show json snapshot of client state',
  pause = '',
  fold = '',
  finish = '',
  log = 'show log; use control-c to exit',
  config = 'get or set config values',
  start = 'start local client service; peer must be "."',
  stop = 'stop local client service; peer must be "."',
  groups = 'show json array of resource group names',
  watch = 'show incoming messages; use control-c to exit',
  units = 'show table of all units by group',
  info = 'show peer host and client info',
)

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
GROUP_CONFIG_KEYS = ['on_idle', 'beta', 'key', 'cpus']

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


_CLIENTS = {}


def eprint(*args, **kwargs):
  print(*args, file=sys.stderr, **kwargs)


def bool_from_string(value):
  if value.lower() in ['true', 'yes', 'on', '1']:
    return True
  elif value.lower() in ['false', 'no', 'off', '0']:
    return False
  else:
    raise Exception(f'error: not a bool string: {value}')


def value_for_key_path(adict, kp):
  # kp: an array of keys or a dot-separated str of keys
  # like to handle int array indicies in str kp
  # ? import munch/addict/benedict
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
  # TODO: handle file:...
  response = urlopen(url)
  if response.getcode() == 200:
    data = json.loads(response.read().decode('utf-8'))
  return data


def _fetch_causes(options, **kwargs):
  data = _fetch_json('https://api.foldingathome.org/project/cause')
  if options.verbose: print('causes:', json.dumps(data, indent=2))
  return data


def validate(options):
  if options.debug: options.verbose = True

  options.peer = options.peer.lstrip() # ONLY left strip
  if not options.peer: raise Exception(f'error: no peer specified')
  # true validation of peer is done by _uri_and_group_for_peer()
  # TODO: accept file:~/peers.json containing {"peers":[".","host2","host3"]}
  #   set options.peers; set options.peer = None

  if options.debug:
    print(f'   peer: {repr(options.peer)}')
    print(f'command: {repr(options.command)}')

  if options.command in [None, '']:
    options.command = DEFAULT_COMMAND
  else:
    options.command = COMMAND_ALIASES.get(options.command, options.command)

  if options.debug:
    print(f'command: {repr(options.command)}')

  if options.command in MULTI_PEER_COMMANDS:
    options.peers = []
    if ',' in options.peer and not '/' in options.peer:
      # assume comma separated list of peers
      peers = options.peer.split(',')
      for peer in peers:
        peer = peer.strip()
        if peer:
          options.peers.append(peer)
      if options.debug:
        print(f'  peers: {options.peers!r}')
    else:
      options.peers = [options.peer]
    options.peer = None

  # validate config key value
  if options.command in ['config']:
    key = options.key
    value = options.value
    keys = VALID_KEYS_VALUES.keys()
    info = VALID_KEYS_VALUES.get(key, {})
    values = info.get('values')
    regex = info.get('re')
    conv = info.get('type')
    default = info.get('default')

    if options.debug:
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

    if value is None: return

    # validate value

    if default is not None and value == '':
      options.value = default
      return

    value0 = value
    if conv is not None and callable(conv):
      options.value = value = conv(value)

    if conv == bool_from_string: return

    if 'user' == key:
      if len(value.encode('utf-8')) > 100:
        raise Exception(f'error: max user length is 100 bytes')
      if value != value0:
        eprint('warning: leading/trailing whitespace trimmed from user')

    if values:
      if value in values: return
      m = f'error: invalid value for {key}: {value}\nvalid values: {values}'
      raise Exception(m)
    elif regex:
      if not re.match(regex, value):
        m = f'error: invalid {key} value: {value}'
        help = info.get('help')
        if help: m += '\n' + help
        raise Exception(m)
      return # valid regex match
    else:
      raise Exception(f'error: config {key} is read-only')


def parse_args():
  global options
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

All commands except "/group config key value" are supported for fah 8.3.
Command config may not behave as expected for fah 8.3.

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

  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('-d', '--debug', action='store_true')
  parser.add_argument('--version', action='version', version=__version__)

  help1 = '[host][:port][/group]  Use "." for localhost'
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
    help = COMMANDS_HELP.get(cmd, default_help)
    par = subparsers.add_parser(cmd, description=help, help=help)
    if cmd == 'config':
      # TODO: add subparser for each valid config key
      par.add_argument('key', metavar='<key>',
        help = ' '.join(VALID_KEYS_VALUES.keys()))
      par.add_argument('value', nargs='?', metavar='<value>',
        help = 'a valid config value for given key')

  for cmd in HIDDEN_COMMANDS:
    subparsers.add_parser(cmd)

  options = parser.parse_args()
  options.argparser = parser
  validate(options)
  return options


def _uri_and_group_for_peer(peer):
  # do not strip right; 8.3 group names might not be stripped
  # create-group should strip what is specified, as web control does
  if peer: peer = peer.lstrip()
  if peer in [None, '']: return (None, None)

  uri = peer
  if peer.startswith(':'):
    uri = 'ws://.' + peer
  elif peer.startswith('/'):
    uri = 'ws://.' + peer
  if urlparse(uri).scheme == '':
    uri = 'ws://' + peer

  u = urlparse(uri)

  if not u.scheme in ['ws', 'wss']:
    eprint(f'error: scheme {u.scheme} is not supported for peer {repr(peer)}')
    return (None, None)

  userpass = ''
  user = u.username
  password = u.password
  if user and password: userpass = f'{user}:{password}@'

  host = u.hostname # can be None
  if host: host = host.strip()
  if host in [None, '', '.', 'localhost', 'localhost.']:
    host = '127.0.0.1'
  else:
    # TODO: validate host regex; maybe disallow numeric IPv6 addresses
    # try to munge a resolvable host name
    # remote in vm is on another subnet; need host.local resolved to ipv4
    if host.endswith('.'): host = host[:-1]
    if host.endswith('.local'): host = host[:-6]
    if not '.' in host:
      try:
        socket.gethostbyname(host)
      except socket.gaierror as e:
        # cannot resolve, try again with '.local', if so use ipv4 addr
        # this will be slow if host does not exist
        # note: we do not catch exception
        # may cause lufah to always use ipv4 running on Windows w 'host.local'
        try:
          host = socket.gethostbyname(host + '.local')
        except socket.gaierror as e:
          m = f'Unable to resolve {repr(host)} or {repr(host + ".local")}'
          raise Exception(m)
        except:
          raise

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
  if group in [None, '']: group = None # no group
  elif group == '/': group = '' # default group
  elif group.startswith("/"): group = group[1:] # strip "/"; can now be ''
  if group and re.match(r'^\/?[\w.-]*$', group):
    # might be connecting to fah 8.1, so append /group
    if not group.startswith('/'): uri += '/'
    uri += group

  return (uri, group)


def munged_group_name(options, group, snapshot):
  # returns group name that exists, None, or throws
  # assume v8.3; old group names may persist from upgrade
  # NOTE: must have connected to have snapshot
  # group may be None
  # expect always having first leading '/' removed from cli argument
  # expect user specified '//name' for actual '/name' (already stripped)
  if group is None: return None # no group specified
  if snapshot is None: raise Exception(f'error: snapshot is None')
  orig_group = group
  # get array of actual group names else []
  groups = list(snapshot.get('groups', {}).keys())
  if not groups:
    # for 8.1
    peers = self.data.get('peers', [])
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
  if options.debug:
    print(f'        groups: {groups}')
    print(f'original group: {repr(orig_group)}"')
    print(f'  munged group: {repr(group)}')
  return group


class FahClient:

  def __init__(self, peer, name=None):
    self._name = None # if exception, __del__ needs _name to exist
    self._ws = None
    self.data = {} # snapshot
    self._version = (0,0,0) # data.info.version as tuple after connect
    # peer is a pseuso-uri that needs munging
    # NOTE: this may raise
    self._uri, self._group = _uri_and_group_for_peer(peer)
    self._name = name if name else self._uri
    # NOTE: this does not actually connect yet
    self._conn = connect(self._uri, ping_interval=None)
    # TODO: once connected, there is data.info.id, which is a better index
    _CLIENTS[self._name] = self
    if options.debug:
      print(f'Created FahClient: {repr(self._name)}')

  def __del__(self):
    if options.debug:
      print("Destructor called for", type(self).__name__, self._name)
    if self._name in _CLIENTS: del _CLIENTS[self._name]

  def version(self): return self._version

  def groups(self):
    groups = list(self.data.get('groups', {}).keys())
    if not groups:
      peers = self.data.get('peers', [])
      groups = [s for s in peers if s.startswith("/")]
    return groups

  async def connect(self, *args, **kwargs):
    if self._ws is not None and self._ws.open: return
    if not self._ws:
      if options.verbose: print(f'Opening {self._uri}')
      try:
        self._ws = await self._conn.__aenter__(*args, **kwargs)
      except Exception as e:
        self.data = {}
        self._version = (0,0,0)
        raise Exception(f"Failed to connect to {self._uri}")
      else:
        if options.verbose: print(f"Connected to {self._uri}")
    r = await self._ws.recv()
    snapshot = json.loads(r)
    v = snapshot.get("info", {}).get("version", "0")
    self._version = tuple([int(x) for x in v.split('.')])
    self.data.update(snapshot)

  async def close(self):
    if self._ws is not None:
      await self._ws.close()
    self._ws = None

  def update(self, data): # data: json array or dict or string
    if isinstance(v, (dict)):
      # currently, this should not happen
      self.data.update(data)
    elif isinstance(v, (list)):
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
    if options.debug:
      print(f'WOULD BE sending: {msgstr}')
      return
    if options.verbose: print(f'sending: {msgstr}')
    if msgstr:
      await self._ws.send(msgstr)

  async def sendCommand(self, cmd):
    if cmd == 'unpause': cmd = 'fold'
    # TODO
    pass
  async def sendGlobalConfig(self, config): pass
  async def sendGroupConfig(self, group, config):pass

  async def __aenter__(self, *args, **kwargs):
    if options.debug: print('entering async context')
    await self.connect(*args, **kwargs)

  async def __aexit__(self, *args, **kwargs):
    if options.debug: print('exiting async context')
    await self._conn.__aexit__(*args, **kwargs)
    self._ws = None


async def status(options, client):
  if not options.debug:
    print(json.dumps(client.data, indent=2))


async def command(options, client):
  cmd = options.command
  if not cmd in SIMPLE_CLIENT_COMMANDS:
    raise Exception(f'unknown client command: {cmd}')
  if client.version() < (8,3):
    if cmd == 'fold': cmd = 'unpause'
    msg = {"cmd": cmd}
  else:
    msg = {"state": cmd, "cmd": "state"}
    # NOTE: group would be created if it doesn't exist
    if client._group is not None:
      group = munged_group_name(options, client._group, client.data)
      if group is not None:
        msg["group"] = group
  await client.send(msg)


# TODO: refactor into config_get(), config_set(), get_config(snapshot,group)
async def config(options, client):
  key = options.key
  value = options.value
  if True:
    ver = client.version()
    haveAcct = 0 < len(client.data.get("info", {}).get("account", ''))

    # FIXME: potential race if groups changes before we write
    # think currently client deletes groups not in group config command
    groups = client.groups() # [] on < 8.3
    # we don't care about 8.1 peer groups because everything is in main config
    # just need to be mindful of possible config.available_cpus

    if (8,3) <= ver:
      group = munged_group_name(options, client._group, client.data)
    else:
      group = client._group

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

    if (8,3) <= ver:
      if key in DEPRECATED_CONFIG_KEYS:
        raise Exception(f'error: key "{key}" is deprecated in fah 8.3')
      if not key in VALID_CONFIG_SET_KEYS:
        raise Exception(f'error: key "{key}" is not supported in fah 8.3')
      if key in GROUP_CONFIG_KEYS:
        raise Exception(f'error: group config is not supported for fah 8.3')
      if haveAcct and key in GLOBAL_CONFIG_KEYS:
        eprint(f'warning: machine is linked to an account')
        eprint(f'warning: "{key}" "{value}" may be overwritten by account')
      eprint(f'warning: config may not work as expected with fah 8.3')

    # TODO: don't send if value == current_value
    # TODO: create appropriate 8.3 config.groups dict with all current groups
    # this is *only* global config with 8.3
    conf = {key: value}
    msg = {"cmd":"config", "config":conf}
    await client.send(msg)


async def log(options, client):
  # TODO: client.sendLogEnable(True)
  await client.send({"cmd": "log", "enable": True})
  if options.debug: return
  while True:
    # TODO: FahClient needs register_callback, msg recv loop, reconnect option
    r = await client._ws.recv()
    msg = json.loads(r)
    # client doesn't just send arrays
    if isinstance(msg, list) and len(msg) and msg[0] == 'log':
      # ignore msg[1], which is -1 or -2
      v = msg[2]
      if isinstance(v, (list, tuple)):
        for line in v: print(line)
      else:
        print(v)
      sys.stdout.flush()


async def experimental(options, **kwargs):
  # ~1 sec delay if remote host ends with '.local'
  client = FahClient(options.peer)
  await client.connect()
  print(json.dumps(client.data, indent=2))
  # ~10 sec delay exiting if don't close first; no async context manager?
  # destructor is called immediately
  await client.close()


async def xpeer(options, **kwargs):
  print('_uri_and_group_for_peer: ', _uri_and_group_for_peer(options.peer))


async def show_groups(options, client):
  print(json.dumps(client.groups()))


async def watch(options, client):
  if options.debug: return
  print(json.dumps(client.data, indent=2))
  # FIXME: this can be slow to react to SIGINT
  async for message in client._ws:
    msg = json.loads(message)
    if isinstance(msg, (list, dict, str)):
      print(json.dumps(msg))
    elif isinstance(msg, bytes):
      print(message.hex())
    sys.stdout.flush()


def print_units_header():
  empty = ''
  print(f'{empty:-<73}')
  print('Project  CPUs  GPUs  Status          Progress  PPD       ETA')
  print(f'{empty:-<73}')


def status_for_unit(client, unit):
  state = unit.get("state", '--') # is never FINISH
  # FIXME: waiting is web control unitview.waiting
  #if unit.get('waiting'): return STATUS_STRINGS.get('WAIT', state)
  if unit.get('pause_reason'):
    return STATUS_STRINGS.get('PAUSE', state)
  if state == 'RUN':
    if client.version() < (8,3):
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
    if paused: state = 'PAUSE'
    elif finish: state = 'FINISH'
  return STATUS_STRINGS.get(state, state)


def print_unit(client, unit):
  if unit is None: return
  # TODO: unit dataclass
  assignment = unit.get("assignment", {})
  project = assignment.get("project", '')
  state = status_for_unit(client, unit)
  cpus = unit.get("cpus", 0)
  gpus = len(unit.get("gpus", []))
  progress = unit.get("progress", 0)
  progress = math.floor(progress * 1000) / 10.0
  progress = str(progress) + '%'
  ppd = unit.get("ppd", 0)
  eta = unit.get("eta", '')
  print(
    f'{project:<7}  {cpus:<4}  {gpus:<4}  {state:<16}{progress:^8}'
    f'  {ppd:<8}  {eta}')


def units_for_group(client, group):
  if client is None:
    # assert ?
    raise Exception('error: units_for_group(client, group): client is None')
  all_units = client.data.get('units', [])
  if group is None or client.version() < (8,3):
    units = all_units
  else:
    units = []
    for unit in all_units:
      g = unit.get('group')
      if g is not None and g == group:
        units.append(unit)
  return units


def client_machine_name(client):
  if client is None: return ''
  return client.data.get('info',{}).get('hostname','')


def clients_sorted_by_machine_name():
  return sorted(list(_CLIENTS.values()), key=client_machine_name)


async def print_units(options, **kwargs):
  if _CLIENTS:
    print_units_header()
  for client in clients_sorted_by_machine_name():
    r = urlparse(client._name)
    name = client_machine_name(client)
    if not name: name = r.hostname
    if r.port and r.port != 7396: name += f':{r.port}'
    if r.path and r.path.startswith('/api/websocket'):
      name += r.path[len('/api/websocket'):]
    groups = client.groups()
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


def print_info(options, client):
  if client is None: return
  info = client.data.get('info',{})
  clientver = info.get('version','')
  os = info.get('os','')
  osver = info.get('os_version','')
  cpu = info.get('cpu','')
  brand = info.get('cpu_brand','')
  cores = info.get('cpus',0)
  host = info.get('hostname','')
  print(f'  Host: {host}')
  print(f'Client: {clientver}')
  print(f'    OS: {os} {osver}')
  print(f'   CPU: {cores} cores, {cpu}, "{brand}"')


def print_info_multi(options, **kwargs):
  clients = clients_sorted_by_machine_name()
  multi = len(clients) > 1
  if multi: print()
  for client in clients:
    print_info(options, client)
    if multi: print()


def start_or_stop_local_sevice(options, **kwargs):
  if sys.platform == 'darwin' and options.command in ['start', 'stop']:
    if options.peer != '.':
      raise Exception('peer must be "." for commands start and stop')
    from subprocess import check_call
    note = f'org.foldingathome.fahclient.nobody.{options.command}'
    cmd = ['notifyutil', '-p', note]
    if options.debug:
      print(f'WOULD BE running: {" ".join(cmd)}')
      return
    if options.verbose: print(' '.join(cmd))
    check_call(cmd)


COMMANDS_DISPATCH = {
  "status"  : status,
  "pause"   : command,
  "unpause" : command,
  "fold"    : command,
  "finish"  : command,
  "log"     : log,
  "config"  : config,
  "groups"  : show_groups,
  "x"       : xpeer,
  "watch"   : watch,
  "start"   : start_or_stop_local_sevice,
  "stop"    : start_or_stop_local_sevice,
  "units"   : print_units,
  "info"    : print_info_multi,
}


async def main_async():
  options = parse_args()

  if not options.command in COMMANDS + HIDDEN_COMMANDS:
    raise Exception(f'error: unknown command: {options.command}')

  func = COMMANDS_DISPATCH.get(options.command)
  if func is None:
    raise Exception(f'error: command {options.command} is not implemented')

  if options.command in NO_CLIENT_COMMANDS:
    client = None
  elif options.command in MULTI_PEER_COMMANDS:
    client = None
  else:
    client = FahClient(options.peer)
    await client.connect()

  if options.command in MULTI_PEER_COMMANDS:
    for peer in options.peers:
      c = FahClient(peer)
      if c is not None:
        await c.connect()

  try:
    if asyncio.iscoroutinefunction(func):
        await func(options, client=client)
    else:
        func(options, client=client)
  except ConnectionClosed:
    if options.verbose: eprint('Connection closed')
  finally:
    for c in _CLIENTS.values():
      try:
        await c.close()
      except: pass


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
  except OSError as e:
    # Windows may raise this
    if e.errno != 22:
      eprint(e)
      sys.exit(1)
  except Exception as e:
    eprint(e)
    sys.exit(1)

if __name__ == '__main__':
  main()
