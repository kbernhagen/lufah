"show json snapshot of client state"

import argparse
import json


async def do_state(args: argparse.Namespace):
    "Show json snapshot of client state."
    client = args.client
    await client.connect()
    print(json.dumps(client.data, indent=2))
