"""Tests for connection validation in commands"""

import asyncio
import os
import socket

import pytest

from lufah.commands import (
    validate_multi_client_connections,
    validate_single_client_connection,
)
from lufah.fahclient import FahClient


def _fahclient_available() -> bool:
    """Check if FAHClient service is running on localhost:7396."""
    # Integration tests are disabled by default to prevent hanging
    # Set RUN_INTEGRATION_TESTS=1 to enable them
    # if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    #    return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            sock.connect(("127.0.0.1", 7396))
        return True
    except Exception:
        return False


# Allow running these tests with RUN_INTEGRATION_TESTS=1 or when FAHClient is available
FAHCLIENT_AVAILABLE = (
    os.getenv("RUN_INTEGRATION_TESTS") == "1" or _fahclient_available()
)


@pytest.mark.asyncio
@pytest.mark.skipif(
    not FAHCLIENT_AVAILABLE,
    reason="FAHClient integration tests disabled (set RUN_INTEGRATION_TESTS=1 to enable)",
)
async def test_validate_single_client_connection_success():
    """Test that validate_single_client_connection succeeds for connected client.

    Note: Requires a FAHClient running on localhost:7396 to pass.
    """
    client = FahClient("localhost:7396")
    try:
        await asyncio.wait_for(client.connect(), timeout=5)
        # If connection succeeds, validation should pass without exception
        validate_single_client_connection(client)
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not FAHCLIENT_AVAILABLE,
    reason="FAHClient integration tests disabled (set RUN_INTEGRATION_TESTS=1 to enable)",
)
async def test_validate_single_client_connection_failure():
    """Test that validate_single_client_connection raises exception for disconnected client."""
    # Use an invalid address that won't connect
    client = FahClient("127.0.0.1:7397")  # Non-existent port
    try:
        await client.connect()
        # Connection should fail silently
        assert not client.is_connected
        # Validation should raise Exception
        with pytest.raises(Exception, match="failed to connect"):
            validate_single_client_connection(client)
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not FAHCLIENT_AVAILABLE,
    reason="FAHClient integration tests disabled (set RUN_INTEGRATION_TESTS=1 to enable)",
)
async def test_validate_multi_client_connections_all_success():
    """Test that validate_multi_client_connections succeeds with all connected.

    Note: Requires a FAHClient running on localhost:7396 to pass.
    """
    client1 = FahClient("localhost:7396")
    client2 = FahClient("127.0.0.1:7396")  # Same client, should succeed
    try:
        await asyncio.wait_for(client1.connect(), timeout=5)
        await asyncio.wait_for(client2.connect(), timeout=5)
        # Should return count of connected clients and not raise
        count = validate_multi_client_connections([client1, client2])
        assert count == 2  # Both should be connected
    finally:
        await client1.close()
        await client2.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not FAHCLIENT_AVAILABLE,
    reason="FAHClient integration tests disabled (set RUN_INTEGRATION_TESTS=1 to enable)",
)
async def test_validate_multi_client_connections_all_failure():
    """Test that validate_multi_client_connections raises exception if all clients fail."""
    client1 = FahClient("127.0.0.1:7397")  # Non-existent port
    client2 = FahClient("127.0.0.1:7398")  # Non-existent port
    try:
        await client1.connect()
        await client2.connect()
        # Both should fail to connect
        assert not client1.is_connected
        assert not client2.is_connected
        # Validation should raise Exception
        with pytest.raises(Exception, match="Failed to connect to any clients"):
            validate_multi_client_connections([client1, client2])
    finally:
        await client1.close()
        await client2.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not FAHCLIENT_AVAILABLE,
    reason="FAHClient integration tests disabled (set RUN_INTEGRATION_TESTS=1 to enable)",
)
async def test_validate_multi_client_connections_partial_success():
    """Test that validate_multi_client_connections succeeds with partial connections.

    Note: Requires a FAHClient running on localhost:7396 to pass.
    """
    client1 = FahClient("localhost:7396")
    client2 = FahClient("127.0.0.1:7397")  # Will fail
    try:
        await asyncio.wait_for(client1.connect(), timeout=5)
        await asyncio.wait_for(client2.connect(), timeout=5)
        # Should succeed because at least one is connected
        count = validate_multi_client_connections([client1, client2])
        assert count >= 1
    finally:
        await client1.close()
        await client2.close()
