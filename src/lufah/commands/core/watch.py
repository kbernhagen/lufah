"show incoming messages; use control-c to exit"

import argparse
import json


async def _print_json_message(_client, msg):
    if isinstance(msg, (list, str)):
        print(json.dumps(msg))
    elif isinstance(msg, (dict)):
        print(json.dumps(msg, indent=2))


async def do_watch(args: argparse.Namespace):
    "Show incoming messages. Use control-c to exit."
    client = args.client
    client.register_callback(_print_json_message)
    await client.connect()
    await client.ws.wait_closed()
