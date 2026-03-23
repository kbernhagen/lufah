"""Tests for connection validation in commands"""

import asyncio

import pytest

from lufah.commands import (
    validate_multi_client_connections,
    validate_single_client_connection,
)
from lufah.fahclient import FahClient


def test_validate_single_client_connection_success():
    """Test that validate_single_client_connection succeeds for connected client.

    Note: Requires a FAHClient running on localhost:7396 to pass.
    """

    async def run_test():
        client = FahClient("localhost:7396")
        try:
            await asyncio.wait_for(client.connect(), timeout=5)
            # If connection succeeds, validation should pass without exception
            validate_single_client_connection(client)
        finally:
            await client.close()

    asyncio.run(run_test())


def test_validate_single_client_connection_failure():
    """Test that validate_single_client_connection raises exception for disconnected client."""

    async def run_test():
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

    asyncio.run(run_test())


def test_validate_multi_client_connections_all_success():
    """Test that validate_multi_client_connections succeeds with all connected.

    Note: Requires a FAHClient running on localhost:7396 to pass.
    """

    async def run_test():
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

    asyncio.run(run_test())


def test_validate_multi_client_connections_all_failure():
    """Test that validate_multi_client_connections raises exception if all clients fail."""

    async def run_test():
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

    asyncio.run(run_test())


def test_validate_multi_client_connections_partial_success():
    """Test that validate_multi_client_connections succeeds with partial connections.

    Note: Requires a FAHClient running on localhost:7396 to pass.
    """

    async def run_test():
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

    asyncio.run(run_test())
