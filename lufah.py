#!/usr/bin/env python3
import os
import sys
import json
import asyncio
from urllib.parse import urlparse
import argparse
import re
import datetime
from websockets import connect # pip3 install websockets
from websockets.exceptions import *

program = os.path.basename(sys.argv[0])
version = '0.1.7'

# TODO:
#   lufah . get <keypath> # show json for snapshot.keypath
#   lufah . groups # show json array of names
#   lufah . create-group <name> # by sending pause to nonexistent group
#   lufah . delete-group <name> # refuse if group has running WU?
HIDDEN_COMMANDS = ['x'] # simple experimental stuff
# allowed cli commands; all visible
commands = 'status pause unpause fold finish log config'.split()
if sys.platform == 'darwin': commands += ['start', 'stop']

commandsHelp = dict(
  status = 'default command if none is specified',
  pause = '',
  unpause = 'alias for fold',
  fold = '',
  finish = '',
  log = 'show log; use control-c to exit',
  config = 'get or set config values',
  start = 'start local client service; peer must be "."',
  stop = 'stop local client service; peer must be "."',
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

# removed in 8.3; there may be others
DEPRECATED_CONFIG_KEYS = ["fold_anon", "peers", "checkpoint", "priority"]

# as sent to client, not cli commands
SIMPLE_CLIENT_COMMANDS = ['pause', 'fold', 'unpause', 'finish']


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def bool_from_string(value):
  if value.lower() in ['true', 'yes', 'on', '1']:
    return True
  elif value.lower() in ['false', 'no', 'off', '0']:
    return False
  else:
    raise Exception(f'error: not a bool string: {value}')


# allowed config keys
validKeysValues = {
  "fold-anon": {"type": bool_from_string},
  "user": {"default":'Anonymous', "type":str.strip, "re":r'^[^\t\n\r]{1,100}$',
    "help": 'If you are using unusual chars, please use Web Control.'},
  "team": {"default": 0, "type": int, "values": range(0, 0x7FFFFFFF)},
  "passkey": {"default": '', "type": str.lower, "re": r'^[0-9a-fA-F]{32}$',
    "help": 'passkey must be 32 hexadecimal characters'},
  #"beta": {"type": bool_from_string}, # don't encourage use of this
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

validKeys = validKeysValues.keys()


def validate():
  if options.debug: options.verbose = True
  # do not strip right; 8.3 group names might not be stripped
  # create-group should strip what is specified, as web control does
  options.peer = options.peer.lstrip()
  if not options.peer: raise Exception(f'error: no peer specified')
  r = urlparse('//' + options.peer)
  host = r.hostname or '127.0.0.1' # note r.hostname can be None
  port = r.port or 7396
  group = r.path or ''
  host = host.strip()
  if host == '.': host = '127.0.0.1'

  if not options.command: options.command = 'status'

  if options.debug:
    print(f'   peer: "{options.peer}"')
    print(f'   host: "{host}"')
    print(f'   port: {port}')
    print(f'  group: "{group}"')
    print(f'command: {options.command}')

  # validate group ^\/[\w.-]*$
  # for v8.3, allow "//" prefix, spaces, special chars
  #   '' is no group (all groups)
  #   '/' is default group (actually named '')
  #   '//' is group '/'
  #   anything else tried as-is else without leading /
  if group == '' or re.match(r'^\/[\w.-]*$', group):
    options.legacyGroupMatch = True

  options.host = host
  options.port = port
  options.group = group
  if r.username and r.password: host = f'{r.username}:{r.password}@{host}'
  elif r.username: host = f'{r.username}@{host}'
  # TODO: validate host, port; maybe disallow numeric IPv6 addresses
  if options.legacyGroupMatch:
    options.uri = f'ws://{host}:{port}/api/websocket{group}'
  else:
    # this is what v8.3 expects, but currently appending /group seems ok
    # when v8.1 support is dropped, just use this instead
    # less restrictive group names are not url friendly
    options.uri = f'ws://{host}:{port}/api/websocket'

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
      print(f'key: {key} value: {value}')
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

All commands except config are supported for fah v8.3.
Command config may not behave as expected for fah v8.3.
Command config is not supported with groups for fah v8.3.
Group names must conform to v8.1 restrictions:
  begins "/", has only letters, numbers, period, underscore, hyphen
Group "/" is taken to mean the default group, which is "".
For a group actually named "/" on v8.3, use "//".
An error may not be shown if the initial connection times out.
If group does not exist, script may hang until silent timeout.
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
  for cmd in HIDDEN_COMMANDS:
    subparsers.add_parser(cmd)
  for cmd in commands:
    help = commandsHelp.get(cmd)
    par = subparsers.add_parser(cmd, description=help, help=help)
    if cmd == 'config':
      # TODO: add subparser for each valid config key
      par.add_argument('key', help = ' '.join(validKeys))
      par.add_argument('value', nargs='?',
        help = 'a valid config value for given key')

  options = parser.parse_args()
  validate()


CLIENTS = {}

class FahClient:
  def __init__(self, host='127.0.0.1', port=7396, group=None):
    self._name = f'{host}:{port}'
    self._uri = f'ws://{host}:{port}/api/websocket'
    self._conn = connect(self._uri)
    self._ws = None
    self.data = {} # snapshot
    self._version = (0,0,0) # data.info.version as tuple
  def __del__(self):
    #print("Destructor called for", type(self).__name__, self._name)
    pass
  def version(self): return self._version
  async def connect(self):
    # FIXME: check if connected first
    if not self._ws: self._ws = await self._conn.__aenter__()
    r = await self._ws.recv()
    snapshot = json.loads(r)
    v = snapshot.get("info", {}).get("version", "0")
    self._version = tuple([int(x) for x in v.split('.')])
    self.data.update(snapshot)
    pass
  async def close(self):
    await self._ws.close()
    self._ws = None
  def update(self, data): # data: json array or dict
    if isinstance(v, (dict)):
      self.data.update(data)
    elif isinstance(v, (list)):
      pass # self._process_update_list(data)
  async def __aexit__(self, *args, **kwargs):
    await self._conn.__aexit__(*args, **kwargs)


async def status(uri):
  if options.verbose: print(f'opening {uri}')
  async with connect(uri) as websocket:
    r = await websocket.recv()
    print(r)


def munged_group_name(group, snapshot):
  # return a group name that exists, else throw
  # assume v8.3
  # NOTE: must have connected to have snapshot
  # pre-munging would be simpler if require '//name' for actual '/name'
  groups = list(snapshot.get('groups', {}).keys())
  if group is None: raise Exception(f'error: group is None')
  if options.verbose: print(f'groups: {groups}')
  if group == '/': group = '' # default group
  elif group == '//': group = '/' # literal group name '/'
  elif group.startswith('//'): group = group[1:]
  elif group.startswith('/'):
    group0 = group[1:] # without leading '/'
    if group0 in groups and not group in groups:
      group = group0
  if not group in groups:
    raise Exception(f'error: no "{group}" in groups {groups}')
  if options.debug: print(f'munged group: "{group}"')
  return group


def value_for_key_path(adict, kp):
  # kp: an array of keys or a dot-separated str of keys
  # like to handle int array indicies in str kp
  # ? import munch/addict/benedict
  return None


async def command(uri, cmd):
  if not cmd in SIMPLE_CLIENT_COMMANDS:
    raise Exception(f'unknown client command: {cmd}')
  if options.verbose: print(f'opening {uri}')
  async with connect(uri) as websocket:
    r = await websocket.recv()
    snapshot = json.loads(r)
    v = snapshot.get("info", {}).get("version", "0")
    ver = tuple([int(x) for x in v.split('.')])
    if ver < (8,3):
      if cmd == 'fold': cmd = 'unpause'
      msg = {"cmd": cmd}
    else:
      t = datetime.datetime.utcnow().isoformat() + 'Z'
      if cmd == 'unpause': cmd = 'fold'
      msg = {"state": cmd, "cmd": "state", "time": t}
      # NOTE: group would be created if it doesn't exist
      # need to validate group or /group exists after connect
      # need to strip '/' prefix if group name doesn't have it
      # if default group switches to '/', handle that
      # maybe just always strip leading "/" for v8.3
      # if group is '', cmd applies to all groups (no group)
      # must test before munge to distinguish no group from default group
      if options.group:
        msg["group"] = munged_group_name(options.group, snapshot)
    if options.debug:
      print(f'WOULD BE sending: {json.dumps(msg)}')
      return
    if options.verbose: print(f'sending: {json.dumps(msg)}')
    await websocket.send(json.dumps(msg))


# TODO: refactor into config_get(), config_set(), get_config(snapshot,group)
async def config(uri, key, value):
  if options.verbose: print(f'opening {uri}')
  async with connect(uri) as websocket:
    r = await websocket.recv()
    snapshot = json.loads(r)
    v = snapshot.get("info", {}).get("version", "0")
    ver = tuple([int(x) for x in v.split('.')])
    haveAcct = 0 < len(snapshot.get("info", {}).get("account", ''))

    # FIXME: potential race if groups changes before we write
    # think currently client deletes groups not in group config command
    groups = list(snapshot.get('groups', {}).keys()) # [] on < 8.3
    # we don't care about 8.1 peer groups because everything is in main config
    # just need to be mindful of possible config.available_cpus

    if (8,3) <= ver:
      group = munged_group_name(options.group, snapshot)
    else:
      group = options.group

    # v8.3 splits config between global(account) and group

    key0 = key # might exist in 8.1
    key = key.replace('-', '_') # convert cli keys to actual

    if value is None:
      # print value for key
      if (8,3) <= ver and key in GROUP_CONFIG_KEYS:
        # snapshot.groups.{group}.config
        conf = snapshot.get('groups',{}).get(group,{}).get("config",{})
        print(json.dumps(conf.get(key)))
      else:
        # try getting key, no matter what it is
        conf = snapshot.get('config', {})
        print(json.dumps(conf.get(key, conf.get(key0))))
      return

    if 'cpus' == key:
      maxcpus0 = snapshot.get('info', {}).get('cpus', 0)
      # available_cpus in fah v8.1.19 only
      maxcpus = snapshot.get('config', {}).get('available_cpus', maxcpus0)
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
      group = munged_group_name(options.group, snapshot)

    # TODO: don't send if value == current_value
    # TODO: create appropriate 8.3 config.groups dict with all current groups
    conf = {key: value}
    t = datetime.datetime.utcnow().isoformat() + 'Z'
    msg = {"cmd":"config", "time":t, "config":conf}
    if options.debug:
      print(f'WOULD BE sending: {json.dumps(msg)}')
      return
    if options.verbose: print(f'sending: {json.dumps(msg)}')
    await websocket.send(json.dumps(msg))


async def log(uri):
  if options.verbose: print(f'opening {uri}')
  # ping_interval=None to prevent timeout:
  # sent 1011 (unexpected error) keepalive ping timeout; no close frame received
  async with connect(uri, ping_interval=None) as websocket:
    r = await websocket.recv() # consume snapshot
    t = datetime.datetime.utcnow().isoformat() + 'Z'
    msg = {"cmd": "log", "enable": True, "time": t}
    if options.debug:
      print(f'WOULD BE sending: {json.dumps(msg)}')
      return
    await websocket.send(json.dumps(msg))
    while True:
      r = await websocket.recv()
      msg = json.loads(r)
      # client doesn't just send arrays
      if isinstance(msg, (list)) and len(msg) and msg[0] == 'log':
        # ignore msg[1], which is -1 or -2
        v = msg[2]
        if isinstance(v, (list, tuple)):
          for line in v: print(line)
        else:
          print(v)


async def experimental():
  # seems to work
  # ~1 sec delay if remote host ends with '.local'
  client = FahClient(options.host, options.port, options.group)
  await client.connect()
  print(json.dumps(client.data, indent=2))
  #print(client.version())
  # ~10 sec delay exiting if don't close first; no async context manager?
  # destructor is called immediatly
  await client.close()


async def main():
  parse_args()

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
    return

  if options.command == 'x':
    await experimental()

  elif options.command in [None, '', 'status']:
    await status(options.uri)

  elif options.command in SIMPLE_CLIENT_COMMANDS:
    await command(options.uri, options.command)

  elif options.command in ['config']:
    await config(options.uri, options.key, options.value)

  elif options.command in ['log']:
    try:
      await log(options.uri)
    except ConnectionClosed:
      if options.verbose: print('connection closed')
      pass

  else:
    raise Exception(f'unknown command: {options.command}')


if __name__ == '__main__':
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    print('\n')
  except Exception as e:
    eprint(e)
    exit(1)
