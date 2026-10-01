"""Tests for wait-until-paused; uses a fake client, no network needed"""

import argparse

import pytest

from lufah.commands.core.wait_until_paused import do_wait_until_paused


class FakeClient:  # pylint: disable=R0902
    """Mimics FahClient.connect() dispatching the initial snapshot to callbacks"""

    name = "fake"
    version = (8, 4, 0)

    def __init__(self, paused: bool, connects: bool = True):
        self.data = {
            "groups": {"": {"config": {"paused": paused, "cpus": 4, "gpus": {}}}}
        }
        self.groups = [""]
        self.is_connected = False
        self._connects = connects
        self._callbacks = []

    def register_callback(self, callback):
        self._callbacks.append(callback)

    async def connect(self):
        if not self._connects:
            return
        self.is_connected = True
        for callback in self._callbacks:
            await callback(self, self.data)

    async def close(self):
        self.is_connected = False

    async def wait_closed(self):
        assert not self.is_connected, "would block forever"


def _args(client, group=None):
    return argparse.Namespace(client=client, group=group)


async def test_already_paused_exits_cleanly():
    """Snapshot closes client during connect(); must not report a failed connection"""
    await do_wait_until_paused(_args(FakeClient(paused=True)))


async def test_running_keeps_waiting():
    """Not paused: client stays connected and we go on to wait_closed()"""
    client = FakeClient(paused=False)
    with pytest.raises(AssertionError, match="would block forever"):
        await do_wait_until_paused(_args(client))
    assert client.is_connected


async def test_connect_failure_still_reported():
    """A real connection failure must still raise"""
    with pytest.raises(Exception, match="failed to connect"):
        await do_wait_until_paused(_args(FakeClient(paused=True, connects=False)))


async def test_paused_state_does_not_leak_between_runs():
    """Flag from an already-paused run must not hide a later connection failure"""
    await do_wait_until_paused(_args(FakeClient(paused=True)))
    with pytest.raises(Exception, match="failed to connect"):
        await do_wait_until_paused(_args(FakeClient(paused=True, connects=False)))
