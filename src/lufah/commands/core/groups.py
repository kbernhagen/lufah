"show json array of resource group names"

import argparse
import json

from lufah.commands import validate_single_client_connection


async def do_groups(args: argparse.Namespace):
    "Show json array of resource group names."
    client = args.client
    await client.connect()
    validate_single_client_connection(client)
    print(json.dumps(client.groups))
