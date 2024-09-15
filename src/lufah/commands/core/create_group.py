"create group if it does not exist"

import argparse


async def do_create_group(args: argparse.Namespace):
    "Create group if it does not exist."
    client = args.client
    await client.connect()
    await client.create_group(client.group)
