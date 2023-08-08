#!/usr/bin/env python3
import os
import sys
import json
import asyncio
from urllib.parse import urlparse
import argparse
import re
from websockets import connect # pip3 install websockets
from websockets.exceptions import *

program = os.path.basename(sys.argv[0])
version = '0.1.3'

commands = 'status pause unpause finish log config'.split()
if sys.platform == 'darwin': commands += ['start', 'stop']


def bool_from_string(value):
  if value.lower() in ['true', 'yes', 'on', '1']:
    return True
  elif value.lower() in ['false', 'no', 'off', '0']:
    return False
  else:
    raise Exception(f'error: not a bool string: {value}')


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
  # no peer editing; an add-peer command might be reasonable
  # it would be an error to change gpus, paused, finish
  # get-only keys
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

  r = urlparse('//' + options.peer)
  host = r.hostname or '127.0.0.1'
  port = r.port or 7396
  group = r.path or ''
  if host == '.': host = '127.0.0.1'
  # validate group ^\/[\w.-]*$ future ^\/[\w.-]+$
  if group and not re.match(r'^\/[\w.-]*$', group):
    raise Exception(f'error: group must consist of letters, numbers, period, underscore, hyphen')

  options.host = host
  options.port = port
  options.group = group
  if r.username and r.password: host = f'{r.username}:{r.password}@{host}'
  options.uri = f'ws://{host}:{port}/api/websocket{group}'

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
        print('warning: leading/trailing whitespace removed from user',
          file=sys.stderr)

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
      return
    else:
      raise Exception(f'error: config {key} is read-only')


def parse_args():
  global options
  description = 'Little Utility for FAH v8'
  epilog = f'''
Examples

{program} . finish
{program} other.local/rg1 status
{program} /my-p-cores config priority normal

Notes

An error may not be shown if initial connection times out.
If group does not exist, script will hang until silent timeout.
Command log may not notice a disconnect.
'''

  parser = argparse.ArgumentParser(description=description, epilog=epilog,
    formatter_class=argparse.RawDescriptionHelpFormatter)

  parser.set_defaults(key=None, value=None)
  parser.set_defaults(host='127.0.0.1', port=7396, group='', uri='')

  parser.add_argument('-v', '--verbose', action='store_true')
  parser.add_argument('-d', '--debug', action='store_true')
  parser.add_argument('--version', action='version', version=version)

  parser.add_argument('peer', default = '.',
    help = '[host][:port][/group]  Use "." for localhost')

  subparsers = parser.add_subparsers(dest='command', metavar = 'command')
  for cmd in commands:
    # TODO: put help text in a validCommands dict
    help = None
    if cmd in ['start', 'stop']:
      help = f'{cmd} local client service; peer must be "."'
    elif cmd == 'config':
      help = 'get or set config values'
    elif cmd == 'log':
      help = 'show log; use control-c to exit'
    par = subparsers.add_parser(cmd, description=help, help=help)
    if cmd == 'config':
      # TODO: add subparser for each valid config key
      par.add_argument('key', help = ' '.join(validKeys))
      par.add_argument('value', nargs='?',
        help = 'a valid config value for given key')

  options = parser.parse_args()
  validate()


async def status(uri):
  if options.verbose: print(f'opening {uri}')
  async with connect(uri) as websocket:
    r = await websocket.recv()
    print(r)


async def command(uri, cmd):
  if options.verbose: print(f'opening {uri}')
  async with connect(uri) as websocket:
    if options.verbose: print(f'sending command: {cmd}')
    await websocket.send(json.dumps({"cmd": cmd}))


async def config(uri, key, value):
  if options.verbose: print(f'opening {uri}')
  async with connect(uri) as websocket:
    r = await websocket.recv()
    snapshot = json.loads(r)
    key = key.replace('-', '_')
    if value is None:
      print(json.dumps(snapshot.get('config', {}).get(key)))
      return
    if 'cpus' == key:
      maxcpus0 = snapshot.get('info', {}).get('cpus', 0)
      # available_cpus in fah v8.1.19+
      maxcpus = snapshot.get('config', {}).get('available_cpus', maxcpus0)
      if value > maxcpus:
        raise Exception(f'error: cpus is greater than available cpus {maxcpus}')
    conf = {key: value}
    if options.debug:
      print(f'WOULD BE sending config: {json.dumps(conf)}')
      return
    if options.verbose: print(f'sending config: {json.dumps(conf)}')
    await websocket.send(json.dumps({"cmd": "config", "config": conf}))


async def log(uri, group):
  if options.verbose: print(f'opening {uri}')
  # ping_interval=None to prevent timeout:
  # sent 1011 (unexpected error) keepalive ping timeout; no close frame received
  async with connect(uri, ping_interval=None) as websocket:
    r = await websocket.recv()
    await websocket.send(json.dumps({"cmd": "log", "enable": True}))
    while True:
      r = await websocket.recv()
      msg = json.loads(r)
      if group:
        filter = f':{group}:'
        if msg[0] == 'log' and filter in msg[2]: print(msg[2])
      else:
        if msg[0] == 'log': print(msg[2])


async def main():
  parse_args()

  if sys.platform == 'darwin' and options.command in ['start', 'stop']:
    if options.peer != '.':
      raise Exception('peer must be "." for commands start and stop')
    from subprocess import check_call
    note = f'org.foldingathome.fahclient.nobody.{options.command}'
    cmd = ['notifyutil', '-p', note]
    if options.verbose: print(' '.join(cmd))
    check_call(cmd)
    return

  if options.command in [None, '', 'status']:
    await status(options.uri)

  elif options.command in ['pause', 'unpause', 'finish']:
    await command(options.uri, options.command)

  elif options.command in ['config']:
    await config(options.uri, options.key, options.value)

  elif options.command in ['log']:
    try:
      await log(options.uri, options.group)
    except ConnectionClosed:
      if options.verbose: print('connection closed')
      pass

  else:
    raise Exception(f'unknown command: {options.command}')


if __name__ == '__main__':
  try:
    asyncio.run(main())
  except KeyboardInterrupt:
    pass
  except Exception as e:
    print(e, file=sys.stderr)
    exit(1)
