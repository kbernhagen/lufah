"show incoming messages; use control-c to exit"

import argparse
import json


async def _print_json_message(_client, msg):
    if isinstance(msg, (list, dict, str)):
        print(json.dumps(msg))


async def do_watch(args: argparse.Namespace):
    "Show incoming messages. Use control-c to exit."
    client = args.client
    client.register_callback(_print_json_message)
    await client.connect()
    print(json.dumps(client.data, indent=2))
    await client.ws.wait_closed()
