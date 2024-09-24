"""
dump all paused units in specified group or all groups
"""

import argparse
import sys

from lufah.logger import logger

from .units import print_unit, print_units_header


async def do_dump_all(args: argparse.Namespace):
    """
    Dump all paused units in specified group or all groups.

    This command is not interactive.
    To dump units, use option "--force".
    You should only dump a WU if it will not be completed before its deadline.
    The ETA may not be accuarate until progress is a few percent done.
    """
    client = args.client
    await client.connect()
    if client.version < (8, 3):
        raise Exception("Error: dump-all requires client 8.3+")
    group = client.group
    units = client.paused_units_in_group(group)
    if len(units) == 0:
        msg = f"{client.machine_name}: no paused units found"
        if group is not None:
            msg += f' in group "{group}"'
        if sys.stdout.isatty():
            print(msg)
        else:
            logger.info("%s", msg)
        return
    if sys.stdout.isatty():
        print("Units to dump:")
        print_units_header()
        for unit in units:
            print_unit(client, unit)
    if not args.force:
        msg = f"{client.name}: to dump units, use option --force"
        if sys.stdout.isatty():
            print(msg)
        else:
            logger.warning("%s", msg)
        return
    for unit in units:
        await client.dump_unit(unit)
