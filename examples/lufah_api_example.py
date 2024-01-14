#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# pylint: disable=bare-except,broad-exception-caught

"""an example of lufah as api"""

import asyncio

from lufah import FahClient, OPTIONS

OPTIONS.verbose = True

_CONFIG = {
  "peers": [
    "localhost",
    ":7399/zz",
    "other.local:9999/some group name"
  ]
}

COMMAND_FOLD   = 'fold' # same as 'unpause'
COMMAND_FINISH = 'finish'
COMMAND_PAUSE  = 'pause'

async def send_command_to_clients(cmd: str, clients: list):
  """send command to all clients"""
  for client in clients:
    try:
      await client.send_command(cmd)
    except:
      pass

async def main_async():
  """example main_async"""
  clients = []
  try:
    for peer in _CONFIG.get('peers'):
      try:
        client = FahClient(peer)
        await client.connect()
        clients.append(client)
      except Exception as e:
        print(e)
    await send_command_to_clients(COMMAND_FINISH, clients)
  finally:
    for client in clients:
      await client.close()

def main():
  """example main"""
  try:
    asyncio.run(main_async())
  except KeyboardInterrupt:
    pass

if __name__ == '__main__':
  main()
