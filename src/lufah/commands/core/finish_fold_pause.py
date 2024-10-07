# pylint: disable=missing-module-docstring

import argparse
import asyncio


async def _do_command_multi(args: argparse.Namespace, command=None):
    await asyncio.gather(*[c.connect() for c in args.clients])
    for client in args.clients:
        try:
            if client.is_connected:
                await client.send_command(command or args.command)
        except Exception as e:
            raise Exception(f"Error: FahClient('{client.name}'):{e}") from e


async def do_finish(args: argparse.Namespace):
    "Finish folding and pause specified group or all groups."
    await _do_command_multi(args, command="finish")


async def do_fold(args: argparse.Namespace):
    "Start folding in specified group or all groups."
    await _do_command_multi(args, command="fold")


async def do_pause(args: argparse.Namespace):
    "Pause folding in specified group or all groups."
    await _do_command_multi(args, command="pause")
