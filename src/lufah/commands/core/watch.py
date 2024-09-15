"show incoming messages; use control-c to exit"

import argparse
import asyncio
import copy
import json
import logging

from lufah.util import diff_dicts

LOGGER = logging.getLogger(__name__)


async def _print_json_message(client, msg):
    _ = client
    if isinstance(msg, (list, dict, str)):
        print(json.dumps(msg))


async def do_watch(args: argparse.Namespace):
    "Show incoming messages. Use control-c to exit."
    client = args.client
    client.register_callback(_print_json_message)
    client.should_process_updates = args.debug
    await client.connect()
    if args.debug:
        snapshot0 = copy.deepcopy(client.data)
    print(json.dumps(client.data, indent=2))
    try:
        await client.ws.wait_closed()
    except (KeyboardInterrupt, asyncio.CancelledError):
        LOGGER.debug("do_watch() caught KeyboardInterrupt or asyncio.CancelledError")
    finally:
        if args.debug:
            diff = diff_dicts(snapshot0, client.data)
            print("\nChanges since connection opened:\n", json.dumps(diff, indent=2))
