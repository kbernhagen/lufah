#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=fixme,missing-function-docstring
# pylint: disable=broad-exception-raised,broad-exception-caught,bare-except
# pylint: disable=too-many-branches,too-many-statements,too-many-lines
# pylint: disable=global-statement # this is for argparse OPTIONS
# pylint: disable=too-many-instance-attributes,wildcard-import
# pylint: disable=too-many-locals
# FIXME: this is excessive disabling

"""
lufah: Little Utility for FAH v8
"""

import os
import sys
import json
import asyncio
import argparse
import re
import errno
import math
import copy
import logging
import platform
from urllib.parse import urlparse
from urllib.request import urlopen
from subprocess import check_call

from websockets.exceptions import ConnectionClosed

from . import __version__
from .const import * # pylint: disable=unused-wildcard-import
from .exceptions import * # pylint: disable=unused-wildcard-import
from .fahclient import FahClient
from .util import (
  eprint, bool_from_string, diff_dicts,
  munged_group_name, uri_and_group_for_peer, get_object_at_key_path
  )


PROGRAM = os.path.basename(sys.argv[0])
if PROGRAM.endswith(".py"):
  PROGRAM = PROGRAM[:-3]

_LOGGER = logging.getLogger(__name__)

OPTIONS = argparse.Namespace()
OPTIONS.verbose = False
OPTIONS.debug = False

_CLIENTS = {}

# TODO:
# lufah . delete-group <name> # refuse if running WU, unless --force
# lufah file:~/peers.json units
#   { "peers": ["peer1", "peer2", ...] }
# lufah /mygpus enable-all-gpus
# lufah . wait-until-paused # wait until all groups are paused (finished)


# FIXME: default is not restricted
# suggest only allow status, units, log, watch
DEFAULT_COMMAND = 'units'

HIDDEN_COMMANDS = ['x'] # experimental stuff
NO_CLIENT_COMMANDS = ['start', 'stop', 'x']

MULTI_PEER_COMMANDS = ['units', 'info', 'fold', 'finish', 'pause']

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
  'create-group',
  'info',
  'log',
  'watch',
  'get',
  'unlink-account',
  'link-account',
  'restart-account',
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
  'link-account' : '<account-token> [<machine-name>]',
  'restart-account' : 'restart account/node connection',
  'create-group' : 'create group if it does not exist',
}


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
  "on-battery": {"type": bool_from_string},
  "keep-awake": {"type": bool_from_string},
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
  if _LOGGER.isEnabledFor(logging.INFO):
    _LOGGER.info('Causes: %s', json.dumps(data, indent=2))
  return data


def validate():
  if OPTIONS.debug:
    OPTIONS.verbose = True

  if OPTIONS.debug:
    logging.basicConfig(level=logging.DEBUG)
  elif OPTIONS.verbose:
    logging.basicConfig(level=logging.INFO)
  else:
    logging.basicConfig(level=logging.WARNING)

  OPTIONS.peer = OPTIONS.peer.lstrip() # ONLY left strip
  if not OPTIONS.peer:
    raise Exception('ERROR: no peer specified')
  # true validation of peer is done by uri_and_group_for_peer()
  # TODO: accept file:~/peers.json containing {"peers":[".","host2","host3"]}
  #   set OPTIONS.peers; set OPTIONS.peer = None

  if OPTIONS.command in [None, '']:
    OPTIONS.command = DEFAULT_COMMAND
  else:
    OPTIONS.command = COMMAND_ALIASES.get(OPTIONS.command, OPTIONS.command)

  OPTIONS.peers = []
  if ',' in OPTIONS.peer and not '/' in OPTIONS.peer:
    # assume comma separated list of peers
    peers = OPTIONS.peer.split(',')
    for peer in peers:
      peer = peer.strip()
      if peer:
        OPTIONS.peers.append(peer)
    _LOGGER.debug('  peers: %s', repr(OPTIONS.peers))
    OPTIONS.peer = None
  else:
    OPTIONS.peers = [OPTIONS.peer]

  if OPTIONS.peer and re.match(r'^[^/]*,.*/.*$', OPTIONS.peer):
    raise Exception('ERROR: host cannot have a comma')

  if OPTIONS.peer is None and not OPTIONS.command in MULTI_PEER_COMMANDS:
    raise Exception(f'ERROR: {OPTIONS.command!r} cannot use multiple peers')

  if OPTIONS.command == 'link-account':
    token = OPTIONS.account_token
    name = OPTIONS.machine_name
    # token is URL base64 encoding of 32 bytes, no padding '=', else ""
    if token and not re.match(r'^[a-zA-Z0-9_\-]{43}$', token):
      raise Exception('ERROR: token must be 43 url base64 characters')
    if name and not re.match(r'^[\w\.-]{1,64}$', name):
      raise Exception('ERROR: name must be 1 to 64 letters, numbers, '
        'underscore, dash (-), dot(.)')
    # empty/null token or name is handled after connecting
    return

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

    if _LOGGER.isEnabledFor(logging.DEBUG):
      _LOGGER.debug('         key: %s', key)
      _LOGGER.debug('       value: %s', value)
      _LOGGER.debug('  valid keys: %s', " ".join(keys))
      _LOGGER.debug('valid values: %s', values)
      _LOGGER.debug('     default: %s', default)
      _LOGGER.debug('       regex: %s', regex)
      _LOGGER.debug('type convert: %s', conv)

    if not key in keys:
      k = ' '.join(keys)
      raise Exception(f'Unsupported config key: {key}\nKnown keys: {k}')

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
        raise Exception('ERROR: max user length is 100 bytes')
      if value != value0:
        _LOGGER.warning('Leading/trailing whitespace trimmed from user')

    if values:
      if value in values:
        return
      m = f'ERROR: invalid value for {key}: {value}\nvalid values: {values}'
      raise Exception(m)
    if regex:
      if not re.match(regex, value):
        m = f'ERROR: invalid {key} value: {value}'
        help1 = info.get('help')
        if help1:
          m += '\n' + help1
        raise Exception(m)
      return # valid regex match
    raise Exception(f'ERROR: config {key} is read-only')


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
  parser.set_defaults(account_token=None, machine_name=None)

  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('-d', '--debug', action='store_true')
  parser.add_argument('--version', action='version', version=__version__)

  help2 = '''\
[host][:port][/group]
Use "." for localhost.
Peer can be a comma-separated list of hosts for commands
units, info, fold, finish, pause:
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
    elif cmd == 'link-account':
      par.add_argument('account_token', metavar='<account-token>',
        help = '43 url base64 characters (32 bytes); use "" for current token')
      par.add_argument('machine_name', nargs='?', metavar='<machine-name>',
        help = '1 to 64 letters, numbers, underscore, dash (-), dot(.)')

  for cmd in HIDDEN_COMMANDS:
    subparsers.add_parser(cmd)

  OPTIONS = parser.parse_args()
  OPTIONS.argparser = parser
  validate()


async def do_status(client):
  await client.connect()
  print(json.dumps(client.data, indent=2))


async def do_command_multi(**_):
  for client in _CLIENTS.values():
    try:
      await client.connect()
      await client.send_command(OPTIONS.command)
    except:
      pass


# TODO: refactor into config_get(), config_set(), get_config(snapshot,group)
async def do_config(client):
  await client.connect()
  key = OPTIONS.key
  value = OPTIONS.value
  ver = client.version
  have_acct = 0 < len(client.data.get("info", {}).get("account", ''))

  # FIXME: potential race if groups changes before we write
  # think currently client deletes groups not in group config command
  groups = client.groups # [] on 8.2; 8.1 may have peer groups
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
      raise Exception(f'ERROR: cpus is greater than available cpus {maxcpus}')
    # FIXME: cpus are in groups on fah 8.3; need to sum cpus across groups
    # available_cpus = maxcpus - total_group_cpus
    # if value > (available_cpus - current_group_cpus)
    # this is simpler if only have one group (the default group)
    # no need to calc available_cpus if new value is 0
    # NOTE: client will not limit cpus value sent for us

  if (8,3) <= ver:
    if key in DEPRECATED_CONFIG_KEYS:
      raise Exception(f'ERROR: key "{key0}" is deprecated in fah 8.3')
    if not key in VALID_CONFIG_SET_KEYS:
      raise Exception(f'ERROR: setting "{key0}" is not supported in fah 8.3')
    if have_acct and key in GLOBAL_CONFIG_KEYS:
      _LOGGER.warning('Machine is linked to an account')
      _LOGGER.warning(' "%s" "%s" may be overwritten by account', key0, value)

  # TODO: don't send if value == current_value
  conf = {key: value}
  msg = {"cmd":"config", "config":conf}
  if (8,3) <= ver and key in GROUP_CONFIG_KEYS:
    if group is None:
      raise Exception(f'ERROR: cannot set "{key0}" on group None')
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
  if isinstance(msg, list) and len(msg) > 1 and msg[0] == 'log':
    # ignore index, which is -1 or -2 or may not exist
    v = msg[-1]
    if isinstance(v, str):
      v = [v]
    try:
      if isinstance(v, (list, tuple)):
        for line in v:
          if line:
            print(line)
    except BrokenPipeError:
      devnull = os.open(os.devnull, os.O_WRONLY)
      os.dup2(devnull, sys.stdout.fileno())
      await client.close()


async def do_log(client):
  client.register_callback(_print_log_lines)
  await client.connect()
  await client.send({"cmd": "log", "enable": True})
  if OPTIONS.debug:
    return
  if client.is_connected:
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
  print('uri_and_group_for_peer: ', uri_and_group_for_peer(OPTIONS.peer))


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
  client.should_process_updates = OPTIONS.debug
  await client.connect()
  if OPTIONS.debug:
    snapshot0 = copy.deepcopy(client.data)
  print(json.dumps(client.data, indent=2))
  try:
    await client.ws.wait_closed()
  finally:
    # ctrl-c seems uncatchable, but finally works
    if OPTIONS.debug:
      diff = diff_dicts(snapshot0, client.data)
      print('\nChanges since connection opened:\n',
        json.dumps(diff, indent=2))


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
    _LOGGER.error(' units_for_group(client, group): client is None')
    return []
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
  return client.data.get('info', {}).get('hostname', client.name)


def clients_sorted_by_machine_name():
  return sorted(list(_CLIENTS.values()), key=client_machine_name)


async def do_print_units(**_):
  for client in _CLIENTS.values():
    await client.connect()
  if _CLIENTS:
    print_units_header()
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
      if not client.is_connected:
        print(name + '  NOT CONNECTED')
        continue
      print(name)
      units = units_for_group(client, None)
      if not units:
        continue
      for unit in units:
        print_unit(client, unit)
    else:
      for group in groups:
        print(f'{name}/{group}')
        units = units_for_group(client, group)
        if not units:
          continue
        for unit in units:
          print_unit(client, unit)


def print_info(client):
  if client is None:
    return
  info = client.data.get('info',{})
  if not info:
    return
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
      _LOGGER.debug('WOULD BE running: %s', " ".join(cmd))
      return
    _LOGGER.info('%s', ' '.join(cmd))
    check_call(cmd)


async def do_create_group(client):
  await client.connect()
  await client.create_group(client.group)


async def do_unlink_account(client):
  await client.connect()
  if (8,3,1) <= client.version and client.version < (8,3,17):
    await client.send({"cmd":"reset"})
  else:
    raise Exception('unlink account requires client 8.3.1 thru 8.3.16')


async def do_restart_account(client):
  await client.connect()
  if (8,3,17) <= client.version:
    await client.send({"cmd":"restart"})
  else:
    raise Exception('restart account requires client 8.3.17+')


async def do_link_account(client):
  await client.connect()
  if (8,3,1) <= client.version:
    token = OPTIONS.account_token
    name = OPTIONS.machine_name
    if not token:
      token = client.data.get('info', {}).get('account', '')
    if not name:
      name = client.data.get('info', {}).get('mach_name', '')
    if not name and OPTIONS.peer == '.':
      name = platform.node()
    if not (token and name):
      raise Exception('ERROR: unable to determine token and name')
    msg = {"cmd":"link", "token":token, "name":name}
    await client.send(msg)


COMMANDS_DISPATCH = {
  "status"  : do_status,
  "fold"    : do_command_multi,
  "finish"  : do_command_multi,
  "pause"   : do_command_multi,
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
  "unlink-account" : do_unlink_account,
  "link-account"   : do_link_account,
  "restart-account": do_restart_account,
  "create-group"   : do_create_group,
}


async def main_async():
  parse_args()

  if not OPTIONS.command in COMMANDS + HIDDEN_COMMANDS:
    raise Exception(f'ERROR:Unknown command: {OPTIONS.command}')

  func = COMMANDS_DISPATCH.get(OPTIONS.command)
  if func is None:
    raise Exception(f'ERROR:Command {OPTIONS.command} is not implemented')

  client = None
  if not OPTIONS.command in NO_CLIENT_COMMANDS:
    for peer in OPTIONS.peers:
      c = FahClient(peer)
      if c is not None:
        _CLIENTS[peer] = c
    if len(_CLIENTS) == 1:
      client = list(_CLIENTS.values())[0]

  try:
    if asyncio.iscoroutinefunction(func):
      await func(client=client)
    else:
      func(client=client)
  except ConnectionClosed:
    _LOGGER.info('Connection closed')
  finally:
    for c in _CLIENTS.values():
      await c.close()


def main():
  try:
    asyncio.run(main_async())
  except (KeyboardInterrupt, EOFError):
    pass
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
