"unlink account"

import argparse

from lufah.commands import validate_single_client_connection


async def do_unlink_account(args: argparse.Namespace):
    """
    Unlink account. Requires client 8.3.1 thru 8.3.16.

    Use Web Control to unlink newer clients.
    """
    client = args.client
    await client.connect()
    validate_single_client_connection(client)
    if (8, 3, 1) <= client.version and client.version < (8, 3, 17):
        await client.send({"cmd": "reset"})
    else:
        raise Exception("Error: unlink account requires client 8.3.1 thru 8.3.16")
