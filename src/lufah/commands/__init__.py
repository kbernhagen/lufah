"""Shared command utilities"""

from lufah.logger import logger


def validate_single_client_connection(client):
    """Validate that a single client is connected.

    Args:
        client: A FahClient instance

    Raises:
        Exception: If client is not connected, with exit code 1
    """
    if not client.is_connected:
        raise Exception(f"Error: {client.name} failed to connect")


def validate_multi_client_connections(clients):
    """Validate that multi-client connections have at least one successful connection.

    For each failed connection, logs a warning. If all connections fail, raises an exception.

    Args:
        clients: A list of FahClient instances

    Returns:
        int: The number of successfully connected clients

    Raises:
        Exception: If zero clients are connected, with exit code 1
    """
    connected_count = 0
    for client in clients:
        if client.is_connected:
            connected_count += 1
        else:
            logger.warning("Failed to connect to %s", client.name)

    if connected_count == 0:
        raise Exception("Error: Failed to connect to any clients")

    return connected_count
