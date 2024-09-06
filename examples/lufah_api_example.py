#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = [
#     "lufah",
# ]
# ///

"""an example of lufah as api"""

from __future__ import annotations

import asyncio
import logging

from lufah import COMMAND_FINISH, COMMAND_FOLD, COMMAND_PAUSE, FahClient  # noqa: F401

_CONFIG = {"peers": ["localhost", "/no such group", "other.local:9999/some group name"]}


async def send_command_to_clients(cmd: str, clients: list[FahClient]):
    """send command to all clients"""
    for client in clients:
        try:
            await client.send_command(cmd)
        except:  # noqa: E722
            pass


async def main_async():
    """example main_async"""
    logging.basicConfig(level=logging.INFO)
    clients = []
    try:
        for peer in _CONFIG.get("peers", []):
            try:
                client = FahClient(peer)
                await client.connect()
                clients.append(client)
            except Exception as e:
                print(e)
        await send_command_to_clients(COMMAND_FINISH, clients)
    finally:
        for client in clients:
            await client.close()


def main():
    """example main"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
