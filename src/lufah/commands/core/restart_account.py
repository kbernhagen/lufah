"restart account/node connection"

import argparse


async def do_restart_account(args: argparse.Namespace):
    """
    Restart account/node connection.

    This is useful if the client has lost its node
    connection and is not automatically reconnecting.
    """
    client = args.client
    await client.connect()
    if (8, 3, 17) <= client.version:
        await client.send({"cmd": "restart"})
    else:
        raise Exception("Error: restart account requires client 8.3.17+")
