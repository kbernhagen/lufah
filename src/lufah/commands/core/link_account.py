"""
link to account-token [machine-name]
"""

import argparse
import platform


async def do_link_account(args: argparse.Namespace):
    """
    Link to account by token.

    Requested machine-name change may be ignored by client or delayed.
    Changing machine-name is best done via Web Control.
    """
    client = args.client
    await client.connect()
    if (8, 3, 1) <= client.version:
        token = args.account_token
        name = args.machine_name
        if not token:
            token = client.data.get("info", {}).get("account", "")
        if not name:
            name = client.data.get("info", {}).get("mach_name", "")
        if not name and args.peer == ".":
            name = platform.node()
        if not (token and name):
            raise Exception("Error: unable to determine token and name")
        msg = {"cmd": "link", "token": token, "name": name}
        await client.send(msg)
