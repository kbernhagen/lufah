"show json array of resource group names"

import argparse
import json


async def do_groups(args: argparse.Namespace):
    "Show json array of resource group names."
    client = args.client
    await client.connect()
    print(json.dumps(client.groups))
