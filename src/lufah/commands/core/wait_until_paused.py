"run until specified group or all groups are paused"

import argparse

from lufah.logger import logger


async def _close_if_paused(client, _):
    # unused: msg
    group = client.group
    if group is None:
        groups = client.groups
    elif group not in client.groups:
        raise Exception(f'group "{group}" does not exist')
    else:
        groups = [group]
    for group in groups:
        # return if any group is not paused
        gconfig = client.data.get("groups", {}).get(group, {}).get("config", {})
        paused = gconfig.get("paused", None)
        # finish = gconfig.get('finish', False)
        if paused is False:
            return
        if paused is None:
            logger.warning('no value for paused in group "%s"', group)
    # all target groups are assumed paused
    await client.close()


async def do_wait_until_paused(args: argparse.Namespace):
    "Run until specified group or all groups are paused."
    client = args.client
    client.register_callback(_close_if_paused)
    client.should_process_updates = True
    await client.connect()
    if client.version < (8, 3, 17):
        raise Exception("Error: wait-until-paused requires client 8.3.17+")
    if args.debug:
        return
    # process initial connection snapshot
    await _close_if_paused(client, None)
    if client.is_connected:
        await client.ws.wait_closed()
