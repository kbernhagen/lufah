"show json value at dot-separated key path in client state"

import argparse
import json

from lufah.commands import validate_single_client_connection
from lufah.util import get_object_at_key_path


async def do_get(args: argparse.Namespace):
    "Show json value at dot-separated key path in client state."
    client = args.client
    await client.connect()
    validate_single_client_connection(client)
    value = get_object_at_key_path(client.data, args.keypath)
    print(json.dumps(value, indent=2))
