"create group if it does not exist"

import argparse

from lufah.commands import validate_single_client_connection


async def do_create_group(args: argparse.Namespace):
    "Create group if it does not exist."
    client = args.client
    await client.connect()
    validate_single_client_connection(client)
    await client.create_group(args.group)


async def do_delete_group(args: argparse.Namespace):
    'Delete group if it exists, is not "", is paused, and has no units.'
    client = args.client
    await client.connect()
    validate_single_client_connection(client)
    await client.delete_group(args.group)
