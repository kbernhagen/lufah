"show json snapshot of client state"

import argparse
import json

from lufah.commands import validate_single_client_connection


async def do_state(args: argparse.Namespace):
    "Show json snapshot of client state."
    client = args.client
    await client.connect()
    validate_single_client_connection(client)
    print(json.dumps(client.data, indent=2))
