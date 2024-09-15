"show log; use control-c to exit"

import argparse
import asyncio
import os
import sys


async def _print_log_lines(client, msg):
    _ = client
    # client doesn't just send arrays
    if isinstance(msg, list) and len(msg) > 1 and msg[0] == "log":
        # ignore index, which is -1 or -2 or may not exist
        v = msg[-1]
        if isinstance(v, str):
            v = [v]
        try:
            if isinstance(v, (list, tuple)):
                for line in v:
                    if line:
                        print(line)
        except BrokenPipeError:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            await client.close()


async def do_log(args: argparse.Namespace):
    "Show client log. Use control-c to exit."
    client = args.client
    client.register_callback(_print_log_lines)
    await client.connect()
    await client.send({"cmd": "log", "enable": True})
    if args.debug:
        return
    if client.is_connected:
        try:
            await client.ws.wait_closed()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
