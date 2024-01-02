#!/usr/bin/env python3
import os
import sys
import json
import asyncio
import socket
from urllib.parse import urlparse
import argparse
import re
import datetime
from websockets import connect # pip3 install websockets
from websockets.exceptions import *

program = os.path.basename(sys.argv[0])
version = '0.1.10'

# TODO:
#   lufah . get <keypath> # show json for snapshot.keypath
#   lufah . create-group <name> # by sending pause to nonexistent group
#   lufah . delete-group <name> # refuse if group has running WU?
HIDDEN_COMMANDS = ['x', 'fake'] # simple experimental stuff
NO_CLIENT_COMMANDS = ['start', 'stop', 'x']
# allowed cli commands; all visible
COMMANDS = 'status pause unpause fold finish log config groups watch'.split()
if sys.platform == 'darwin': COMMANDS += ['start', 'stop']

COMMANDS_HELP = dict(
  status = 'show json snapshot of client state',
  pause = '',
  unpause = 'alias for fold',
  fold = '',
  finish = '',
  log = 'show log; use control-c to exit',
  config = 'get or set config values',
  start = 'start local client service; peer must be "."',
  stop = 'stop local client service; peer must be "."',
  groups = 'show resource group names',
  watch = 'show incoming messages; use control-c to exit',
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

# both as sent to client, and cli command
SIMPLE_CLIENT_COMMANDS = ['pause', 'fold', 'finish']

CLIENTS = {}


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
validKeysValues = {
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


def validate(options):
  if options.debug: options.verbose = True
  # do not strip right; 8.3 group names might not be stripped
  # create-group should strip what is specified, as web control does
  options.peer = options.peer.lstrip()
  if not options.peer: raise Exception(f'error: no peer specified')
  r = urlparse('//' + options.peer)
  host = r.hostname or '127.0.0.1' # note r.hostname can be None
  port = r.port or 7396
  group = r.path # expect '' or '/*'
  host = host.strip()
  if host in ['.', 'localhost']: host = '127.0.0.1'

  if options.command in [None, '']: options.command = 'status'
  elif options.command == 'unpause': options.command = 'fold'

  # validate and munge group
  # for v8.3, allow "//" prefix, spaces, special chars
  # None or '' is no group (aka all groups)
  # '/'  will be '' (default group)
  # '//' will be '/'
  # '//*' will be '/*'
  # 8.1 group name '/' requires using '//'
  if group in [None, '']: group = None # no group
  elif group == '/': group = '' # default group
  else:
    if re.match(r'^\/[\w.-]+$', group):
      options.legacyGroupMatch = True # but not necessarily connecting to 8.1
    if group.startswith("/"): group = group[1:] # strip "/"; can now be ''

  options.host = host
  options.port = port
  options.group = group

  if r.username and r.password: host = f'{r.username}:{r.password}@{host}'
  elif r.username: host = f'{r.username}@{host}'

  # TODO: validate host, port; maybe disallow numeric IPv6 addresses

  # FIXME: do not add group to uri for newer commands, even if legacy match
  if options.legacyGroupMatch:
    options.uri = f'ws://{host}:{port}/api/websocket/{group}'
  else:
    # this is what v8.3 expects, but currently appending /group seems ok
    # when v8.1 support is dropped, just use this instead
    # less restrictive group names are not url friendly
    options.uri = f'ws://{host}:{port}/api/websocket'

  if options.debug:
    print(f'\n   peer: "{options.peer}"')
    print(f'   host: "{host}"')
    print(f'   port: {port}')
    print(f'  group: "{group}"')
    print(f'command: {options.command}')
    print(f'    uri: "{options.uri}"')

  # validate config key value
  if options.command in ['config']:
    key = options.key
    value = options.value
    keys = validKeysValues.keys()
    info = validKeysValues.get(key, {})
    values = info.get('values')
    regex = info.get('re')
    conv = info.get('type')
    default = info.get('default')

    if options.debug:
      print(f'\nkey: {key} value: {value}')
      print(f'valid keys: {" ".join(keys)}')
      print(f'valid values: {values}')
      print(f'default {default}')
      print(f'regex {regex}')
      print(f'type convert {conv}')

    if not key in keys:
      k = ' '.join(keys)
      raise Exception(f'unsupported config key: {key}\nknown keys: {k}')

    if value is None: return
    # else validate value

    if default is not None and value == '':
      options.value = default
      return

    value0 = value
    if conv is not None: # assume callable
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

{program} . finish
{program} other.local/rg1 status
{program} /mygpu1 config cpus 0

Notes

All commands except `/group config key value` are supported for fah 8.3.
Command config may not behave as expected for fah 8.3.

Group names should preferably conform to fah 8.1 restrictions:
  begins "/", has only letters, numbers, period, underscore, hyphen
Group names with spaces and special chars may work with 8.3. This is untested.
Group "/" is taken to mean the default group, which is "".
For a group actually named "/" on 8.3, use "//".

An error may not be shown if the initial connection times out.
If group does not exist on 8.1, this script may hang until silent timeout.
Config priority does not seem to work. Cores are probably setting priority.
'''

  if sys.platform == 'darwin':
    epilog += 'Commands start and stop are macOS-only.'

  parser = argparse.ArgumentParser(description=description, epilog=epilog,
    formatter_class=argparse.RawDescriptionHelpFormatter)

  parser.set_defaults(key=None, value=None) # do not remove this
  parser.set_defaults(legacyGroupMatch=False)
  parser.set_defaults(host='127.0.0.1', port=7396, group='', uri='')

  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('-d', '--debug', action='store_true')
  parser.add_argument('--version', action='version', version=version)

  parser.add_argument('peer',
    help = '[host][:port][/group]  Use "." for localhost')

  subparsers = parser.add_subparsers(dest='command', metavar = 'command')

  for cmd in COMMANDS:
    help = COMMANDS_HELP.get(cmd)
    par = subparsers.add_parser(cmd, description=help, help=help)
    if cmd == 'config':
      # TODO: add subparser for each valid config key
      par.add_argument('key', help = ' '.join(validKeysValues.keys()))
      par.add_argument('value', nargs='?',
        help = 'a valid config value for given key')

  for cmd in HIDDEN_COMMANDS:
    subparsers.add_parser(cmd)

  options = parser.parse_args()
  validate(options)
  return options


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
    print(f'groups: {groups}')
    print(f'original group: "{orig_group}"')
    print(f'munged group: "{group}"')
  return group


class FahClient:
  # FIXME: not tested with fah 8.1 groups
  def __init__(self, host='127.0.0.1', port=7396, group=None, name=None):
    self._host = host
    self._port = port
    self._name = name if name else f'{host}:{port}'
    self._group = group  # group is usually None
    self.data = {} # snapshot
    self._version = (0,0,0) # data.info.version as tuple
    self._build_uri()
    if options.debug:
      print(f'   name: "{self._name}"')

  def __del__(self):
    #print("Destructor called for", type(self).__name__, self._name)
    pass

  def _build_uri(self):
    self._ws = None
    # try to munge a resolvable host name
    # remote in vm is on another subnet; need host.local resolved to ipv4
    host = self._host
    if host and host.endswith('.local'): host = host[:-6]
    if host and not '.' in host:
      try:
        socket.gethostbyname(host)
      except socket.gaierror as e:
        # cannot resolve, try again with '.local', if so use ipv4 addr
        # this will be slow if host does not exist
        # note: we do not catch exception
        # may cause lufah to always use ipv4 running on Windows w 'host.local'
        ip = socket.gethostbyname(host + '.local')
        host = ip
    self._uri = f'ws://{host}:{self._port}/api/websocket'
    group = self._group # is usually None
    if group and re.match(r'^\/?[\w.-]*$', group):
      # might be connecting to fah 8.1
      if not group.startswith('/'): self._uri += '/'
      self._uri += group
    self._conn = connect(self._uri, ping_interval=None)

  def version(self): return self._version

  def groups(self):
    groups = list(self.data.get('groups', {}).keys())
    if not groups:
      peers = self.data.get('peers', [])
      groups = [s for s in peers if s.startswith("/")]
    return groups

  async def connect(self):
    if self._ws is not None and self._ws.open: return
    if not self._ws:
      if options.verbose: print(f'Opening {self._uri}')
      try:
        self._ws = await self._conn.__aenter__()
      except Exception as e:
        eprint(f"Failed to connect to {self._uri}")
        self.data = {}
        self._version = (0,0,0)
        raise e
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

  async def __aexit__(self, *args, **kwargs):
    await self._conn.__aexit__(*args, **kwargs)


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
    if options.group is not None:
      group = munged_group_name(options, options.group, client.data)
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
      group = munged_group_name(options, options.group, client.data)
    else:
      group = options.group

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


async def experimental(options, **kwargs):
  # ~1 sec delay if remote host ends with '.local'
  client = FahClient(options.host, options.port, options.group)
  await client.connect()
  print(json.dumps(client.data, indent=2))
  # ~10 sec delay exiting if don't close first; no async context manager?
  # destructor is called immediately
  await client.close()


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
  "x"       : experimental,
  "watch"   : watch,
  "start"   : start_or_stop_local_sevice,
  "stop"    : start_or_stop_local_sevice,
}


async def main():
  options = parse_args()

  if not options.command in COMMANDS + HIDDEN_COMMANDS:
    raise Exception(f'error: unknown command: {options.command}')

  func = COMMANDS_DISPATCH.get(options.command)
  if func is None:
    raise Exception(f'error: command {options.command} is not implemented')

  if options.command in NO_CLIENT_COMMANDS:
    client = None
  else:
    client = FahClient(options.host, options.port, options.group)
    await client.connect()

  try:
    if asyncio.iscoroutinefunction(func):
        await func(options, client=client)
    else:
        func(options, client=client)
  except ConnectionClosed:
    if options.verbose: eprint('Connection closed')
  finally:
    if client is not None: await client.close()


if __name__ == '__main__':
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    print('\n')
  except Exception as e:
    eprint(e)
    exit(1)
