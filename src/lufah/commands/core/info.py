"show host and client info"

import argparse
import asyncio


def _print_info(client):
    if client is None:
        return
    info = client.data.get("info", {})
    if not info:
        return
    clientver = info.get("version", "")  # the string, not tuple
    osname = info.get("os", "")
    osver = info.get("os_version", "")
    cpu = info.get("cpu", "")
    brand = info.get("cpu_brand", "")
    cores = info.get("cpus", 0)
    host = info.get("hostname", "")
    print(f"  Host: {host}")
    print(f"Client: {clientver}")
    print(f"    OS: {osname} {osver}")
    print(f'   CPU: {cores} cores, {cpu}, "{brand}"')


async def do_info(args: argparse.Namespace):
    "Show host and client info."
    await asyncio.gather(*[c.connect() for c in args.clients])
    clients = sorted(args.clients, key=lambda c: c.machine_name)
    multi = len(clients) > 1
    if multi:
        print()
    for client in clients:
        _print_info(client)
        if multi and client.is_connected:
            print()
