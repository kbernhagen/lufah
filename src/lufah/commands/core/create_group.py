"create group if it does not exist"

import argparse


async def do_create_group(args: argparse.Namespace):
    "Create group if it does not exist."
    client = args.client
    await client.connect()
    await client.create_group(client.group)


async def do_delete_group(args: argparse.Namespace):
    'Delete group if it exists, is not "", is paused, and has no units.'
    client = args.client
    await client.connect()
    await client.delete_group(client.group)
